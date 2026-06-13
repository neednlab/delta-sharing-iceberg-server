"""
Admin 认证依赖模块

该模块提供 FastAPI 依赖注入函数 get_current_admin()，
用于保护 Admin API 端点。从请求 Cookie 中提取和验证 JWT Token，
返回当前登录的管理员 ID。

与 Data Plane 的 get_current_recipient() 模式一致，
区别在于 Admin 认证从 Cookie 中读取 JWT 而非 Authorization header。
"""

from fastapi import Request
from loguru import logger

from app.core.errors import DeltaSharingError, ErrorCode
from app.core.security import decode_admin_token
from app.repositories.admin_user_repository import AdminUserRepository


async def get_current_admin(request: Request) -> str:
    """FastAPI 依赖函数，从 Cookie 中验证管理员 JWT 并返回 admin_id。

    该函数作为 FastAPI 依赖使用，确保所有 Admin API 端点都经过管理员认证。
    从请求的 Cookie 中获取 admin_token，解码验证 JWT 后返回管理员 ID。

    认证流程：
    1. 从 Cookie 中提取 admin_token
    2. 调用 decode_admin_token() 解码和验证 JWT
    3. 验证通过后查询数据库确认管理员存在且激活
    4. 返回 admin_id 供下游使用

    Args:
        request: FastAPI Request 对象。

    Returns:
        已验证的管理员 ID（UUID 字符串）。

    Raises:
        DeltaSharingError:
            - 401: Cookie 缺失、JWT 无效或用户不存在
            - 403: 管理员账户已停用
    """
    # 从 Cookie 中提取 admin_token
    token = request.cookies.get("admin_token")
    if not token:
        logger.warning(
            "管理员认证失败：admin_token Cookie 缺失 | "
            f"path={request.url.path} | "
            f"client={request.client.host if request.client else 'unknown'}"
        )
        raise DeltaSharingError(
            ErrorCode.AUTHENTICATION_HEADER_MISSING,
            "Authentication required. Please login first.",
            status_code=401,
        )

    # 解码验证 JWT
    payload = decode_admin_token(token)
    if payload is None:
        logger.warning(
            "管理员认证失败：JWT 无效或已过期 | "
            f"path={request.url.path} | "
            f"client={request.client.host if request.client else 'unknown'}"
        )
        raise DeltaSharingError(
            ErrorCode.INVALID_TOKEN,
            "Invalid or expired session. Please login again.",
            status_code=401,
        )

    admin_id = payload.get("sub")
    if not admin_id:
        logger.warning("管理员认证失败：JWT 中缺少 sub 声明")
        raise DeltaSharingError(
            ErrorCode.INVALID_TOKEN,
            "Invalid session token.",
            status_code=401,
        )

    # 验证管理员在数据库中存在且激活
    admin_repo = AdminUserRepository()
    admin = admin_repo.find_by_id(admin_id)

    if admin is None:
        logger.warning(
            f"管理员认证失败：数据库中未找到 admin_id={admin_id[:8]}..."
        )
        raise DeltaSharingError(
            ErrorCode.INVALID_TOKEN,
            "Invalid session. Please login again.",
            status_code=401,
        )

    if not admin.get("is_active", 0):
        logger.warning(
            f"管理员认证失败：账户已停用 | admin_id={admin_id[:8]}... | "
            f"username={admin.get('username')}"
        )
        raise DeltaSharingError(
            ErrorCode.TOKEN_REVOKED,
            "Account is disabled. Please contact system administrator.",
            status_code=403,
        )

    logger.debug(f"管理员认证成功 | admin_id={admin_id[:8]}... | path={request.url.path}")
    return admin_id
