"""
Admin API - 管理员认证端点

该模块提供 Admin UI 的管理员登录/登出 API：
- POST /auth/login: 用户名密码登录，返回 JWT Cookie
- POST /auth/logout: 清除 JWT Cookie
- GET /auth/me: 获取当前登录管理员信息

端点路径前缀: /admin/v1/auth
"""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.core.audit import get_audit_logger
from app.core.errors import ErrorCode, DeltaSharingError
from app.core.security import create_admin_token, verify_password
from app.core.admin_auth import get_current_admin
from app.repositories.admin_user_repository import AdminUserRepository
from app.utils.audit_utils import raise_audited_error
from loguru import logger


router = APIRouter(prefix="/auth", tags=["admin-auth"])


class LoginRequest(BaseModel):
    """登录请求模型"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """登录响应模型"""
    admin_id: str
    username: str
    display_name: str


class AdminInfoResponse(BaseModel):
    """管理员信息响应模型"""
    admin_id: str
    username: str
    display_name: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response, request: Request = None):
    """管理员登录。

    验证用户名和密码，成功后签发 JWT Token 并设置到 HttpOnly Cookie 中。
    Cookie 属性：HttpOnly（JS 不可读取）、SameSite=Strict（防 CSRF）。

    Args:
        body: 包含 username 和 password 的登录请求。
        response: FastAPI Response 对象，用于设置 Cookie。
        request: HTTP Request 对象（用于审计日志）。

    Returns:
        LoginResponse: 包含 admin_id、username、display_name。

    Raises:
        DeltaSharingError: 登录失败时返回 401。
    """
    audit_logger = get_audit_logger()
    try:
        # 参数校验
        if not body.username or not body.password:
            raise DeltaSharingError(
                ErrorCode.INVALID_PARAMETER_VALUE,
                "Username and password are required.",
                status_code=401,
            )

        # 查找管理员用户
        repo = AdminUserRepository()
        admin = repo.find_by_username(body.username)

        if admin is None:
            logger.warning(
                f"管理员登录失败：用户不存在 | username={body.username} | "
                f"client={request.client.host if request and request.client else 'unknown'}"
            )
            raise DeltaSharingError(
                ErrorCode.INVALID_TOKEN,
                "Invalid username or password.",
                status_code=401,
            )

        # 检查账户是否激活
        if not admin.get("is_active", 0):
            logger.warning(
                f"管理员登录失败：账户已停用 | username={body.username}"
            )
            raise DeltaSharingError(
                ErrorCode.TOKEN_REVOKED,
                "Account is disabled.",
                status_code=401,
            )

        # 验证密码
        if not verify_password(body.password, admin["password_hash"]):
            logger.warning(
                f"管理员登录失败：密码错误 | username={body.username} | "
                f"client={request.client.host if request and request.client else 'unknown'}"
            )
            raise DeltaSharingError(
                ErrorCode.INVALID_TOKEN,
                "Invalid username or password.",
                status_code=401,
            )

        # 签发 JWT Token 并设置 Cookie
        token = create_admin_token(admin["admin_id"])

        # 设置 HttpOnly Cookie
        # secure=False 用于开发环境（非 HTTPS）；生产部署时应改为 True
        response.set_cookie(
            key="admin_token",
            value=token,
            httponly=True,      # JS 不可读取，防 XSS
            samesite="strict",  # 防 CSRF
            secure=False,       # 开发环境无需 HTTPS
            max_age=8 * 60 * 60,  # 8 小时有效期
            path="/",           # Cookie 适用于所有路径
        )

        logger.info(
            f"管理员登录成功 | username={body.username} | "
            f"admin_id={admin['admin_id'][:8]}... | "
            f"client={request.client.host if request and request.client else 'unknown'}"
        )

        return LoginResponse(
            admin_id=admin["admin_id"],
            username=admin["username"],
            display_name=admin.get("display_name", ""),
        )

    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_LOGIN",
            request=request,
            category="admin",
        )
    except Exception:
        logger.exception("管理员登录时发生未预期错误")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error",
                status_code=500,
            ),
            "ADMIN_LOGIN",
            request=request,
            category="admin",
        )


@router.post("/logout")
async def logout(response: Response):
    """管理员登出。

    清除 admin_token Cookie，使客户端失去认证状态。
    即使未登录也返回 200 OK（幂等操作）。

    Args:
        response: FastAPI Response 对象，用于清除 Cookie。

    Returns:
        dict: {"message": "Logged out successfully"}
    """
    response.delete_cookie(
        key="admin_token",
        path="/",
        httponly=True,
        samesite="strict",
        secure=False,
    )
    logger.info("管理员登出成功")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=AdminInfoResponse)
async def get_current_admin_info(
    admin_id: str = Depends(get_current_admin),
    request: Request = None,
):
    """获取当前登录管理员信息。

    通过 get_current_admin 依赖进行 JWT 验证。
    如果未登录或 JWT 无效则返回 401。

    Args:
        admin_id: 由 get_current_admin 依赖注入的已认证管理员 ID。
        request: HTTP Request 对象（用于审计日志）。

    Returns:
        AdminInfoResponse: 当前管理员的信息。
    """
    audit_logger = get_audit_logger()
    try:
        repo = AdminUserRepository()
        admin = repo.find_by_id(admin_id)

        if admin is None:
            raise DeltaSharingError(
                ErrorCode.INVALID_TOKEN,
                "Invalid session.",
                status_code=401,
            )

        return AdminInfoResponse(
            admin_id=admin["admin_id"],
            username=admin["username"],
            display_name=admin.get("display_name", ""),
        )

    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_GET_ME",
            request=request,
            category="admin",
        )
    except Exception:
        logger.exception("获取管理员信息时发生未预期错误")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error",
                status_code=500,
            ),
            "ADMIN_GET_ME",
            request=request,
            category="admin",
        )
