"""
Admin User Repository 模块

该模块提供 Admin User 实体的数据库 CRUD 操作。
封装所有 admin_users 表相关的数据库操作。

Repository 职责:
- find_by_username: 按 username 精确查询管理员用户
- find_by_id: 按 admin_id (UUID) 精确查询
- create: 创建新管理员用户（含 bcrypt 密码哈希）
- update_password: 更新管理员密码
"""

from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import get_database, admin_users
from app.core.errors import DeltaSharingError, ErrorCode
from app.core.security import hash_password
from app.utils.time_utils import now_ts


class AdminUserRepository:
    """Admin User Repository 类

    封装所有 admin_users 表的数据库操作。
    使用 SQLAlchemy Core API 执行数据库操作。

    Attributes:
        _db: Database 单例实例。
    """

    def __init__(self):
        """初始化 AdminUserRepository。"""
        self._db = get_database()
        self._table = admin_users

    def find_by_username(self, username: str) -> Optional[Dict]:
        """按用户名精确查询管理员用户。

        Args:
            username: 管理员用户名（区分大小写）。

        Returns:
            包含管理员用户完整信息的字典，未找到返回 None。
            返回字典键：admin_id, username, password_hash, display_name,
            is_active, created_at, updated_at
        """
        with self._db.get_engine().connect() as conn:
            stmt = select(self._table).where(
                self._table.c.username == username
            )
            result = conn.execute(stmt).fetchone()
            if result is None:
                return None
            return dict(result._mapping)

    def find_by_id(self, admin_id: str) -> Optional[Dict]:
        """按管理员 ID 精确查询。

        Args:
            admin_id: 管理员 UUID。

        Returns:
            包含管理员用户完整信息的字典，未找到返回 None。
        """
        with self._db.get_engine().connect() as conn:
            stmt = select(self._table).where(
                self._table.c.admin_id == admin_id
            )
            result = conn.execute(stmt).fetchone()
            if result is None:
                return None
            return dict(result._mapping)

    def create(
        self,
        username: str,
        plain_password: str,
        display_name: str = "",
    ) -> Dict:
        """创建新管理员用户。

        对明文密码进行 bcrypt 哈希后存储。
        如果用户名已存在则抛出重复错误。

        Args:
            username: 管理员用户名（唯一）。
            plain_password: 明文密码，将在存储前进行 bcrypt 哈希。
            display_name: 显示名称，默认为空字符串。

        Returns:
            新创建的管理员用户字典。

        Raises:
            DeltaSharingError: 用户名已存在时抛出 DUPLICATE_RECIPIENT 错误。
        """
        import uuid

        admin_id = str(uuid.uuid4())
        password_hash_val = hash_password(plain_password)
        ts = now_ts()

        with self._db.get_engine().begin() as conn:
            try:
                conn.execute(
                    self._table.insert().values(
                        admin_id=admin_id,
                        username=username,
                        password_hash=password_hash_val,
                        display_name=display_name,
                        is_active=1,
                        created_at=ts,
                        updated_at=ts,
                    )
                )
            except IntegrityError:
                raise DeltaSharingError(
                    ErrorCode.DUPLICATE_RECIPIENT,
                    f"Admin user '{username}' already exists",
                )

        return {
            "admin_id": admin_id,
            "username": username,
            "display_name": display_name,
            "is_active": 1,
            "created_at": ts,
            "updated_at": ts,
        }

    def update_password(self, username: str, new_plain_password: str) -> bool:
        """更新管理员密码。

        找到指定用户后，使用 bcrypt 哈希新密码并更新。

        Args:
            username: 管理员用户名。
            new_plain_password: 新的明文密码。

        Returns:
            更新成功返回 True，用户不存在返回 False。
        """
        user = self.find_by_username(username)
        if user is None:
            return False

        new_hash = hash_password(new_plain_password)
        ts = now_ts()

        with self._db.get_engine().begin() as conn:
            conn.execute(
                self._table.update()
                .where(self._table.c.admin_id == user["admin_id"])
                .values(password_hash=new_hash, updated_at=ts)
            )

        return True
