"""
Delta Sharing Iceberg Server 主模块

该模块是 Delta Sharing Server 的应用入口点，负责：
- 创建和配置 FastAPI 应用实例
- 初始化数据库连接
- 初始化腾讯云 COS 客户端
- 配置 loguru 全局日志（应用日志流 B）
- 配置 CORS 中间件和统一请求日志中间件
- 注册所有 API 路由

服务器遵循 Delta Sharing 协议，为 Iceberg 表格式提供兼容支持。
通过 bearer token 进行身份验证，支持 Pandas/Spark/Databricks 等客户端访问。

启动方式:
    cd server && uv run python main.py
"""

from dotenv import load_dotenv

load_dotenv(".env.local", override=True)

import json
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.types import ASGIApp, Scope, Receive, Send, Message

from app.core.config import load_config, get_config
from app.core.database import init_database, get_database
from app.core.cos_client import init_cos_client
from app.core.audit import request_id_ctx, get_audit_logger
from app.core.cache import CacheMiddleware, _request_cache_managers
from app.core.errors import DeltaSharingError, ErrorCode
from app.core.logging_config import configure_logging

from app.routes.shares import router as shares_router
from app.routes.metadata import router as metadata_router
from app.routes.version import router as version_router
from app.routes.query import router as query_router
from app.routes.health import router as health_router
from app.api.admin import admin_router

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class AuditLoggingMiddleware:
    """审计日志中间件（原始 ASGI 级）

    使用原始 ASGI 中间件代替 Starlette BaseHTTPMiddleware，
    因为后者返回的 _StreamingResponse 不支持同步读取响应体。
    本中间件通过包装 ASGI send 函数拦截响应体字节，
    从而在错误响应（status >= 400）中提取 errorCode 和 message。

    端口分离后，每个应用实例通过 app_category 参数指定默认审计分类：
    - Data Plane 应用使用 "data_plane"
    - Admin API 应用使用 "admin"

    Attributes:
        app: 内层 ASGI 应用实例。
        app_category: 默认审计日志分类标签，用于路径不匹配已知前缀时的 fallback。
    """

    def __init__(self, app: ASGIApp, app_category: str = "internal") -> None:
        """初始化审计日志中间件。

        Args:
            app: 内层 ASGI 应用实例。
            app_category: 默认审计日志分类标签（"data_plane" | "admin" | "internal"）。
        """
        self.app = app
        self.app_category = app_category

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 入口点。

        仅处理 HTTP 请求：为每个请求生成 request_id，
        包装 send 函数以收集响应体，请求完成后自动
        记录审计日志（含错误详情）。

        Args:
            scope: ASGI scope 字典。
            receive: ASGI receive callable。
            send: 原始 ASGI send callable。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 生成请求唯一标识
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)
        request_id_ctx.set(request_id)

        start_time = time.time()
        response_body_chunks: list[bytes] = []
        response_status: list[int] = [200]

        async def send_wrapper(message: Message) -> None:
            """包装后的 send 函数，拦截响应状态码和响应体字节。"""
            if message["type"] == "http.response.start":
                response_status[0] = message["status"]
            elif message["type"] == "http.response.body":
                response_body_chunks.append(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # 请求结束后始终记录审计日志
            duration_ms = int((time.time() - start_time) * 1000)
            status_code = response_status[0]

            audit_logger = get_audit_logger()
            if not audit_logger.is_recorded():
                path = scope.get("path", "/")
                # 路径优先匹配，未匹配时 fallback 到应用实例的 app_category
                if path.startswith("/health"):
                    category = "health"
                elif path.startswith("/delta-sharing/admin"):
                    category = "admin"
                elif path.startswith("/delta-sharing"):
                    category = "data_plane"
                else:
                    category = self.app_category

                # 提取错误响应中的 error_code / error_message
                error_code = None
                error_message = None
                if status_code >= 400 and response_body_chunks:
                    try:
                        body = b"".join(response_body_chunks)
                        err_data = json.loads(body.decode("utf-8"))
                        if isinstance(err_data, dict):
                            # 格式1: HTTPException 包装
                            # → {"detail": {"errorCode": ..., "message": ...}}
                            detail = err_data.get("detail", {})
                            if isinstance(detail, dict):
                                error_code = detail.get("errorCode")
                                error_message = detail.get("message")
                            # 格式2: DeltaSharingError 处理器直接返回
                            # → {"errorCode": ..., "message": ...}
                            if not error_code:
                                error_code = err_data.get("errorCode")
                            if not error_message:
                                error_message = err_data.get("message")
                    except Exception:
                        logger.debug("Failed to parse error response body for audit logging")

                audit_logger.log(
                    operation=f"{scope.get('method', 'UNKNOWN')}_{path.split('?')[0]}",
                    category=category,
                    http_method=scope.get("method"),
                    http_path=path,
                    http_status_code=status_code,
                    http_duration_ms=duration_ms,
                    error_code=error_code,
                    error_message=error_message,
                )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器

    使用 FastAPI 推荐的 lifespan 事件处理器替代已弃用的 on_event 钩子。
    yield 之前的代码在应用启动时执行，yield 之后的代码在应用关闭时执行。
    由于双应用共享进程，仅 Data Plane 应用注册 lifespan 以管理数据库关闭。
    """
    # 启动逻辑（如有需要可在此添加）
    yield
    # 关闭逻辑：优雅关闭数据库连接
    logger.info("正在关闭数据库连接...")
    try:
        db = get_database()
        db.close()
        logger.info("数据库连接已关闭")
    except Exception:
        pass


def _register_common_exception_handlers(app: FastAPI) -> None:
    """为 FastAPI 应用注册公共异常处理器。

    该辅助函数提取了 Data Plane 和 Admin API 共用的异常处理逻辑，
    包括 DeltaSharingError、HTTPException 和通用 Exception 处理器。

    Args:
        app: 需要注册异常处理器的 FastAPI 应用实例。
    """
    _AUTH_ERROR_CODES = {
        ErrorCode.AUTHENTICATION_HEADER_MISSING,
        ErrorCode.AUTHENTICATION_HEADER_INVALID,
        ErrorCode.INVALID_TOKEN,
        ErrorCode.TOKEN_MALFORMED,
        ErrorCode.TOKEN_EXPIRED,
        ErrorCode.TOKEN_REVOKED,
    }

    @app.exception_handler(DeltaSharingError)
    async def delta_sharing_error_handler(request: Request, exc: DeltaSharingError):
        """Delta Sharing 错误异常处理器。

        将 DeltaSharingError 异常转换为标准 JSON 响应格式。
        对于认证相关错误码，自动追加 WWW-Authenticate: Bearer 响应头。

        Args:
            request: HTTP 请求对象。
            exc: DeltaSharingError 异常实例。

        Returns:
            JSON 格式的错误响应。
        """
        headers = None
        if exc.error_code in _AUTH_ERROR_CODES:
            headers = {"WWW-Authenticate": "Bearer"}
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
            headers=headers,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """HTTPException 全局处理器。

        将 FastAPI 默认的 HTTPException 重新包装为统一的错误响应格式。
        对 detail 为 dict 的（已包装好的）保留原样；
        对 detail 为 str 的默认格式包装为结构化错误。

        Args:
            request: HTTP 请求对象。
            exc: HTTPException 异常实例。

        Returns:
            JSON 格式的错误响应。
        """
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"errorCode": "INVALID_REQUEST", "message": str(exc.detail)},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """通用 Exception 异常处理器（安全网兜底）。

        捕获所有未分类的 Python 异常，记录完整 traceback，
        返回 500 INTERNAL_ERROR 结构化响应，永不暴露 HTML traceback。

        Args:
            request: HTTP 请求对象。
            exc: 未捕获的异常实例。

        Returns:
            500 JSON 格式的错误响应。
        """
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={"errorCode": "INTERNAL_ERROR", "message": "Internal server error"},
        )


def create_data_plane_app() -> FastAPI:
    """创建 Data Plane 的 FastAPI 应用实例。

    Data Plane 处理客户端数据访问请求，绑定到 0.0.0.0:8088，
    允许任意来源的 CORS，注册 health 端点和所有数据面路由。

    Returns:
        配置完成的 Data Plane FastAPI 应用实例。
    """
    app = FastAPI(
        title="Delta Sharing Server - Data Plane",
        description="A Delta Sharing protocol compatible server for Iceberg tables",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS 允许所有来源（数据面需要从任意客户端接收请求）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 请求级缓存中间件
    app.add_middleware(CacheMiddleware, managers=_request_cache_managers)

    # 审计日志中间件：Data Plane 应用的所有请求默认为 data_plane 分类
    app.add_middleware(AuditLoggingMiddleware, app_category="data_plane")

    # 注册公共异常处理器
    _register_common_exception_handlers(app)

    # 注册路由：health 端点和 Data Plane 数据面路由
    app.include_router(health_router)
    app.include_router(shares_router, prefix="/delta-sharing")
    app.include_router(metadata_router, prefix="/delta-sharing")
    app.include_router(version_router, prefix="/delta-sharing")
    app.include_router(query_router, prefix="/delta-sharing")

    return app


def create_admin_app() -> FastAPI:
    """创建 Admin API 的 FastAPI 应用实例。

    Admin API 处理管理端操作请求，绑定到 127.0.0.1:8089，
    仅允许 localhost 来源的 CORS，注册管理路由。

    admin_router 自带 prefix="/admin/v1"，在此处添加 prefix="/delta-sharing"
    后组合出完整路径 /delta-sharing/admin/v1/...，与原有路径保持一致。

    Returns:
        配置完成的 Admin API FastAPI 应用实例。
    """
    app = FastAPI(
        title="Delta Sharing Server - Admin API",
        description="Admin API for managing shares, recipients, and tokens",
        version="0.1.0",
    )

    # CORS 仅允许 localhost 来源（Admin API 仅限本地管理端访问）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 请求级缓存中间件
    app.add_middleware(CacheMiddleware, managers=_request_cache_managers)

    # 审计日志中间件：Admin API 应用的所有请求默认为 admin 分类
    app.add_middleware(AuditLoggingMiddleware, app_category="admin")

    # 注册公共异常处理器
    _register_common_exception_handlers(app)

    # 注册路由：admin_router 自带 /admin/v1 prefix，添加 /delta-sharing 后
    # 组合成完整路径 /delta-sharing/admin/v1/...
    app.include_router(admin_router, prefix="/delta-sharing")

    return app


def main():
    import asyncio
    import uvicorn

    # 1. 加载配置
    load_config("./config.yaml")
    config = get_config()

    # 2. 配置 loguru 全局日志
    configure_logging(
        log_dir=getattr(config.logging, "log_dir", "./log"),
        log_level=getattr(config.logging, "app_log_level", "INFO"),
        log_retention=getattr(config.logging, "app_log_retention", "30 days"),
    )

    # 3. 初始化数据库（共享连接池）
    init_database()

    # 4. 初始化 COS 客户端（共享）
    init_cos_client()

    # 5. 创建两个独立的应用实例
    data_plane_app = create_data_plane_app()
    admin_app = create_admin_app()

    # 6. 创建两个 uvicorn 配置
    data_plane_config = uvicorn.Config(
        data_plane_app,
        host=config.server.host,
        port=config.server.port,
        log_level="info",
        timeout_keep_alive=30,
    )

    admin_config = uvicorn.Config(
        admin_app,
        host=config.server.admin_host,
        port=config.server.admin_port,
        log_level="info",
        timeout_keep_alive=30,
    )

    # 7. 并发启动两个 uvicorn 服务器
    data_plane_server = uvicorn.Server(data_plane_config)
    admin_server = uvicorn.Server(admin_config)

    logger.info(
        f"启动双端口服务: "
        f"Data Plane @ {config.server.host}:{config.server.port}, "
        f"Admin API @ {config.server.admin_host}:{config.server.admin_port}"
    )

    async def serve():
        await asyncio.gather(
            data_plane_server.serve(),
            admin_server.serve(),
        )

    asyncio.run(serve())


if __name__ == "__main__":
    main()
