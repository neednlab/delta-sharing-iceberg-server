"""
认证服务模块

该模块提供 Delta Sharing Server 的身份认证功能，包括：
- Bearer Token 的验证和撤销
- Token 轮换
- Token 信息查询
- FastAPI 认证依赖函数

认证服务使用 TokenRepository 进行数据访问，Service 层负责业务逻辑判断。
"""

import hashlib
from typing import Optional, Dict, Any

from fastapi import Request

from app.core.config import get_config
from app.core.errors import DeltaSharingError, ErrorCode
from app.repositories.token_repository import TokenRepository
from app.utils.time_utils import now_ts


# 模块级 AuthService 单例，避免每次认证请求重复创建实例
_auth_service: Optional["AuthService"] = None


def _get_auth_service() -> "AuthService":
    """获取 AuthService 模块级单例。

    延迟初始化，首次调用时创建实例，后续调用复用同一实例。

    Returns:
        AuthService 单例实例。
    """
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


async def get_current_recipient(request: Request) -> str:
    """FastAPI 认证依赖函数，验证 Bearer Token 并返回接收者 ID。

    该函数作为 FastAPI 依赖使用，确保所有受保护的 API 端点都经过身份验证。
    仅通过一次数据库查询（validate_token）完成所有状态检查。
    区分不同的认证失败原因并返回适当的 HTTP 状态码。

    Args:
        request: HTTP 请求对象。

    Returns:
        经验证的接收者 ID。

    Raises:
        DeltaSharingError: 如果认证失败或 token 无效。
            - 401: 认证头缺失、格式无效或 token 无效
            - 403: Token 已过期或已被撤销
    """
    authorization = request.headers.get("authorization")

    if authorization is None:
        raise DeltaSharingError(
            ErrorCode.AUTHENTICATION_HEADER_MISSING,
            "Missing authorization header",
            status_code=401,
        )

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise DeltaSharingError(
            ErrorCode.AUTHENTICATION_HEADER_INVALID,
            "Invalid authorization header format",
            status_code=401,
        )

    token = parts[1]

    if not token:
        raise DeltaSharingError(
            ErrorCode.TOKEN_MALFORMED,
            "Token is empty",
            status_code=401,
        )

    # 单次数据库查询完成所有 token 状态检查（是否有效、是否撤销、是否过期）
    auth_service = _get_auth_service()
    token_info = auth_service.validate_token(token)

    if token_info is None:
        raise DeltaSharingError(
            ErrorCode.INVALID_TOKEN,
            "Invalid or expired bearer token",
            status_code=401,
        )

    if token_info.get("is_revoked", False):
        raise DeltaSharingError(
            ErrorCode.TOKEN_REVOKED,
            "Token has been revoked",
            status_code=403,
        )

    if token_info.get("is_expired", False):
        raise DeltaSharingError(
            ErrorCode.TOKEN_EXPIRED,
            "Token has expired",
            status_code=403,
        )

    return token_info.get("recipient_id")


class AuthService:
    """认证服务类

    该类提供 Bearer Token 的完整生命周期管理功能。
    使用 TokenRepository 进行数据访问，Service 层负责过期/撤销判断等业务逻辑。

    Attributes:
        config: 全局配置实例。
        token_repo: TokenRepository 实例。
    """

    def __init__(self):
        """初始化认证服务。"""
        self.config = get_config()
        self.token_repo = TokenRepository()

    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证 Token 的有效性。

        对输入 token 做 SHA-256 哈希后，通过 TokenRepository 查询记录。
        单次数据库查询完成所有状态检查（是否存在、是否撤销、是否过期）。

        注意：此方法不再对已撤销 token 返回 None，而是返回包含
        is_revoked=True 的字典，由调用方根据业务需求处理。

        Args:
            token: 待验证的 Token 明文字符串。

        Returns:
            如果 token 未找到返回 None；
            否则返回包含 recipient_id、expires_at、is_expired、is_revoked 的字典。
        """
        if not token:
            return None

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        record = self.token_repo.find_by_hash(token_hash)

        if not record:
            return None

        is_expired = False
        if record["expires_at"]:
            if now_ts() > record["expires_at"]:
                is_expired = True

        return {
            "recipient_id": record["recipient_id"],
            "expires_at": record["expires_at"],
            "is_expired": is_expired,
            "is_revoked": record["is_revoked"],
        }

    def is_token_revoked(self, token: str) -> bool:
        """检查 Token 是否已被撤销。

        对输入 token 做 SHA-256 哈希后查询撤销表。
        此方法用于管理端独立查询撤销状态，不用于认证热路径。

        Args:
            token: 待检查的 Token 明文字符串。

        Returns:
            如果 Token 已被撤销返回 True，否则返回 False。
        """
        if not token:
            return False
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return self.token_repo.is_revoked(token_hash)

    def revoke_token(self, token: str, reason: Optional[str] = None) -> bool:
        """撤销指定的 Token。

        对输入 token 做 SHA-256 哈希后调用 TokenRepository 执行撤销。

        Args:
            token: 要撤销的 Token 明文字符串。
            reason: 撤销原因（可选）。

        Returns:
            如果成功撤销返回 True，否则返回 False。
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return self.token_repo.revoke(token_hash, reason)

    def get_token_info(self, token: str) -> Optional[Dict[str, Any]]:
        """获取 Token 的详细信息。

        对输入 token 做 SHA-256 哈希后查询数据库。
        返回结构与 validate_token 保持一致。

        Args:
            token: Token 明文字符串。

        Returns:
            包含 Token 详细信息的字典，包括 recipient_id、expires_at、
            is_expired、is_revoked。未找到则返回 None。
        """
        if not token:
            return None

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        record = self.token_repo.find_by_hash(token_hash)

        if not record:
            return None

        is_expired = False
        if record["expires_at"]:
            if now_ts() > record["expires_at"]:
                is_expired = True

        return {
            "recipient_id": record["recipient_id"],
            "expires_at": record["expires_at"],
            "is_expired": is_expired,
            "is_revoked": record["is_revoked"],
        }


def normalize_name(name: str) -> str:
    """规范化名称。

    将名称转换为小写，用于不区分大小写的比较。

    Args:
        name: 待规范的名称。

    Returns:
        小写格式的名称。
    """
    return name.lower()
