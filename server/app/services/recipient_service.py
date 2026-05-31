"""
Recipient 服务模块

该模块提供 Recipient 实体的完整生命周期管理功能，包括：
- 创建、查询、更新、物理删除 recipient
- Recipient 状态管理（激活/禁用）

RecipientService 是纯业务逻辑层，所有数据访问委托 RecipientRepository 执行，
不再直接操作 SQL/cursor/connection。

Recipient 是 Delta Sharing 中的数据消费方实体，通过 bearer token 与之关联。
"""

from typing import Optional, Dict, Any

from app.repositories.recipient_repository import RecipientRepository
from app.utils.page_token_utils import encode_page_token, decode_page_token


class RecipientService:
    """Recipient 服务类

    提供 Recipient 实体的完整 CRUD 操作和状态管理功能。
    分页逻辑保留在 Service 层，Repository 仅返回全量按名称排序的数据。

    Attributes:
        recipient_repo: RecipientRepository 实例。
    """

    def __init__(self):
        """初始化 Recipient 服务。"""
        self.recipient_repo = RecipientRepository()

    # ------------------------------------------------------------------
    # Recipient CRUD 操作
    # ------------------------------------------------------------------

    def create_recipient(
        self, name: str, comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建新的 Recipient。

        委托 RecipientRepository.create() 执行数据库写入。
        Repository 内部处理 UUID 生成和时间戳。

        Args:
            name: Recipient 名称（全局唯一）。
            comment: 描述说明（可选）。

        Returns:
            创建的 Recipient 字典，包含 id、name、comment、created_at、updated_at、is_active。

        Raises:
            ValueError: 如果名称已存在。
        """
        return self.recipient_repo.create(name, comment)

    def get_recipient_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取 Recipient。

        Args:
            name: Recipient 名称。

        Returns:
            Recipient 字典，如果不存在则返回 None。
        """
        return self.recipient_repo.find_by_name(name)

    def get_recipient_by_id(self, recipient_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取 Recipient。

        Args:
            recipient_id: Recipient UUID。

        Returns:
            Recipient 字典，如果不存在则返回 None。
        """
        return self.recipient_repo.find_by_id(recipient_id)

    def list_recipients(
        self, max_results: Optional[int] = None, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """列出所有 Recipient，支持分页。

        Repository 返回全量按名称排序的数据，Service 层负责应用分页逻辑。
        分页使用 Base64 编码的 offset 令牌机制。

        Args:
            max_results: 最大返回数量。
            page_token: 分页令牌。

        Returns:
            包含 items 和 next_page_token 的字典。
        """
        all_recipients = self.recipient_repo.list_all()

        offset = 0
        if page_token:
            decoded_offset = decode_page_token(page_token)
            offset = decoded_offset if decoded_offset is not None else 0

        recipients_subset = all_recipients[offset:]
        next_token = None

        if max_results and max_results > 0:
            recipients_subset = all_recipients[offset : offset + max_results]
            if offset + max_results < len(all_recipients):
                next_offset = offset + max_results
                next_token = encode_page_token(next_offset)

        return {"items": recipients_subset, "next_page_token": next_token}

    def update_recipient(
        self,
        name: str,
        new_name: Optional[str] = None,
        comment: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新 Recipient。

        委托 RecipientRepository.update() 执行动态 UPDATE。
        Repository 内部处理名称唯一性检查和 updated_at 时间戳更新。

        Args:
            name: Recipient 当前名称。
            new_name: 新名称（可选）。
            comment: 新描述（可选）。
            is_active: 激活状态（可选）。

        Returns:
            更新后的 Recipient 字典，如果不存在则返回 None。

        Raises:
            ValueError: 如果新名称已存在。
        """
        return self.recipient_repo.update(name, new_name, comment, is_active)

    def delete_recipient(self, name: str) -> bool:
        """物理删除 Recipient（级联删除关联数据）。

        委托 RecipientRepository.delete() 执行级联删除。
        删除范围：bearer_tokens → recipient_shares → recipients。

        Args:
            name: Recipient 名称。

        Returns:
            如果成功删除返回 True，如果不存在返回 False。
        """
        return self.recipient_repo.delete(name)

    def activate_recipient(self, name: str) -> Optional[Dict[str, Any]]:
        """激活 Recipient（设置 is_active = True）。

        委托 update_recipient() 执行，内部通过 Repository.update() 处理。

        Args:
            name: Recipient 名称。

        Returns:
            更新后的 Recipient 字典，如果不存在则返回 None。
        """
        return self.update_recipient(name, is_active=True)
