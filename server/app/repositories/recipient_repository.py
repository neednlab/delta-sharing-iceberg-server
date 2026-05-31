"""
Recipient Repository 模块

该模块提供 Recipient 实体的数据库 CRUD 操作。
封装所有 recipients 表相关的数据库操作。

Repository 职责:
- create: 创建新 Recipient 并持久化到 recipients 表
- find_by_name: 按 recipient_name 精确查询
- find_by_id: 按 recipient_id (UUID) 精确查询
- list_all: 返回所有记录，按 recipient_name ASC 排序
- update: 动态 UPDATE，仅更新非 None 字段
- delete: 级联删除 recipients + bearer_tokens + recipient_shares
- exists_by_name: 轻量检查名称是否存在

与 RecipientService 解耦，遵循现有 Repository 模式（ShareRepository/TokenRepository 风格）。
"""

import uuid
from typing import Dict, List, Optional, Any

from sqlalchemy import select, Connection
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.database import get_database, recipients, bearer_tokens, recipient_shares
from app.core.errors import DeltaSharingError, ErrorCode
from app.utils.time_utils import now_ts


class RecipientRepository:
    """Recipient Repository 类

    封装所有 recipients 表的数据库操作。
    使用 SQLAlchemy Core API 执行数据库操作，
    通过 Engine 上下文管理器管理事务边界。

    Attributes:
        _db: Database 单例实例。
    """

    def __init__(self):
        """初始化 RecipientRepository。"""
        self._db = get_database()
        self._r = recipients
        self._bt = bearer_tokens
        self._rs = recipient_shares

    # ------------------------------------------------------------------
    # 私有辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _get_recipient_id(conn: Connection, name: str) -> Optional[str]:
        """根据 recipient_name 查找 recipient_id。

        该方法供内部 delete/update 等需要 name→id 转换的操作用。

        Args:
            conn: SQLAlchemy Connection 对象。
            name: Recipient 名称（精确匹配）。

        Returns:
            recipient_id 字符串，未找到返回 None。
        """
        r = recipients
        result = conn.execute(
            r.select().with_only_columns(r.c.recipient_id).where(r.c.recipient_name == name)
        )
        row = result.fetchone()
        return row.recipient_id if row else None

    @staticmethod
    def _get_recipient_id_excluding(
        conn: Connection, name: str, exclude_name: str
    ) -> Optional[str]:
        """检查除了指定名称外另一名称是否存在。

        供 update 方法中的名称唯一性检查使用。

        Args:
            conn: SQLAlchemy Connection 对象。
            name: 待检查的 Recipient 名称。
            exclude_name: 排除的 Recipient 名称（当前名称）。

        Returns:
            如果存在则返回 recipient_id，否则返回 None。
        """
        r = recipients
        result = conn.execute(
            r.select()
            .with_only_columns(r.c.recipient_id)
            .where(r.c.recipient_name == name, r.c.recipient_name != exclude_name)
        )
        row = result.fetchone()
        return row.recipient_id if row else None

    @staticmethod
    def _row_to_recipient_dict(row) -> Dict[str, Any]:
        """将 recipients 表行数据转换为字典。

        Args:
            row: SQLAlchemy Row 对象，包含 recipients 表的所有列。

        Returns:
            标准化的 Recipient 字典。
        """
        return {
            "recipient_id": row.recipient_id,
            "recipient_name": row.recipient_name,
            "comment": row.comment,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "is_active": bool(row.is_active),
        }

    # ------------------------------------------------------------------
    # 公共方法：创建
    # ------------------------------------------------------------------

    def create(self, name: str, comment: Optional[str] = None) -> Dict[str, Any]:
        """创建新的 Recipient。

        使用 uuid.uuid4() 生成 recipient_id，默认 is_active=1。
        created_at 和 updated_at 由 Repository 内部通过 now_ts() 生成。

        Args:
            name: Recipient 名称（全局唯一）。
            comment: 描述说明（可选）。

        Returns:
            创建的 Recipient 字典，包含 recipient_id、recipient_name、
            comment、created_at、updated_at、is_active。

        Raises:
            DeltaSharingError: 如果名称已存在 (RECIPIENT_ALREADY_EXISTS)。
        """
        r = self._r
        recipient_id = str(uuid.uuid4())
        current_ts = now_ts()

        with self._db.get_engine().begin() as conn:
            if self._get_recipient_id(conn, name):
                raise DeltaSharingError(
                    ErrorCode.RECIPIENT_ALREADY_EXISTS,
                    f"Recipient with name '{name}' already exists",
                    status_code=409,
                )

            try:
                conn.execute(
                    r.insert().values(
                        recipient_id=recipient_id,
                        recipient_name=name,
                        comment=comment,
                        created_at=current_ts,
                        updated_at=current_ts,
                        is_active=1,
                    )
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.RECIPIENT_ALREADY_EXISTS,
                    f"Recipient with name '{name}' already exists",
                    status_code=409,
                    details={"db_error": str(e.orig) if e.orig else str(e)},
                )
            except OperationalError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    "Database operation failed",
                    status_code=500,
                    details={"db_error": str(e)},
                )

        return {
            "recipient_id": recipient_id,
            "recipient_name": name,
            "comment": comment,
            "created_at": current_ts,
            "updated_at": current_ts,
            "is_active": True,
        }

    # ------------------------------------------------------------------
    # 公共方法：查询
    # ------------------------------------------------------------------

    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """按 recipient_name 精确查询。

        Args:
            name: Recipient 名称。

        Returns:
            Recipient 字典，如果不存在则返回 None。
        """
        r = self._r
        with self._db.get_engine().connect() as conn:
            result = conn.execute(r.select().where(r.c.recipient_name == name))
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_recipient_dict(row)

    def find_by_id(self, recipient_id: str) -> Optional[Dict[str, Any]]:
        """按 recipient_id (UUID) 精确查询。

        Args:
            recipient_id: Recipient UUID。

        Returns:
            Recipient 字典，如果不存在则返回 None。
        """
        r = self._r
        with self._db.get_engine().connect() as conn:
            result = conn.execute(r.select().where(r.c.recipient_id == recipient_id))
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_recipient_dict(row)

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有 Recipient 记录。

        按 recipient_name ASC 排序。分页逻辑保留在 Service 层处理，
        与 ShareService 从 config 读取全量数据再分页的模式一致。

        Returns:
            Recipient 字典列表。
        """
        r = self._r
        with self._db.get_engine().connect() as conn:
            result = conn.execute(r.select().order_by(r.c.recipient_name.asc()))
            return [self._row_to_recipient_dict(row) for row in result.fetchall()]

    def exists_by_name(self, name: str) -> bool:
        """轻量检查名称是否已存在。

        使用 SELECT 而非 SELECT * 以最小化 I/O 开销。
        供 Service 层在 create 前进行名称唯一性检查使用。

        Args:
            name: Recipient 名称。

        Returns:
            如果名称已存在返回 True，否则返回 False。
        """
        r = self._r
        with self._db.get_engine().connect() as conn:
            result = conn.execute(r.select().where(r.c.recipient_name == name))
            return result.fetchone() is not None

    # ------------------------------------------------------------------
    # 公共方法：更新
    # ------------------------------------------------------------------

    def update(
        self,
        name: str,
        new_name: Optional[str] = None,
        comment: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """动态更新 Recipient。

        仅更新传入的非 None 字段，updated_at 由 Repository 内部自动设置。

        Args:
            name: Recipient 当前名称。
            new_name: 新名称（可选）。
            comment: 新描述（可选）。
            is_active: 激活状态（可选）。

        Returns:
            更新后的 Recipient 字典，如果不存在则返回 None。

        Raises:
            DeltaSharingError: 如果新名称已存在 (RECIPIENT_ALREADY_EXISTS)。
        """
        r = self._r

        with self._db.get_engine().begin() as conn:
            if not self._get_recipient_id(conn, name):
                return None

            if new_name and new_name != name:
                if self._get_recipient_id_excluding(conn, new_name, name):
                    raise DeltaSharingError(
                        ErrorCode.RECIPIENT_ALREADY_EXISTS,
                        f"Recipient with name '{new_name}' already exists",
                        status_code=409,
                    )

            current_ts = now_ts()
            update_values = {"updated_at": current_ts}

            if new_name:
                update_values["recipient_name"] = new_name
            if comment is not None:
                update_values["comment"] = comment
            if is_active is not None:
                update_values["is_active"] = 1 if is_active else 0

            conn.execute(r.update().values(**update_values).where(r.c.recipient_name == name))

        final_name = new_name if new_name else name
        return self.find_by_name(final_name)

    # ------------------------------------------------------------------
    # 公共方法：删除
    # ------------------------------------------------------------------

    def delete(self, name: str) -> bool:
        """物理删除 Recipient（级联删除关联数据）。

        级联删除范围与 RecipientService.delete_recipient() 保持一致：
        bearer_tokens → recipient_shares → recipients。

        Args:
            name: Recipient 名称。

        Returns:
            如果成功删除返回 True，如果不存在返回 False。
        """
        r = self._r
        bt = self._bt
        rs = self._rs

        with self._db.get_engine().begin() as conn:
            if not self._get_recipient_id(conn, name):
                return False

            # 使用子查询获取 recipient_id，确保级联删除一致性
            rid_subq = select(r.c.recipient_id).where(r.c.recipient_name == name).scalar_subquery()

            conn.execute(bt.delete().where(bt.c.recipient_id == rid_subq))
            conn.execute(rs.delete().where(rs.c.recipient_id == rid_subq))
            conn.execute(r.delete().where(r.c.recipient_name == name))

        return True
