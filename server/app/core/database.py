"""
数据库管理模块

该模块提供 Delta Sharing Server 的数据库管理功能，基于 SQLAlchemy Core 实现。
数据库用于存储以下 8 张业务表：
- shares: 共享资源定义
- shared_schemas: 共享 Schema 定义
- shared_tables: 共享 Table 定义
- recipients: 数据接收方
- recipient_shares: 接收方与 Share 的授权关系
- bearer_tokens: Bearer Token 认证凭证（token_hash 存储 SHA-256 哈希值，不持久化 Profile）
- token_revocation: Token 撤销记录（token_hash 存储 SHA-256 哈希值）
- snapshot_version: 快照版本追踪信息

使用 SQLAlchemy Engine + MetaData + Table 管理数据库连接与表结构，
支持 SQLite 和 PostgreSQL 双向兼容。
使用单例模式确保全局只有一个数据库引擎实例。

业务数据访问已迁移至 Repository 层：
- Token 相关 → TokenRepository
- Version 相关 → VersionRepository
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
    text,
)
from loguru import logger

from app.core.config import get_config


# 定义 MetaData 实例，用于注册所有表定义
_metadata = MetaData()

# ------------------------------------------------------------------
# 8 张业务表的 Table 对象定义
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

    def __new__(cls):
        """获取或创建单例实例。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self, db_url: Optional[str] = None) -> None:
        """初始化数据库引擎并创建表结构。

        使用 create_engine(url) 创建 Engine，对 SQLite 自动传入
        connect_args={"check_same_thread": False}。
        SQLite 数据库启用 WAL 模式以提升并发读取性能，避免读-写互斥导致的
        "database is locked" 错误（在高并发场景下可能导致 token 验证失败返回 401）。
        初始化后自动执行数据库迁移（如删除废弃的 profile 列）。

        Args:
            db_url: SQLAlchemy 数据库连接 URL，如果为 None 则使用配置中的 URL。
        """
        if db_url is None:
            config = get_config()
            db_url = config.database.url

        connect_args = {}
        # 标记是否使用 SQLite，用于后续 WAL 模式配置
        _is_sqlite = db_url.startswith("sqlite")
        if _is_sqlite:
            connect_args["check_same_thread"] = False
            db_path = db_url[len("sqlite:///") :]
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

        self._engine = create_engine(db_url, connect_args=connect_args, echo=False)
        self._metadata.create_all(self._engine, checkfirst=True)
        logger.info(f"数据库引擎已初始化: {db_url}")

        # SQLite WAL 模式：提升并发读写性能，避免 "database is locked" 错误
        if _is_sqlite:
            self._enable_wal_mode()


    def _enable_wal_mode(self) -> None:
        """为 SQLite 数据库启用 WAL（Write-Ahead Logging）模式。

        WAL 模式下读操作不会被写操作阻塞，写操作也不会被读操作阻塞，
        显著提升高并发场景下的数据库访问稳定性。
        journal_mode 设置为 WAL 后持久生效（写入数据库文件头部），
        后续所有连接均自动使用 WAL 模式。
        """
        if self._engine is None:
            return
        with self._engine.connect() as conn:
            # 执行 PRAGMA 启用 WAL 模式（持久生效，仅需执行一次）
            conn.execute(text("PRAGMA journal_mode=WAL"))
            # 自动 WAL checkpoint 阈值设为 1000 页（约 4MB），
            # 避免 WAL 文件无限增长
            conn.execute(text("PRAGMA wal_autocheckpoint=1000"))
            conn.commit()
            logger.info("SQLite WAL 模式已启用 (journal_mode=WAL, wal_autocheckpoint=1000)")

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
