"""
请求体大小限制中间件模块

该模块提供 ASGI 级别的请求体大小限制中间件。
在请求体被读取/解析之前检查 Content-Length header，
超限请求立即返回 413 Payload Too Large 响应，
避免将超大请求体读入内存导致 OOM 风险。

使用方式:
    from app.core.request_size_limit import RequestSizeLimitMiddleware
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=1_048_576)
"""

import json

from loguru import logger
from starlette.types import ASGIApp, Scope, Receive, Send


class RequestSizeLimitMiddleware:
    """请求体大小限制 ASGI 中间件

    在 ASGI 层面拦截超大请求体，是防止内存耗尽 DoS 攻击的第一道防线。
    通过检查 HTTP Content-Length header 实现轻量级限制，
    在 body 被读取前即可拒绝请求，零内存开销。

    Attributes:
        app: 内层 ASGI 应用实例。
        max_size_bytes: 允许的最大请求体字节数。
    """

    def __init__(self, app: ASGIApp, max_size_bytes: int = 1_048_576) -> None:
        """初始化请求体大小限制中间件。

        Args:
            app: 内层 ASGI 应用实例。
            max_size_bytes: 允许的最大请求体字节数，默认为 1MB (1048576 bytes)。
        """
        self.app = app
        self.max_size_bytes = max_size_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 入口点。

        仅处理 HTTP 请求：检查 Content-Length header，
        若超过限制则立即返回 413 响应，否则透传至内层应用。

        Args:
            scope: ASGI scope 字典。
            receive: ASGI receive callable。
            send: ASGI send callable。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = self._extract_content_length(scope)

        if content_length is not None and content_length > self.max_size_bytes:
            max_mb = self.max_size_bytes // (1024 * 1024)
            logger.warning(
                f"Request body too large: {content_length} bytes "
                f"(limit: {self.max_size_bytes} bytes / {max_mb}MB), "
                f"path={scope.get('path', '/')}"
            )
            await self._send_413_response(send, max_mb)
            return

        await self.app(scope, receive, send)

    def _extract_content_length(self, scope: Scope) -> int | None:
        """从 ASGI scope 中提取 Content-Length header 值。

        Args:
            scope: ASGI scope 字典。

        Returns:
            解析后的 Content-Length 整数值，若 header 不存在或无效则返回 None。
        """
        for key, value in scope.get("headers", []):
            if key == b"content-length":
                try:
                    return int(value.decode("latin-1"))
                except (ValueError, UnicodeDecodeError):
                    return None
        return None

    async def _send_413_response(self, send: Send, max_mb: int) -> None:
        """发送 413 Payload Too Large 响应。

        使用 Delta Sharing 标准错误响应格式。

        Args:
            send: ASGI send callable。
            max_mb: 最大请求体大小（MB），用于错误消息。
        """
        error_body = json.dumps(
            {
                "errorCode": "REQUEST_TOO_LARGE",
                "message": f"Request body exceeds maximum size of {max_mb}MB",
            }
        ).encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(error_body)).encode("latin-1")),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": error_body,
            }
        )
