"""
Token Repository 模块

该模块提供 Bearer Token 的数据库 CRUD 操作。
封装所有 bearer_tokens、token_revocation 表的数据库操作。

Repository 职责:
- create: 创建新 Token 并持久化到 bearer_tokens 表
- find_by_hash: 按 SHA-256 哈希值查找 Token（只查不判断过期/撤销）
- revoke: 撤销 Token 并写入 token_revocation 表
- is_revoked: 检查 Token 是否已被撤销
- count_active: 统计有效 Token 数量
- list_by_recipient: 列出 Recipient 的所有 Token
- get_valid_by_recipient: 获取 Recipient 的有效 Token
"""

import hashlib
import secrets
from typing import Dict, List, Optional, Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.database import get_database, bearer_tokens, token_revocation
from app.core.errors import DeltaSharingError, ErrorCode
from app.utils.time_utils import now_ts


class TokenRepository:
    """Token Repository 类

    封装所有 Bearer Token 的数据库操作。
    使用 SQLAlchemy Core API 执行数据库操作，
    通过 Engine 上下文管理器管理事务边界。
    Token 以 SHA-256 哈希值存储，明文仅在创建时返回一次。
    """

    def __init__(self):
        """初始化 TokenRepository。"""
        self._db = get_database()
        self._bt = bearer_tokens
        self._tr = token_revocation

    # ------------------------------------------------------------------
    # 公共方法：创建 Token
    # ------------------------------------------------------------------

    def create(self, recipient_id: str, expiration_hours: int = None) -> Dict[str, Any]:
        """创建新的 Bearer Token。

        Token 生成后以 SHA-256 哈希值存储，明文仅在返回值中出现一次。
        服务端不持久化 Profile 内容，Profile 由调用方通过 API 响应即时获取。

        Args:
            recipient_id: 接收者 ID。
            expiration_hours: 过期小时数，如果为 None 则使用配置默认值。

        Returns:
            包含 token（明文，仅此一次）、token_prefix、expires_at 的字典。
        """
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        token_prefix = token[:8]
        now_ts_val = now_ts()
        expires_at = now_ts_val + expiration_hours * 3600 if expiration_hours else None

        bt = self._bt
        with self._db.get_engine().begin() as conn:
            try:
                conn.execute(
                    bt.insert().values(
                        token_hash=token_hash,
                        token_prefix=token_prefix,
                        recipient_id=recipient_id,
                        created_at=now_ts_val,
                        expires_at=expires_at,
                    )
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    "Failed to create token due to database integrity error",
                    status_code=500,
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
            "token": token,
            "token_prefix": token_prefix,
            "expires_at": expires_at,
        }

    # ------------------------------------------------------------------
    # 公共方法：查询 Token
    # ------------------------------------------------------------------

    def find_by_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """按 SHA-256 哈希值查找 Token 记录。

        只执行数据库查询，不判断过期/撤销状态，由 Service 层处理业务逻辑。

        Args:
            token_hash: Token 的 SHA-256 哈希值。

        Returns:
            包含 recipient_id、expires_at、is_revoked 的字典，
            如果未找到则返回 None。
        """
        bt = self._bt
        with self._db.get_engine().connect() as conn:
            result = conn.execute(bt.select().where(bt.c.token_hash == token_hash))
            row = result.fetchone()
            if not row:
                return None

            return {
                "recipient_id": row.recipient_id,
                "expires_at": row.expires_at,
                "is_revoked": bool(row.is_revoked),
            }

    # ------------------------------------------------------------------
    # 公共方法：撤销 Token
    # ------------------------------------------------------------------

    def revoke(self, token_hash: str, reason: str = None) -> bool:
        """撤销指定 Token（通过 token_hash）。

        撤销时向 token_revocation 表写入撤销记录。
        token_revocation 表的插入使用 SQLite 方言的 OR IGNORE 前缀以确保幂等性。

        Args:
            token_hash: Token 的 SHA-256 哈希值。
            reason: 撤销原因（可选）。

        Returns:
            如果成功撤销返回 True，否则返回 False。
        """
        bt = self._bt
        tr = self._tr
        now_ts_val = now_ts()

        with self._db.get_engine().begin() as conn:
            result = conn.execute(
                bt.update()
                .values(is_revoked=1, revoked_at=now_ts_val)
                .where(bt.c.token_hash == token_hash)
            )

            if result.rowcount > 0:
                # 使用 OR IGNORE 前缀确保 token_revocation 插入幂等性
                conn.execute(
                    tr.insert()
                    .prefix_with("OR IGNORE", dialect="sqlite")
                    .values(
                        token_hash=token_hash,
                        revoked_at=now_ts_val,
                        reason=reason,
                    )
                )
                return True
        return False

    # ------------------------------------------------------------------
    # 公共方法：检查撤销状态
    # ------------------------------------------------------------------

    def is_revoked(self, token_hash: str) -> bool:
        """检查 Token 是否在撤销表中。

        Args:
            token_hash: Token 的 SHA-256 哈希值。

        Returns:
            如果已撤销返回 True，否则返回 False。
        """
        tr = self._tr
        with self._db.get_engine().connect() as conn:
            result = conn.execute(tr.select().where(tr.c.token_hash == token_hash))
            return result.fetchone() is not None

    # ------------------------------------------------------------------
    # 公共方法：统计有效 Token 数量
    # ------------------------------------------------------------------

    def count_active(self, recipient_id: str) -> int:
        """统计指定 Recipient 的有效 Token 数量。

        有效 Token 定义为：is_revoked=0 且未过期。

        Args:
            recipient_id: Recipient UUID。

        Returns:
            有效 Token 数量。
        """
        current_ts = now_ts()
        bt = self._bt

        with self._db.get_engine().connect() as conn:
            result = conn.execute(
                bt.select()
                .with_only_columns(func.count().label("count"))
                .where(
                    bt.c.recipient_id == recipient_id,
                    bt.c.is_revoked == 0,
                    (bt.c.expires_at == None) | (bt.c.expires_at > current_ts),  # noqa: E711
                )
            )
            row = result.fetchone()
            return row.count if row else 0

    # ------------------------------------------------------------------
    # 公共方法：列出 Recipient 的 Token
    # ------------------------------------------------------------------

    def list_by_recipient(
        self, recipient_id: str, include_expired: bool = False
    ) -> List[Dict[str, Any]]:
        """列出指定 Recipient 的所有 Token 元数据。

        Args:
            recipient_id: Recipient UUID。
            include_expired: 是否包含已过期的 token，默认 False 仅返回有效 token。

        Returns:
            token 列表，每项包含 token_hash、token_prefix、recipient_id、
            created_at、expires_at、is_revoked、revoked_at。
        """
        bt = self._bt

        with self._db.get_engine().connect() as conn:
            query = bt.select().where(bt.c.recipient_id == recipient_id)

            if not include_expired:
                current_ts = now_ts()
                query = query.where(
                    bt.c.is_revoked == 0,
                    (bt.c.expires_at == None) | (bt.c.expires_at > current_ts),  # noqa: E711
                )

            query = query.order_by(bt.c.created_at.desc())
            result = conn.execute(query)

            results = []
            for row in result.fetchall():
                results.append(
                    {
                        "token_hash": row.token_hash,
                        "token_prefix": row.token_prefix,
                        "recipient_id": row.recipient_id,
                        "created_at": row.created_at,
                        "expires_at": row.expires_at,
                        "is_revoked": bool(row.is_revoked),
                        "revoked_at": row.revoked_at,
                    }
                )
            return results

    # ------------------------------------------------------------------
    # 公共方法：获取 Recipient 的有效 Token
    # ------------------------------------------------------------------

    def get_valid_by_recipient(self, recipient_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 Recipient 的最新一个有效 Token 信息。

        Args:
            recipient_id: Recipient UUID。

        Returns:
            包含 token_hash、expires_at 的字典，
            如果不存在有效 token 则返回 None。
        """
        bt = self._bt
        current_ts = now_ts()

        with self._db.get_engine().connect() as conn:
            result = conn.execute(
                bt.select()
                .where(
                    bt.c.recipient_id == recipient_id,
                    bt.c.is_revoked == 0,
                    (bt.c.expires_at == None) | (bt.c.expires_at > current_ts),  # noqa: E711
                )
                .order_by(bt.c.created_at.desc())
                .limit(1)
            )
            row = result.fetchone()
            if row:
                return {
                    "token_hash": row.token_hash,
                    "expires_at": row.expires_at,
                }
            return None

    # ------------------------------------------------------------------
    # 公共方法：Profile 管理 - 已移除（Profile 不再持久化，由 API 响应即时交付）
    # ------------------------------------------------------------------
