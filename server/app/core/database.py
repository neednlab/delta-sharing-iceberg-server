"""
数据库管理模块

该模块提供 Delta Sharing Server 的数据库管理功能，基于 SQLAlchemy Core 实现。
数据库用于存储以下 9 张业务表：
- shares: 共享资源定义
- shared_schemas: 共享 Schema 定义
- shared_tables: 共享 Table 定义
- recipients: 数据接收方
- recipient_shares: 接收方与 Share 的授权关系
- bearer_tokens: Bearer Token 认证凭证（token_hash 存储 SHA-256 哈希值，不持久化 Profile）
- token_revocation: Token 撤销记录（token_hash 存储 SHA-256 哈希值）
- snapshot_version: 快照版本追踪信息
- admin_users: 管理员用户表（username + bcrypt 密码哈希）

使用 SQLAlchemy Engine + MetaData + Table 管理数据库连接与表结构，
支持 SQLite 和 PostgreSQL 双向兼容。
使用单例模式确保全局只有一个数据库引擎实例。

业务数据访问已迁移至 Repository 层：
- Token 相关 → TokenRepository
- Version 相关 → VersionRepository
- Admin 用户相关 → AdminUserRepository
"""

import os
from typing import Optional

from sqlalchemy import (
    Engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Text,
    Index,
    UniqueConstraint,
    ForeignKeyConstraint,
    create_engine,
    event,
    text,
)
from sqlalchemy.pool import NullPool, QueuePool
from loguru import logger

from app.core.config import get_config


# 定义 MetaData 实例，用于注册所有表定义
_metadata = MetaData()

# ------------------------------------------------------------------
# 9 张业务表的 Table 对象定义
# 时间戳列 (created_at, updated_at, granted_at, revoked_at) 不设置
# server_default，由 Repository 层通过 now_ts() 显式传入，
# 以避免数据库方言差异（SQLite strftime vs PG EXTRACT(EPOCH...)）
# ------------------------------------------------------------------

snapshot_version = Table(
    "snapshot_version",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("share_name", String, nullable=False),
    Column("schema_name", String, nullable=False),
    Column("table_name", String, nullable=False),
    Column("snapshot_id", Integer, nullable=False),
    Column("version", Integer, nullable=False),
    Column("timestamp", Integer, nullable=False),
    Column("created_at", Integer, nullable=False),
    UniqueConstraint("share_name", "schema_name", "table_name", "snapshot_id"),
)

bearer_tokens = Table(
    "bearer_tokens",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("token_hash", String, unique=True, nullable=False),
    Column("token_prefix", String, nullable=False),
    Column("recipient_id", String, nullable=False),
    Column("created_at", Integer, nullable=False),
    Column("expires_at", Integer),
    Column("is_revoked", Integer, default=0),
    Column("revoked_at", Integer),
)

recipients = Table(
    "recipients",
    _metadata,
    Column("recipient_id", String, primary_key=True),
    Column("recipient_name", String, unique=True, nullable=False),
    Column("comment", Text),
    Column("created_at", Integer, nullable=False),
    Column("updated_at", Integer, nullable=False),
    Column("is_active", Integer, default=1),
)

shares = Table(
    "shares",
    _metadata,
    Column("share_id", String, primary_key=True),
    Column("share_name", String, unique=True, nullable=False),
    Column("display_name", String),
    Column("comment", Text),
    Column("properties", Text),
    Column("created_at", Integer, nullable=False),
    Column("updated_at", Integer, nullable=False),
)

shared_schemas = Table(
    "shared_schemas",
    _metadata,
    Column("schema_id", String, primary_key=True),
    Column("share_id", String, nullable=False),
    Column("schema_name", String, nullable=False),
    Column("metastore_db", String, nullable=False, default=""),
    Column("created_at", Integer, nullable=False),
    Column("updated_at", Integer, nullable=False),
    UniqueConstraint("share_id", "schema_name"),
    ForeignKeyConstraint(["share_id"], ["shares.share_id"], ondelete="CASCADE"),
)

shared_tables = Table(
    "shared_tables",
    _metadata,
    Column("table_id", String, primary_key=True),
    Column("share_id", String, nullable=False),
    Column("linked_schema_id", String),
    Column("table_name", String, nullable=False),
    Column("location", String, nullable=False, default=""),
    Column("metastore_db", String, nullable=False, default=""),
    Column("metastore_table", String),
    Column("schema_name", String, nullable=False, default=""),
    Column("auxiliary_locations", Text),
    Column("created_at", Integer, nullable=False),
    Column("updated_at", Integer, nullable=False),
    UniqueConstraint("share_id", "linked_schema_id", "metastore_db", "metastore_table"),
    ForeignKeyConstraint(["share_id"], ["shares.share_id"], ondelete="CASCADE"),
    ForeignKeyConstraint(["linked_schema_id"], ["shared_schemas.schema_id"], ondelete="CASCADE"),
)

recipient_shares = Table(
    "recipient_shares",
    _metadata,
    Column("id", String, primary_key=True),
    Column("recipient_id", String, nullable=False),
    Column("share_id", String),
    Column("granted_at", Integer, nullable=False),
    Column("granted_by", String),
    UniqueConstraint("recipient_id", "share_id"),
    ForeignKeyConstraint(["recipient_id"], ["recipients.recipient_id"], ondelete="CASCADE"),
    ForeignKeyConstraint(["share_id"], ["shares.share_id"], ondelete="CASCADE"),
)

token_revocation = Table(
    "token_revocation",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("token_hash", String, unique=True, nullable=False),
    Column("revoked_at", Integer, nullable=False),
    Column("reason", String),
)

# 管理员用户表：存储 Admin UI 登录用户信息
# password_hash 使用 bcrypt 哈希存储，永不明文保存
admin_users = Table(
    "admin_users",
    _metadata,
    Column("admin_id", String, primary_key=True),
    Column("username", String, unique=True, nullable=False),
    Column("password_hash", String, nullable=False),
    Column("display_name", String, default=""),
    Column("is_active", Integer, default=1),
    Column("created_at", Integer, nullable=False),
    Column("updated_at", Integer, nullable=False),
)

# ------------------------------------------------------------------
# 业务索引定义
# 由 MetaData.create_all() 一并创建，包含 IF NOT EXISTS 语义
# ------------------------------------------------------------------

idx_snapshot_version_table = Index(
    "idx_snapshot_version_table",
    snapshot_version.c.share_name,
    snapshot_version.c.schema_name,
    snapshot_version.c.table_name,
)

idx_snapshot_version_timestamp = Index(
    "idx_snapshot_version_timestamp",
    snapshot_version.c.share_name,
    snapshot_version.c.schema_name,
    snapshot_version.c.table_name,
    snapshot_version.c.timestamp,
)

idx_bearer_tokens_token_hash = Index(
    "idx_bearer_tokens_token_hash",
    bearer_tokens.c.token_hash,
)

idx_bearer_tokens_recipient = Index(
    "idx_bearer_tokens_recipient",
    bearer_tokens.c.recipient_id,
)

idx_recipient_shares_recipient = Index(
    "idx_recipient_shares_recipient",
    recipient_shares.c.recipient_id,
)

idx_admin_users_username = Index(
    "idx_admin_users_username",
    admin_users.c.username,
)


class Database:
    """数据库管理类

    该类使用单例模式管理 SQLAlchemy Engine + MetaData。
    仅负责引擎的创建、表结构初始化和生命周期管理。
    业务数据访问由各 Repository 层负责。

    Attributes:
        _instance: 单例实例。
        _engine: SQLAlchemy Engine 实例。
        _metadata: SQLAlchemy MetaData 实例（包含所有 Table 定义）。
    """

    _instance: Optional["Database"] = None
    _engine: Optional[Engine] = None
    _metadata: MetaData = _metadata

    # 表对象引用，方便 Repository 层通过实例访问
    shares_table = shares
    shared_schemas_table = shared_schemas
    shared_tables_table = shared_tables
    recipients_table = recipients
    recipient_shares_table = recipient_shares
    bearer_tokens_table = bearer_tokens
    token_revocation_table = token_revocation
    snapshot_version_table = snapshot_version
    admin_users_table = admin_users

    def __new__(cls):
        """获取或创建单例实例。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self, db_url: Optional[str] = None) -> None:
        """初始化数据库引擎并创建表结构。

        使用 create_engine(url, **kwargs) 创建 Engine。
        对 SQLite 自动传入 connect_args={"check_same_thread": False}。
        SQLite 数据库默认使用 NullPool 连接池策略（适合读密集型场景），
        可通过 database.pool.pool_type 切换为 QueuePool。
        PostgreSQL 数据库始终使用 QueuePool。
        SQLite 数据库额外应用 WAL 模式和读性能 PRAGMA 优化。
        初始化后自动执行数据库迁移（如删除废弃的 profile 列）。

        Args:
            db_url: SQLAlchemy 数据库连接 URL，如果为 None 则使用配置中的 URL。
        """
        if db_url is None:
            config = get_config()
            db_url = config.database.url

        connect_args = {}
        _is_sqlite = db_url.startswith("sqlite")
        if _is_sqlite:
            connect_args["check_same_thread"] = False
            db_path = db_url[len("sqlite:///") :]
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

        pool_config = get_config().database.pool
        engine_kwargs = self._build_engine_kwargs(
            is_sqlite=_is_sqlite,
            pool_config=pool_config,
        )

        self._engine = create_engine(
            db_url,
            connect_args=connect_args,
            echo=False,
            **engine_kwargs,
        )
        self._metadata.create_all(self._engine, checkfirst=True)
        logger.info(f"数据库引擎已初始化: {db_url}")

        if _is_sqlite:
            self._apply_sqlite_pragmas()

        self._log_pool_config(is_sqlite=_is_sqlite, pool_config=pool_config)

    def _build_engine_kwargs(self, is_sqlite: bool, pool_config) -> dict:
        """构建 create_engine() 的连接池关键字参数。

        对 SQLite 数据库根据 pool_type 选择 NullPool 或 QueuePool，
        PostgreSQL 数据库始终使用 QueuePool 并忽略 pool_type 配置。

        NullPool 仅支持 pool_recycle 和 pool_pre_ping，
        不支持 pool_size、max_overflow、pool_timeout（这些仅 QueuePool 有效）。

        Args:
            is_sqlite: 是否为 SQLite 数据库。
            pool_config: PoolConfig 配置实例。

        Returns:
            包含 poolclass, pool_size, max_overflow, pool_recycle,
            pool_timeout, pool_pre_ping 的参数字典。
        """
        kwargs = {}

        if is_sqlite:
            if pool_config.pool_type == "queue_pool":
                kwargs["poolclass"] = QueuePool
                kwargs["pool_size"] = pool_config.pool_size
                kwargs["max_overflow"] = pool_config.max_overflow
                kwargs["pool_timeout"] = pool_config.pool_timeout
            else:
                kwargs["poolclass"] = NullPool
        else:
            kwargs["poolclass"] = QueuePool
            kwargs["pool_size"] = pool_config.pool_size
            kwargs["max_overflow"] = pool_config.max_overflow
            kwargs["pool_timeout"] = pool_config.pool_timeout

        kwargs["pool_recycle"] = pool_config.pool_recycle
        kwargs["pool_pre_ping"] = pool_config.pool_pre_ping

        return kwargs

    def _apply_sqlite_pragmas(self) -> None:
        """为 SQLite 数据库启用 WAL 模式并注册连接级 PRAGMA 优化。

        WAL 模式（journal_mode=WAL）和 wal_autocheckpoint 是持久设置，
        写入数据库文件头部，所有后续连接自动继承，只需执行一次。

        连接级 PRAGMA（cache_size、mmap_size、temp_store、synchronous、
        foreign_keys）通过 SQLAlchemy `connect` 事件注册，确保
        每个新连接（包括 NullPool 模式下的每次 connect()）都自动应用。

        mmap_size 设置失败时（如 32 位系统）记录警告日志并回退，不阻止启动。
        """
        if self._engine is None:
            return

        # 持久化 PRAGMA：仅需执行一次，写入数据库文件头部
        with self._engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA wal_autocheckpoint=1000"))
            conn.commit()

        # 注册连接事件：每个新连接自动应用连接级 PRAGMA
        self._register_sqlite_connect_events()

        logger.info(
            "SQLite PRAGMA 优化已应用: journal_mode=WAL, "
            "wal_autocheckpoint=1000, cache_size=-20000, "
            "mmap_size=268435456, temp_store=MEMORY, "
            "synchronous=NORMAL, foreign_keys=ON"
        )

    def _register_sqlite_connect_events(self) -> None:
        """注册 SQLAlchemy `connect` 事件，为每个新连接应用连接级 PRAGMA。

        NullPool 模式下每次 connect() 创建新连接，必须通过事件机制
        确保每个连接都获得正确的 PRAGMA 设置。QueuePool 模式下同样适用。
        """
        engine = self._engine
        if engine is None:
            return

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_connection, connection_record):
            """新连接建立时设置连接级 PRAGMA 优化参数。

            这些 PRAGMA 仅影响当前连接，不会持久化到数据库文件。
            mmap_size 失败时仅记录警告，不影响连接建立。
            """
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA cache_size=-20000")
            cursor.execute("PRAGMA temp_store=2")
            cursor.execute("PRAGMA synchronous=1")
            cursor.execute("PRAGMA foreign_keys=ON")
            try:
                cursor.execute("PRAGMA mmap_size=268435456")
            except Exception as e:
                logger.warning(
                    f"mmap_size 设置失败（可能是 32 位系统或文件系统不支持 mmap），"
                    f"已跳过当前连接的 mmap 优化: {e}"
                )
            cursor.close()

    def _log_pool_config(self, is_sqlite: bool, pool_config) -> None:
        """输出连接池配置摘要日志。

        Args:
            is_sqlite: 是否为 SQLite 数据库。
            pool_config: PoolConfig 配置实例。
        """
        pool_type = pool_config.pool_type if is_sqlite else "queue_pool"
        if pool_type == "null_pool" or (is_sqlite and pool_config.pool_type == "null_pool"):
            pool_desc = "pool_type=NullPool (SQLite 读密集型优化)"
        else:
            pool_desc = (
                f"pool_type=QueuePool, pool_size={pool_config.pool_size}, "
                f"max_overflow={pool_config.max_overflow}"
            )

        logger.info(
            f"连接池配置: {pool_desc}, "
            f"pool_recycle={pool_config.pool_recycle}s, "
            f"pool_timeout={pool_config.pool_timeout}s, "
            f"pool_pre_ping={pool_config.pool_pre_ping}"
        )

    def get_engine(self) -> Engine:
        """获取 SQLAlchemy Engine 实例。

        Returns:
            Engine 实例。

        Raises:
            RuntimeError: 如果数据库未初始化。
        """
        if self._engine is None:
            raise RuntimeError("Database not initialized")
        return self._engine

    def close(self) -> None:
        """释放数据库引擎资源。

        调用 Engine.dispose() 关闭所有连接池中的连接。
        """
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            logger.info("数据库引擎已释放")


_global_db: Optional[Database] = None


def get_database() -> Database:
    """获取全局数据库实例。

    如果数据库尚未初始化，则进行初始化。

    Returns:
        全局 Database 实例。
    """
    global _global_db
    if _global_db is None:
        _global_db = Database()
        _global_db.initialize()
    return _global_db


def init_database(db_url: Optional[str] = None) -> Database:
    """初始化全局数据库实例。

    Args:
        db_url: SQLAlchemy 数据库连接 URL，如果为 None 则使用配置中的 URL。

    Returns:
        初始化的 Database 实例。
    """
    global _global_db
    _global_db = Database()
    _global_db.initialize(db_url)
    return _global_db
