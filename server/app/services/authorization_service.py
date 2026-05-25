"""
Authorization 授权服务模块

该模块提供 Recipient-Share 授权关系的管理功能，包括：
- 授权/撤销 share 给 recipient
- 查询 recipient 的授权列表
- 验证 recipient 是否有权访问特定 share

AuthorizationService 是纯业务逻辑层（验证 + 编排），所有数据访问委托
RecipientShareRepository 执行，不再直接操作 SQL/cursor/connection。

授权检查在 Delta Sharing 中是权限控制的核心，确保数据消费者只能访问被授权的共享资源。
"""

from typing import Optional, Dict, Any, List

from app.core.config import get_config, get_all_shares
from app.core.errors import DeltaSharingError, ErrorCode
from app.repositories.recipient_share_repository import RecipientShareRepository
from app.repositories.share_repository import ShareRepository


class AuthorizationService:
    """Authorization 授权服务类

    提供 Recipient-Share 授权关系的完整管理功能。
    所有数据访问委托 RecipientShareRepository 执行，Service 层仅负责
    业务验证（recipient 存在性、share 存在性、重复授权检查）和方法编排。

    Attributes:
        config: 全局配置实例。
        auth_repo: RecipientShareRepository 实例。
    """

    def __init__(self):
        """初始化 Authorization 服务。"""
        self.config = get_config()
        self.auth_repo = RecipientShareRepository()

    def _is_database_authorization_enabled(self) -> bool:
        """判断是否启用数据库级授权管理。

        从 shares 配置中读取 use_database 字段，统一处理类型兼容性。
        当 use_database 为 False 时跳过授权检查（允许访问所有 share）。

        Returns:
            如果启用数据库授权返回 True，否则返回 False。
        """
        shares_config = self.config.shares
        if isinstance(shares_config, type(get_config().shares)):
            return shares_config.use_database
        return getattr(shares_config, "use_database", False)

    def grant_share_to_recipient(
        self, recipient_name: str, share_name: str, granted_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """将 share 授权给 recipient。

        业务流程：
        1. 验证 recipient 存在
        2. 验证 share 存在
        3. 获取 share_id
        4. 检查是否已有重复授权
        5. 执行授权写入

        Args:
            recipient_name: Recipient 名称。
            share_name: Share 名称。
            granted_by: 授权人名称（可选）。

        Returns:
            授权记录字典，包含 id、recipient_id、share_name、granted_at、granted_by。

        Raises:
            DeltaSharingError: 如果 recipient 或 share 不存在，或已存在授权。
        """
        from app.services.recipient_service import RecipientService

        recipient_service = RecipientService()
        recipient = recipient_service.get_recipient_by_name(recipient_name)
        if not recipient:
            raise DeltaSharingError(
                ErrorCode.RECIPIENT_NOT_FOUND,
                f"Recipient '{recipient_name}' not found",
                status_code=404,
            )

        all_shares = get_all_shares()
        if share_name.lower() not in all_shares:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{share_name}' not found",
                status_code=404,
            )

        share_repo = ShareRepository()
        share_id = share_repo.get_share_id(share_name)
        if not share_id:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{share_name}' not found",
                status_code=404,
            )

        if self.auth_repo.exists(recipient["recipient_id"], share_id):
            raise DeltaSharingError(
                ErrorCode.AUTHORIZATION_ALREADY_EXISTS,
                f"Authorization already exists for recipient '{recipient_name}' and share '{share_name}'",
                status_code=409,
            )

        result = self.auth_repo.grant(recipient["recipient_id"], share_id, granted_by)
        result["share_name"] = share_name.lower()
        return result

    def revoke_share_from_recipient(self, recipient_name: str, share_name: str) -> bool:
        """撤销 recipient 对 share 的访问权限。

        业务流程：
        1. 验证 recipient 存在
        2. 获取 share_id（不存在则直接返回 False）
        3. 执行撤销

        Args:
            recipient_name: Recipient 名称。
            share_name: Share 名称。

        Returns:
            如果成功撤销返回 True，如果授权不存在返回 False。

        Raises:
            DeltaSharingError: 如果 recipient 不存在 (RECIPIENT_NOT_FOUND)。
        """
        from app.services.recipient_service import RecipientService

        recipient_service = RecipientService()
        recipient = recipient_service.get_recipient_by_name(recipient_name)
        if not recipient:
            raise DeltaSharingError(
                ErrorCode.RECIPIENT_NOT_FOUND,
                f"Recipient '{recipient_name}' not found",
                status_code=404,
            )

        share_repo = ShareRepository()
        share_id = share_repo.get_share_id(share_name)
        if not share_id:
            return False

        return self.auth_repo.revoke(recipient["recipient_id"], share_id)

    def list_recipient_shares(self, recipient_name: str) -> List[Dict[str, Any]]:
        """列出 recipient 被授权的所有 share。

        业务流程：
        1. 验证 recipient 存在
        2. 委托 Repository 查询授权列表

        Args:
            recipient_name: Recipient 名称。

        Returns:
            授权记录列表。

        Raises:
            DeltaSharingError: 如果 recipient 不存在 (RECIPIENT_NOT_FOUND)。
        """
        from app.services.recipient_service import RecipientService

        recipient_service = RecipientService()
        recipient = recipient_service.get_recipient_by_name(recipient_name)
        if not recipient:
            raise DeltaSharingError(
                ErrorCode.RECIPIENT_NOT_FOUND,
                f"Recipient '{recipient_name}' not found",
                status_code=404,
            )

        return self.auth_repo.list_by_recipient(recipient["recipient_id"])

    def check_share_access(self, recipient_id: str, share_name: str) -> bool:
        """检查 recipient 是否有权访问特定 share。

        当数据库授权未启用时，直接返回 True（允许访问所有 share）。
        启用时委托 Repository 进行轻量级 SELECT 1 查询。

        Args:
            recipient_id: Recipient UUID。
            share_name: Share 名称。

        Returns:
            如果有权访问返回 True，否则返回 False。
        """
        if not self._is_database_authorization_enabled():
            return True

        share_repo = ShareRepository()
        share_id = share_repo.get_share_id(share_name)
        if not share_id:
            return False

        return self.auth_repo.check_access(recipient_id, share_id)

    def get_recipient_shares(self, recipient_id: str) -> List[str]:
        """获取 recipient 有权访问的所有 share 名称列表。

        当数据库授权未启用时，返回所有 share 名称列表。
        启用时委托 Repository 查询并仅返回 share_name 字符串列表。

        Args:
            recipient_id: Recipient UUID。

        Returns:
            share 名称列表。
        """
        if not self._is_database_authorization_enabled():
            all_shares = get_all_shares()
            return list(all_shares.keys())

        return self.auth_repo.list_share_names(recipient_id)

    def get_authorized_shares_filter(self, recipient_id: str) -> List[str]:
        """获取 recipient 有权访问的 share 名称列表，用于过滤查询结果。

        纯透传方法，内部委托 get_recipient_shares() 处理数据库/配置双模式逻辑。

        Args:
            recipient_id: Recipient UUID。

        Returns:
            有权访问的 share 名称列表。
        """
        return self.get_recipient_shares(recipient_id)
