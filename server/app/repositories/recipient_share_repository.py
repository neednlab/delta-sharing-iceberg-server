"""
RecipientShare Repository 模块

该模块提供 Recipient-Share 授权关系的数据库 CRUD 操作。
封装所有 recipient_shares 表相关的数据库操作。

Repository 职责:
- grant: 向 recipient_shares 表插入授权记录
- revoke: 从 recipient_shares 表删除授权记录
- exists: 检查授权关系是否已存在
- list_by_recipient: JOIN shares 表列出 recipient 的所有授权（含 share_name）
- list_share_names: JOIN shares 表仅返回 share_name 字符串列表
- check_access: 使用 SELECT 轻量检查授权记录

与 AuthorizationService 解耦，遵循现有 Repository 模式（ShareRepository/TokenRepository 风格）。
"""

import uuid
from typing import Dict, List, Optional, Any

from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.database import get_database, recipient_shares, shares
from app.core.errors import DeltaSharingError, ErrorCode
from app.utils.time_utils import now_ts


class RecipientShareRepository:
    """RecipientShare Repository 类

    封装所有 recipient_shares 表的数据库操作。
    使用 SQLAlchemy Core API 执行数据库操作，
    通过 Engine 上下文管理器管理事务边界。

    Attributes:
        _db: Database 单例实例。
    """

    def __init__(self):
        """初始化 RecipientShareRepository。"""
        self._db = get_database()
        self._rs = recipient_shares
        self._sh = shares

    # ------------------------------------------------------------------
    # 公共方法：授权管理
    # ------------------------------------------------------------------

    def grant(
        self, recipient_id: str, share_id: str, granted_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """向 recipient_shares 表插入授权记录。

        granted_at 时间戳由 Repository 内部通过 now_ts() 生成，
        调用方无需传入时间戳参数。
        使用 UUID 作为主键替代原先的 last_insert_rowid()。

        Args:
            recipient_id: Recipient UUID。
            share_id: Share UUID。
            granted_by: 授权人名称（可选）。

        Returns:
            包含 id、recipient_id、share_id、granted_at、granted_by 的字典。
        """
        current_ts = now_ts()
        auth_id = str(uuid.uuid4())

        rs = self._rs
        with self._db.get_engine().begin() as conn:
            try:
                conn.execute(
                    rs.insert().values(
                        id=auth_id,
                        recipient_id=recipient_id,
                        share_id=share_id,
                        granted_at=current_ts,
                        granted_by=granted_by,
                    )
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.AUTHORIZATION_ALREADY_EXISTS,
                    "Authorization already exists",
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
            "id": auth_id,
            "recipient_id": recipient_id,
            "share_id": share_id,
            "granted_at": current_ts,
            "granted_by": granted_by,
        }

    def revoke(self, recipient_id: str, share_id: str) -> bool:
        """从 recipient_shares 表删除匹配的授权记录。

        仅删除 recipient_id 和 share_id 精确匹配的记录。
        不会验证授权记录是否存在，由 Service 层负责存在性检查。

        Args:
            recipient_id: Recipient UUID。
            share_id: Share UUID。

        Returns:
            如果删除成功（影响了行）返回 True，否则返回 False。
        """
        rs = self._rs
        with self._db.get_engine().begin() as conn:
            result = conn.execute(
                rs.delete().where(
                    rs.c.recipient_id == recipient_id,
                    rs.c.share_id == share_id,
                )
            )
            return result.rowcount > 0

    # ------------------------------------------------------------------
    # 公共方法：存在性检查
    # ------------------------------------------------------------------

    def exists(self, recipient_id: str, share_id: str) -> bool:
        """轻量检查授权关系是否已存在。

        使用 SELECT 而非 SELECT * 以最小化 I/O 开销。
        该方法供 Service 层在 grant 前进行重复授权检查使用。

        Args:
            recipient_id: Recipient UUID。
            share_id: Share UUID。

        Returns:
            如果授权记录已存在返回 True，否则返回 False。
        """
        rs = self._rs
        with self._db.get_engine().connect() as conn:
            result = conn.execute(
                rs.select().where(
                    rs.c.recipient_id == recipient_id,
                    rs.c.share_id == share_id,
                )
            )
            return result.fetchone() is not None

    def check_access(self, recipient_id: str, share_id: str) -> bool:
        """使用 SELECT 轻量检查 recipient 是否有权访问特定 share。

        与 exists() 语义相同，命名区分用于不同的业务场景：
        - exists()：创建授权前的重复检查
        - check_access()：数据面访问时的权限验证

        Args:
            recipient_id: Recipient UUID。
            share_id: Share UUID。

        Returns:
            如果有权访问返回 True，否则返回 False。
        """
        rs = self._rs
        with self._db.get_engine().connect() as conn:
            result = conn.execute(
                rs.select().where(
                    rs.c.recipient_id == recipient_id,
                    rs.c.share_id == share_id,
                )
            )
            return result.fetchone() is not None

    # ------------------------------------------------------------------
    # 公共方法：合并查询（share 存在性 + 授权验证）
    # ------------------------------------------------------------------

    def check_access_with_share_validation(
        self, share_name: str, recipient_id: str
    ) -> Optional[Dict[str, Any]]:
        """使用 outerjoin 合并 share 存在性验证和授权检查为单次 SQL 查询。

        使用 SQLAlchemy Core outerjoin 将 shares 表和 recipient_shares 表
        合并为单次查询，同时返回 share_id 和授权状态。
        替代原先 share_exists() + check_share_access() 两次独立查询。

        Args:
            share_name: Share 名称。
            recipient_id: Recipient UUID。

        Returns:
            如果 share 存在，返回 {"share_id": "<uuid>", "authorized": True/False}。
            如果 share 不存在，返回 None。
        """
        rs = self._rs
        sh = self._sh

        j = sh.outerjoin(
            rs,
            and_(
                sh.c.share_id == rs.c.share_id,
                rs.c.recipient_id == recipient_id,
            ),
        )

        with self._db.get_engine().connect() as conn:
            result = conn.execute(
                sh.select()
                .with_only_columns(
                    sh.c.share_id,
                    rs.c.id.label("auth_id"),
                )
                .select_from(j)
                .where(sh.c.share_name == share_name.lower())
            )
            row = result.fetchone()
            if row is None:
                return None
            return {
                "share_id": row.share_id,
                "authorized": row.auth_id is not None,
            }

    # ------------------------------------------------------------------
    # 公共方法：授权列表查询
    # ------------------------------------------------------------------

    def list_by_recipient(self, recipient_id: str) -> List[Dict[str, Any]]:
        """列出指定 recipient 的所有授权记录。

        JOIN shares 表获取 share_name，按 granted_at DESC 排序，
        最近授权的记录排在前面。

        Args:
            recipient_id: Recipient UUID。

        Returns:
            授权记录列表，每项包含 id、recipient_id、share_id、share_name、
            granted_at、granted_by 字段。
        """
        rs = self._rs
        sh = self._sh

        with self._db.get_engine().connect() as conn:
            j = rs.join(sh, rs.c.share_id == sh.c.share_id)
            result = conn.execute(
                rs.select()
                .with_only_columns(
                    rs.c.id,
                    rs.c.recipient_id,
                    rs.c.share_id,
                    sh.c.share_name,
                    rs.c.granted_at,
                    rs.c.granted_by,
                )
                .select_from(j)
                .where(rs.c.recipient_id == recipient_id)
                .order_by(rs.c.granted_at.desc())
            )

            results = []
            for row in result.fetchall():
                results.append(
                    {
                        "id": row.id,
                        "recipient_id": row.recipient_id,
                        "share_id": row.share_id,
                        "share_name": row.share_name,
                        "granted_at": row.granted_at,
                        "granted_by": row.granted_by,
                    }
                )
            return results

    def list_share_names(self, recipient_id: str) -> List[str]:
        """获取 recipient 有权访问的所有 share 名称列表。

        JOIN shares 表获取 share_name，仅返回字符串列表而非完整授权记录。
        供数据面 API 使用，快速构建 authorized_shares 过滤列表。

        Args:
            recipient_id: Recipient UUID。

        Returns:
            share 名称字符串列表。
        """
        rs = self._rs
        sh = self._sh

        with self._db.get_engine().connect() as conn:
            j = rs.join(sh, rs.c.share_id == sh.c.share_id)
            result = conn.execute(
                sh.select()
                .with_only_columns(sh.c.share_name)
                .select_from(j)
                .where(rs.c.recipient_id == recipient_id)
            )

            return [row.share_name for row in result.fetchall()]
