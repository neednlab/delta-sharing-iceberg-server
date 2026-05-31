"""
Token 配额服务模块

该模块提供 Bearer Token 的配额管理和验证功能，包括：
- 统计有效 token 数量
- Token 生成前的状态和配额验证
- Token 列表查询
- Profile 数据构建（不持久化，通过 API 响应即时交付）

该服务在 AuthService 基础上增加了 recipient 状态验证、share 授权验证和 token 配额控制。
所有数据访问委托 TokenRepository 执行。
"""

from typing import Dict, Any, List

from app.core.config import get_config
from app.core.errors import (
    DeltaSharingError,
    ErrorCode,
    TokenQuotaExceededError,
    RecipientInactiveError,
    NoSharesAssignedError,
)
from app.repositories.token_repository import TokenRepository
from app.utils.time_utils import ts_to_datetime


class TokenService:
    """Token 配额服务类

    提供 Bearer Token 的配额管理和验证功能。
    在 AuthService 基础上增加了 recipient 状态验证、share 授权验证和 token 配额控制。
    Profile 数据由本服务构建并通过 API 响应即时交付，不持久化到数据库。

    Attributes:
        config: 全局配置实例。
        token_repo: TokenRepository 实例。
    """

    def __init__(self):
        """初始化 Token 服务。"""
        self.config = get_config()
        self.token_repo = TokenRepository()

    def count_active_tokens(self, recipient_id: str) -> int:
        """统计 recipient 持有的有效 token 数量。

        有效 token 定义为：is_revoked=0 且未过期。

        Args:
            recipient_id: Recipient UUID。

        Returns:
            有效 token 数量。
        """
        return self.token_repo.count_active(recipient_id)

    def generate_token(
        self,
        recipient_id: str,
        require_authorized_shares: bool = True,
        expiration_hours: int = None,
    ) -> Dict[str, Any]:
        """生成新的 Bearer Token。

        在生成 token 前验证：
        1. recipient 状态必须为激活
        2. recipient 必须至少有一个授权的 share
        3. token 配额不能超过限制

        Args:
            recipient_id: Recipient UUID。
            require_authorized_shares: 是否要求有授权的 share。
            expiration_hours: 过期小时数，如果为 None 则使用配置默认值。

        Returns:
            包含 token 和 expires_at 的字典。

        Raises:
            RecipientInactiveError: 如果 recipient 未激活。
            NoSharesAssignedError: 如果 recipient 没有授权的 share。
            TokenQuotaExceededError: 如果 token 配额已满。
        """
        from app.services.recipient_service import RecipientService
        from app.services.authorization_service import AuthorizationService

        recipient_service = RecipientService()
        recipient = recipient_service.get_recipient_by_id(recipient_id)
        if not recipient:
            raise DeltaSharingError(
                ErrorCode.RECIPIENT_NOT_FOUND,
                f"Recipient '{recipient_id}' not found",
            )

        if not recipient["is_active"]:
            raise RecipientInactiveError(
                f"Recipient '{recipient['recipient_name']}' is inactive and cannot generate tokens"
            )

        if require_authorized_shares:
            auth_service = AuthorizationService()
            shares = auth_service.get_recipient_shares(recipient_id)
            if not shares:
                raise NoSharesAssignedError(
                    f"Recipient '{recipient['recipient_name']}' has no authorized shares"
                )

        max_tokens = self.config.token.max_tokens_per_recipient
        active_count = self.count_active_tokens(recipient_id)
        if active_count >= max_tokens:
            raise TokenQuotaExceededError(
                f"Maximum tokens ({max_tokens}) exceeded for recipient '{recipient['recipient_name']}'",
                max_tokens=max_tokens,
            )

        return self._create_token(recipient_id, expiration_hours)

    def _create_token(
        self, recipient_id: str, expiration_hours: int = None
    ) -> Dict[str, Any]:
        """内部方法：创建 token 并构建 Profile 数据。

        委托 TokenRepository 执行 token 创建和持久化。
        Profile 数据由本方法构建（不持久化），通过 API 响应即时交付给调用者。

        Args:
            recipient_id: Recipient UUID。
            expiration_hours: 过期小时数，如果为 None 则使用配置默认值。

        Returns:
            包含 token、token_prefix、expires_at、profile_data 的字典。
            token 明文仅在此返回一次，调用者应通过 API 响应传递给最终用户。
        """
        exp_hours = (
            expiration_hours
            if expiration_hours is not None
            else self.config.token.expiration_hours
        )

        token_data = self.token_repo.create(recipient_id, exp_hours)

        # 构建 Profile JSON 数据（不持久化，由 API 响应即时返回）
        endpoint = self.config.profile.endpoint
        expiration_time = None
        if token_data["expires_at"]:
            expiration_time = ts_to_datetime(token_data["expires_at"]).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        profile_data = {
            "shareCredentialsVersion": 1,
            "endpoint": endpoint,
            "bearerToken": token_data["token"],
        }
        if expiration_time:
            profile_data["expirationTime"] = expiration_time

        return {
            "token": token_data["token"],
            "token_prefix": token_data["token_prefix"],
            "expires_at": token_data["expires_at"],
            "profile_data": profile_data,
        }

    def list_recipient_tokens(
        self, recipient_id: str, include_expired: bool = False
    ) -> List[Dict[str, Any]]:
        """列出 recipient 的所有 token。

        Args:
            recipient_id: Recipient UUID。
            include_expired: 是否包含已过期的 token。

        Returns:
            token 列表，每项包含 token_prefix、created_at、expires_at、
            is_revoked 等字段（不含 token 明文）。
        """
        return self.token_repo.list_by_recipient(recipient_id, include_expired)

    def get_valid_token(self, recipient_id: str) -> Dict[str, Any] | None:
        """获取 recipient 的一个有效 token 的信息。

        由于 token 在数据库中以 SHA-256 哈希值存储，无法返回明文。
        返回 token 的哈希值和元数据。

        Args:
            recipient_id: Recipient UUID。

        Returns:
            包含 token_hash、expires_at 的字典，
            如果不存在有效 token 则返回 None。
        """
        return self.token_repo.get_valid_by_recipient(recipient_id)
