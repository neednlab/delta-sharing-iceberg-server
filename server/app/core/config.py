"""
配置管理模块

该模块负责加载和管理 Delta Sharing Server 的所有配置项。
支持从 YAML 配置文件和环境变量两种方式读取配置。
配置包括服务器设置、COS 存储设置、数据库设置、共享表配置等。

配置优先级：环境变量 > YAML 配置文件
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml

from loguru import logger
from app.core.errors import DeltaSharingError, ErrorCode


class ServerConfig:
    """服务器配置类

    Attributes:
        host: Data Plane 服务器监听地址，默认为 "0.0.0.0"。
        port: Data Plane 服务器监听端口，默认为 8088。
        admin_host: Admin API 服务器监听地址，默认为 "127.0.0.1"（仅本地访问）。
        admin_port: Admin API 服务器监听端口，默认为 8089。
        api_prefix: API 路径前缀，默认为 "/delta-sharing"。
        max_request_body_size_mb: Data Plane 请求体大小上限（MB），默认为 1。
        admin_max_request_body_size_mb: Admin API 请求体大小上限（MB），默认为 10。
    """

    host: str = "0.0.0.0"
    port: int = 8088
    admin_host: str = "127.0.0.1"
    admin_port: int = 8089
    api_prefix: str = "/delta-sharing"
    max_request_body_size_mb: int = 1
    admin_max_request_body_size_mb: int = 10


class COSConfig:
    """腾讯云 COS 存储配置类

    Attributes:
        region: COS 区域。
        secret_id: 访问密钥 ID。
        secret_key: 访问密钥 Key。
        endpoint: COS 访问端点。
    """

    region: str = ""
    secret_id: str = ""
    secret_key: str = ""
    endpoint: str = ""


class PoolConfig:
    """连接池配置类

    配置 SQLAlchemy Engine 的连接池行为。
    NullPool 适用于 SQLite 读密集型场景（连接创建开销极低），
    QueuePool 适用于 PostgreSQL 等远端数据库场景。

    Attributes:
        pool_type: 连接池类型，"null_pool" 或 "queue_pool"。
            SQLite 默认为 "null_pool"，PostgreSQL 忽略此配置始终使用 QueuePool。
        pool_size: QueuePool 模式下持久连接数，默认 10。
        max_overflow: QueuePool 模式下额外临时连接上限，默认 20。
        pool_recycle: 连接回收时间（秒），-1 表示不回收，默认 3600。
        pool_timeout: 获取连接超时时间（秒），默认 10。
        pool_pre_ping: 连接前是否执行健康检查（SELECT 1），默认 True。
    """

    pool_type: str = "null_pool"
    pool_size: int = 10
    max_overflow: int = 20
    pool_recycle: int = 3600
    pool_timeout: int = 10
    pool_pre_ping: bool = True


class DatabaseConfig:
    """数据库配置类

    支持 SQLAlchemy Database URL 格式。
    默认使用 SQLite，可通过修改 url 切换至 PostgreSQL 等其他数据库。

    Attributes:
        url: SQLAlchemy 数据库连接 URL，默认为 "sqlite:///./data/server.db"。
        pool: 连接池配置，默认为 PoolConfig 默认值。
    """

    url: str = "sqlite:///./data/server.db"

    def __init__(self):
        self.pool = PoolConfig()


class TokenConfig:
    """Token 配置类

    Attributes:
        rotation_period_hours: Token 轮换周期（小时），默认为 24 小时。
        expiration_hours: Token 过期时间（小时），默认为 168 小时（7 天）。
        max_tokens_per_recipient: 每个 recipient 最多持有的有效 token 数量，默认为 2。
        page_token_secret: Page token HMAC 签名密钥，通过环境变量 PAGE_TOKEN_SECRET 配置。
    """

    rotation_period_hours: int = 24
    expiration_hours: int = 168
    max_tokens_per_recipient: int = 2
    page_token_secret: str = ""


class PresignedURLConfig:
    """预签名 URL 配置类

    Attributes:
        expiration_hours: 预签名 URL 默认过期时间（小时），默认为 6 小时。
        min_expiration_hours: 预签名 URL 最小过期时间（小时），默认为 1 小时。
        max_expiration_hours: 预签名 URL 最大过期时间（小时），默认为 168 小时（7 天）。
    """

    expiration_hours: int = 6
    min_expiration_hours: int = 1
    max_expiration_hours: int = 168


class TableConfig:
    """表配置类

    Attributes:
        location: 表的存储位置路径。
        metastore_db: Metastore 数据库名称。
        metastore_table: Metastore 表名称。
        auxiliary_locations: 辅助存储位置列表（可选）。
        access_modes: 支持的访问模式列表，如 ["url", "dir"]（可选）。
    """

    location: str = ""
    metastore_db: str = ""
    metastore_table: str = ""
    auxiliary_locations: Optional[List[str]] = None
    access_modes: Optional[List[str]] = None


class SchemaConfig:
    """Schema 配置类

    Attributes:
        tables: 该 Schema 下的表配置字典，键为表名（不区分大小写）。
    """

    tables: Dict[str, TableConfig] = {}


class ShareConfig:
    """Share 配置类

    Attributes:
        schemas: 该 Share 下的 Schema 配置字典，键为 Schema 名（不区分大小写）。
        id: Share 的唯一标识符（可选）。
        display_name: 显示名称（可选）。
        comment: 描述说明（可选）。
        properties: 键值对属性（可选）。
    """

    schemas: Dict[str, "SchemaConfig"] = {}
    id: Optional[str] = None
    display_name: Optional[str] = None
    comment: Optional[str] = None
    properties: Optional[Dict[str, str]] = None


class SharesConfig:
    """Shares 配置类

    Attributes:
        shares: 所有 Share 的配置字典，键为 Share 名（不区分大小写）。
        use_database: 是否使用数据库存储 shares 配置，默认为 False（使用 config.yaml）。
        fallback_file: 当 use_database=True 时，数据库中找不到时的回退配置文件路径。
    """

    shares: Dict[str, Any] = {}
    use_database: bool = False
    fallback_file: Optional[str] = None


class ProfileConfig:
    """Profile 配置类

    Profile 文件用于客户端连接服务器，包含服务端点和支持的 Token 过期时间。

    Attributes:
        endpoint: 服务端点 URL，默认为 "http://localhost:8088/delta-sharing"。
        token_expiration_hours: Token 过期时间（小时），默认为 168 小时（7 天）。
    """

    endpoint: str = "http://localhost:8088/delta-sharing"
    token_expiration_hours: int = 168


class LoggingConfig:
    """日志配置类

    管理应用日志和审计日志的全局配置。

    Attributes:
        log_dir: 日志文件输出目录，默认为 "./log"。
        app_log_level: 应用日志级别，控制控制台和文件 handler 的输出级别。
                       默认为 "INFO"。可选值：DEBUG/INFO/WARNING/ERROR。
        app_log_retention: 应用日志文件保留时长，默认为 "30 days"。
        audit_log_level: 审计日志级别，默认为 "INFO"。控制 file_paths 等敏感字段是否记录。
                         可选值："INFO"/"DEBUG"。
    """

    log_dir: str = "./log"
    app_log_level: str = "INFO"
    app_log_retention: str = "30 days"
    audit_log_level: str = "INFO"


class AdminConfig:
    """管理员认证配置类

    管理 Admin UI 的 JWT 认证相关配置。

    Attributes:
        jwt_secret: JWT 签名密钥。支持通过配置文件中的 ${JWT_SECRET} 占位符
            从环境变量读取，或直接设置明文值。未配置时启动时自动生成随机密钥。
    """

    jwt_secret: str = ""


class DLCConfig:
    """腾讯云 DLC 配置类

    DLC (Data Lake Computing) 是腾讯云数据湖计算服务。

    Attributes:
        secret_id: DLC 访问密钥 ID。
        secret_key: DLC 访问密钥 Key。
        region: DLC 区域，默认为 "ap-shanghai"。
        endpoint: DLC API 端点。
    """

    secret_id: str = ""
    secret_key: str = ""
    region: str = ""
    endpoint: str = ""


class Config:
    """全局配置类

    该类包含所有配置项的实例，管理服务器的完整配置状态。

    Attributes:
        server: 服务器配置。
        cos: COS 存储配置。
        database: 数据库配置。
        token: Token 配置。
        presigned_url: 预签名 URL 配置。
        shares: Shares 配置。
        profile: Profile 配置。
        admin: 管理员认证配置。
        dlc: DLC 配置。
        logging: 日志配置（含审计日志级别）。
    """

    server: ServerConfig
    cos: COSConfig
    database: DatabaseConfig
    token: TokenConfig
    presigned_url: PresignedURLConfig
    shares: SharesConfig
    profile: ProfileConfig
    admin: AdminConfig
    dlc: DLCConfig
    logging: LoggingConfig

    def __init__(self):
        """初始化所有配置子类的实例。"""
        self.server = ServerConfig()
        self.cos = COSConfig()
        self.database = DatabaseConfig()
        self.token = TokenConfig()
        self.presigned_url = PresignedURLConfig()
        self.shares = SharesConfig()
        self.profile = ProfileConfig()
        self.admin = AdminConfig()
        self.dlc = DLCConfig()
        self.logging = LoggingConfig()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """从字典数据创建 Config 实例。

        Args:
            data: 包含配置数据的字典。

        Returns:
            配置完成的 Config 实例。
        """
        config = cls()

        for section_name, attr_name in _CONFIG_SECTION_MAP.items():
            if section_name in data:
                section_obj = getattr(config, attr_name)
                section_data = data[section_name]
                for key, value in section_data.items():
                    # 处理嵌套的 pool 配置子节
                    if key == "pool" and isinstance(value, dict):
                        for pool_key, pool_value in value.items():
                            setattr(section_obj.pool, pool_key, pool_value)
                    else:
                        setattr(section_obj, key, value)

        if "shares" in data:
            if isinstance(data["shares"], dict):
                shares_data = data["shares"].copy()
                config.shares.use_database = shares_data.pop("use_database", False)
                config.shares.fallback_file = shares_data.pop("fallback_file", None)
                config.shares.shares = shares_data
            else:
                config.shares = data["shares"]

        return config


_CONFIG_SECTION_MAP = {
    "server": "server",
    "cos": "cos",
    "database": "database",
    "token": "token",
    "presigned_url": "presigned_url",
    "profile": "profile",
    "admin": "admin",
    "dlc": "dlc",
    "logging": "logging",
}


_global_config: Optional[Config] = None


def load_config(config_path: str = "./config.yaml") -> Config:
    """从配置文件加载配置。

    读取 YAML 配置文件并加载所有配置项。环境变量会覆盖配置文件中的值。

    Args:
        config_path: 配置文件路径，默认为 "./config.yaml"。

    Returns:
        加载完成的 Config 实例。

    Raises:
        FileNotFoundError: 配置文件不存在时抛出。
    """
    global _global_config

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # 旧格式兼容：检测 database.path 自动转换为 database.url
    _migrate_database_path_to_url(data)

    _global_config = Config.from_dict(data)

    _env_overrides = [
        ("COS_SECRET_ID", _global_config.cos, "secret_id", None),
        ("COS_SECRET_KEY", _global_config.cos, "secret_key", None),
        ("DLC_SECRET_ID", _global_config.dlc, "secret_id", None),
        ("DLC_SECRET_KEY", _global_config.dlc, "secret_key", None),
        ("DLC_ENDPOINT", _global_config.dlc, "endpoint", None),
        ("DLC_REGION", _global_config.dlc, "region", "ap-shanghai"),
        ("PAGE_TOKEN_SECRET", _global_config.token, "page_token_secret", None),
        ("JWT_SECRET", _global_config.admin, "jwt_secret", None),
    ]

    for env_name, config_obj, attr_name, default in _env_overrides:
        env_value = os.environ.get(env_name)
        if env_value:
            setattr(config_obj, attr_name, env_value)
        elif default is not None:
            setattr(config_obj, attr_name, default)

    _validate_all_config(_global_config)

    return _global_config


def _migrate_database_path_to_url(data: Dict[str, Any]) -> None:
    """检测旧格式 database.path 配置并自动转换为 database.url。

    向后兼容逻辑：
    - 如果存在 database.path 且不存在 database.url，自动将其转换为
      database.url 格式（sqlite:///<path>），并打印弃用警告。
    - 如果两者同时存在，优先使用 database.url，忽略 database.path 并打印警告。
    - 如果仅有 database.url，无需处理。

    Args:
        data: 从配置文件解析出的原始配置字典。
    """
    database_section = data.get("database", {})
    if not isinstance(database_section, dict):
        return

    has_path = "path" in database_section
    has_url = "url" in database_section

    if has_path and has_url:
        logger.warning(
            "配置文件同时存在 database.path 和 database.url，"
            "将以 database.url 为准，旧 database.path 配置已废弃，请尽快更新配置文件"
        )
        del database_section["path"]
    elif has_path:
        old_path = database_section["path"]
        new_url = f"sqlite:///{old_path}"
        database_section["url"] = new_url
        del database_section["path"]
        logger.warning(
            f"检测到旧格式 database.path: '{old_path}'，"
            f"已自动转换为 database.url: '{new_url}'。"
            f"请尽快更新配置文件，database.path 将在未来版本中移除"
        )


def get_config() -> Config:
    """获取全局配置实例。

    如果尚未加载配置，则使用默认路径加载。

    Returns:
        全局 Config 实例。
    """
    global _global_config
    if _global_config is None:
        _global_config = load_config()
    return _global_config


def _build_table_config(data: dict) -> TableConfig:
    """从字典构建 TableConfig，统一 database/config 双路径的字段映射。

    该函数为 4 个查询函数提供一致的 TableConfig 构建逻辑，
    消除重复的字段赋值代码。

    Args:
        data: 包含表配置数据的字典。

    Returns:
        填充完成的 TableConfig 实例。
    """
    tc = TableConfig()
    tc.location = data.get("location", "")
    tc.metastore_db = data.get("metastore_db", "")
    tc.metastore_table = data.get("metastore_table", "")
    tc.auxiliary_locations = data.get("auxiliary_locations")
    return tc


def get_table_config(share_name: str, schema_name: str, table_name: str) -> Optional[TableConfig]:
    """获取指定表的配置信息。

    根据 Share、Schema 和表名查找对应的表配置。查找时不区分大小写。
    当 use_database=true 时从数据库读取，否则从配置文件读取。

    Args:
        share_name: Share 名称。
        schema_name: Schema 名称。
        table_name: 表名称。

    Returns:
        如果找到则返回 TableConfig 实例，否则返回 None。
    """
    config = get_config()

    if config.shares.use_database:
        from app.repositories.share_repository import ShareRepository

        repo = ShareRepository()
        table_data = repo.get_table(share_name, schema_name, table_name)
        if table_data:
            return _build_table_config(table_data)
        return None

    shares_data = config.shares

    shares_dict = _unwrap_shares_dict(shares_data)
    if shares_dict is None:
        return None

    share_name_lower = share_name.lower()
    if share_name_lower in shares_dict:
        share = shares_dict[share_name_lower]
        if isinstance(share, dict):
            schemas = share.get("schemas", {})
        elif hasattr(share, "schemas"):
            schemas = share.schemas
        else:
            return None

        schema_name_lower = schema_name.lower()
        if schema_name_lower in schemas:
            schema = schemas[schema_name_lower]
            if isinstance(schema, dict):
                tables = schema.get("tables", {})
            elif hasattr(schema, "tables"):
                tables = schema.tables
            else:
                return None

            table_name_lower = table_name.lower()
            if table_name_lower in tables:
                table_data = tables[table_name_lower]
                table_config = TableConfig()
                if isinstance(table_data, dict):
                    for key, value in table_data.items():
                        setattr(table_config, key, value)
                elif hasattr(table_data, "__dict__"):
                    for key, value in table_data.__dict__.items():
                        if not key.startswith("_"):
                            setattr(table_config, key, value)
                return table_config
    return None


def get_all_shares() -> Dict[str, ShareConfig]:
    """获取所有 Share 配置。

    当 use_database=true 时从数据库读取，否则从配置文件读取。

    Returns:
        包含所有 Share 配置的字典，键为 Share 名（转小写）。
    """
    config = get_config()
    if config.shares.use_database:
        return _get_shares_from_database()
    return _get_shares_from_config()


def _unwrap_shares_dict(shares_data: object) -> Optional[Dict[str, Any]]:
    """将 config.shares 解包为纯 dict 格式。

    兼容 SharesConfig 对象和纯 dict 两种数据源，统一返回 dict 以便后续处理。

    Args:
        shares_data: config.shares 的值，可能为 SharesConfig 或 dict。

    Returns:
        包含 shares 数据的字典，如果类型不支持则返回 None。
    """
    if isinstance(shares_data, SharesConfig):
        return shares_data.shares
    if isinstance(shares_data, dict):
        return shares_data
    return None


def _get_shares_from_database() -> Dict[str, ShareConfig]:
    """从数据库获取所有 Share 配置。

    Returns:
        包含所有 Share 配置的字典，键为 Share 名（转小写）。
    """
    from app.repositories.share_repository import ShareRepository

    repo = ShareRepository()
    shares_list = repo.list_shares()

    result = {}
    for share in shares_list:
        share_name = share["share_name"]
        share_config = ShareConfig()
        share_config.id = share.get("share_id")
        share_config.display_name = share.get("display_name")
        share_config.comment = share.get("comment")
        share_config.properties = share.get("properties")
        share_config.schemas = repo.get_share_schemas_from_db(share_name)
        result[share_name.lower()] = share_config
    return result


def _get_shares_from_config() -> Dict[str, ShareConfig]:
    """从配置文件获取所有 Share 配置。

    Returns:
        包含所有 Share 配置的字典，键为 Share 名（转小写）。
    """
    config = get_config()
    shares_data = config.shares

    shares_dict = _unwrap_shares_dict(shares_data)
    if shares_dict is None:
        return {}

    result = {}
    for key, value in shares_dict.items():
        share_config = ShareConfig()
        if isinstance(value, dict):
            for k, v in value.items():
                if k != "schemas":
                    # schemas 字段不在 _get_shares_from_config 中填充，
                    # 由调用者通过 get_share_schemas() 按需获取以实现延迟加载
                    setattr(share_config, k, v)
        result[key.lower()] = share_config
    return result


def get_share_schemas(share_name: str) -> Dict[str, SchemaConfig]:
    """获取指定 Share 下的所有 Schema 配置。

    当 use_database=true 时从数据库读取，否则从配置文件读取。

    Args:
        share_name: Share 名称。

    Returns:
        包含所有 Schema 配置的字典，键为 Schema 名（转小写）。
    """
    config = get_config()
    if config.shares.use_database:
        return _get_schemas_from_database(share_name)
    return _get_schemas_from_config(share_name)


def _get_schemas_from_database(share_name: str) -> Dict[str, SchemaConfig]:
    """从数据库获取指定 Share 下的所有 Schema 配置。

    Args:
        share_name: Share 名称。

    Returns:
        包含所有 Schema 配置的字典，键为 Schema 名（转小写）。
    """
    from app.repositories.share_repository import ShareRepository

    repo = ShareRepository()
    schemas_dict = repo.get_share_schemas_from_db(share_name)

    result = {}
    for schema_name_lower, schema_data in schemas_dict.items():
        schema_config = SchemaConfig()
        # tables 字段不在此处填充，由调用者通过 _get_tables_from_database()
        # 按需获取以实现职责分离，避免一次查询加载全部表数据
        schema_config.tables = {}
        result[schema_name_lower] = schema_config
    return result


def _get_schemas_from_config(share_name: str) -> Dict[str, SchemaConfig]:
    """从配置文件获取指定 Share 下的所有 Schema 配置。

    Args:
        share_name: Share 名称。

    Returns:
        包含所有 Schema 配置的字典，键为 Schema 名（转小写）。
    """
    config = get_config()
    shares_data = config.shares

    shares_dict = _unwrap_shares_dict(shares_data)
    if shares_dict is None:
        return {}

    share_name_lower = share_name.lower()
    if share_name_lower in shares_dict:
        share = shares_dict[share_name_lower]
        if isinstance(share, dict) and "schemas" in share:
            schemas = share["schemas"]
            result = {}
            for key, value in schemas.items():
                schema_config = SchemaConfig()
                if isinstance(value, dict):
                    for k, v in value.items():
                        setattr(schema_config, k, v)
                result[key.lower()] = schema_config
            return result
    return {}


def get_schema_tables(share_name: str, schema_name: str) -> Dict[str, TableConfig]:
    """获取指定 Schema 下的所有表配置。

    当 use_database=true 时从数据库读取，否则从配置文件读取。

    Args:
        share_name: Share 名称。
        schema_name: Schema 名称。

    Returns:
        包含所有表配置的字典，键为表名（转小写）。
    """
    config = get_config()
    if config.shares.use_database:
        return _get_tables_from_database(share_name, schema_name)
    return _get_tables_from_config(share_name, schema_name)


def _get_tables_from_database(share_name: str, schema_name: str) -> Dict[str, TableConfig]:
    """从数据库获取指定 Schema 下的所有表配置。

    Args:
        share_name: Share 名称。
        schema_name: Schema 名称。

    Returns:
        包含所有表配置的字典，键为表名（转小写）。
    """
    from app.repositories.share_repository import ShareRepository

    repo = ShareRepository()
    tables_dict = repo.get_schema_tables_from_db(share_name, schema_name)

    result = {}
    for table_name_lower, table_data in tables_dict.items():
        result[table_name_lower] = _build_table_config(table_data)
    return result


def _get_tables_from_config(share_name: str, schema_name: str) -> Dict[str, TableConfig]:
    """从配置文件获取指定 Schema 下的所有表配置。

    Args:
        share_name: Share 名称。
        schema_name: Schema 名称。

    Returns:
        包含所有表配置的字典，键为表名（转小写）。
    """
    config = get_config()
    shares_data = config.shares

    shares_dict = _unwrap_shares_dict(shares_data)
    if shares_dict is None:
        return {}

    share_name_lower = share_name.lower()
    if share_name_lower in shares_dict:
        share = shares_dict[share_name_lower]
        if isinstance(share, dict) and "schemas" in share:
            schemas = share["schemas"]
            schema_name_lower = schema_name.lower()
            if schema_name_lower in schemas:
                schema = schemas[schema_name_lower]
                if isinstance(schema, dict) and "tables" in schema:
                    tables = schema["tables"]
                    result = {}
                    for key, value in tables.items():
                        if isinstance(value, dict):
                            result[key.lower()] = _build_table_config(value)
                        else:
                            result[key.lower()] = TableConfig()
                    return result
    return {}


def get_share_all_tables(share_name: str) -> Dict[str, Dict[str, TableConfig]]:
    """获取指定 Share 下的所有 Table（包含直绑表和关联表）。

    与 get_schema_tables() 逐个 Schema 查询不同，本函数一次性返回该 Share 下
    的全部 Table，既包括通过 shared_schemas 实体关联的表，也包括
    linked_schema_id 为 NULL、仅通过 schema_name 字段指向虚拟 Schema 的直绑表。

    当 use_database=true 时从数据库读取，否则从配置文件读取。
    配置模式下的直绑表场景不适用，返回空字典。

    Args:
        share_name: Share 名称。

    Returns:
        嵌套字典，外层键为 schema_name（小写），内层键为 table_name（小写），
        值为 TableConfig 对象。
    """
    config = get_config()
    if config.shares.use_database:
        return _get_all_tables_from_database(share_name)
    return _get_all_tables_from_config(share_name)


def _get_all_tables_from_database(share_name: str) -> Dict[str, Dict[str, TableConfig]]:
    """从数据库获取指定 Share 下的所有 Table（含直绑表和关联表）。

    Args:
        share_name: Share 名称。

    Returns:
        嵌套字典，外层键为 schema_name（小写），内层键为 table_name（小写），
        值为 TableConfig 对象。
    """
    from app.repositories.share_repository import ShareRepository

    repo = ShareRepository()
    all_tables_dict = repo.get_all_tables_for_share(share_name)

    result: Dict[str, Dict[str, TableConfig]] = {}
    for schema_name_lower, tables_dict in all_tables_dict.items():
        result[schema_name_lower] = {}
        for table_name_lower, table_data in tables_dict.items():
            result[schema_name_lower][table_name_lower] = _build_table_config(table_data)
    return result


def _get_all_tables_from_config(share_name: str) -> Dict[str, Dict[str, TableConfig]]:
    """从配置文件获取指定 Share 下的所有 Table。

    配置文件模式下依次遍历 share→schemas→tables 构建嵌套字典。

    Args:
        share_name: Share 名称。

    Returns:
        嵌套字典，外层键为 schema_name（小写），内层键为 table_name（小写），
        值为 TableConfig 对象。
    """
    config = get_config()
    shares_data = config.shares
    shares_dict = _unwrap_shares_dict(shares_data)
    if shares_dict is None:
        return {}

    share_name_lower = share_name.lower()
    if share_name_lower not in shares_dict:
        return {}

    share = shares_dict[share_name_lower]
    if not isinstance(share, dict) or "schemas" not in share:
        return {}

    result: Dict[str, Dict[str, TableConfig]] = {}
    for schema_name, schema_value in share["schemas"].items():
        schema_name_lower = schema_name.lower()
        result[schema_name_lower] = {}
        if isinstance(schema_value, dict) and "tables" in schema_value:
            for table_name, table_value in schema_value["tables"].items():
                table_config = TableConfig()
                if isinstance(table_value, dict):
                    for k, v in table_value.items():
                        setattr(table_config, k, v)
                result[schema_name_lower][table_name.lower()] = table_config
    return result


def _validate_cos_path_format(config: Config) -> None:
    """校验所有表的 location 格式。

    校验配置文件中的表 location，location 必须为 cosn://bucket/key 格式，
    否则拒绝启动。数据库模式的表校验由 validate_cos_path_format_in_database()
    在数据库初始化后单独调用。

    Args:
        config: 全局配置对象。

    Raises:
        DeltaSharingError: 当 location 格式无效时抛出。
    """
    shares_data = config.shares
    shares_dict = _unwrap_shares_dict(shares_data)
    if shares_dict is None:
        return

    for share_key, share_value in shares_dict.items():
        if not isinstance(share_value, dict) or "schemas" not in share_value:
            continue
        schemas = share_value["schemas"]
        for schema_key, schema_value in schemas.items():
            if not isinstance(schema_value, dict) or "tables" not in schema_value:
                continue
            tables = schema_value["tables"]
            for table_key, table_value in tables.items():
                location = None
                if isinstance(table_value, dict):
                    location = table_value.get("location")
                elif hasattr(table_value, "location"):
                    location = table_value.location

                if location and not location.startswith("cosn://"):
                    raise DeltaSharingError(
                        ErrorCode.INVALID_PARAMETER_VALUE,
                        f"表 '{share_key}.{schema_key}.{table_key}' 的 location 格式无效: "
                        f"'{location}'。location 必须为 cosn://bucket/key 格式。",
                    )


def validate_cos_path_format_in_database() -> None:
    """校验数据库中所有表的 location 格式。

    遍历所有 share → schema → table 记录，检查 location 是否为
    cosn://bucket/key 格式。任意表格式无效即抛出 DeltaSharingError
    并拒绝启动。

    此函数必须在 init_database() 之后调用，因为它需要查询数据库。
    由 main() 在数据库初始化后显式调用。

    Raises:
        DeltaSharingError: 当数据库中任意表的 location 格式无效时抛出。
    """
    from app.repositories.share_repository import ShareRepository

    repo = ShareRepository()
    all_shares = repo.list_shares()

    invalid_tables = []
    for share in all_shares:
        share_name = share["share_name"]
        all_tables = repo.get_all_tables_for_share(share_name)
        for schema_name, tables in all_tables.items():
            for table_name, table_data in tables.items():
                location = (table_data.get("location") or "").strip()
                if location and not location.startswith("cosn://"):
                    invalid_tables.append(f"{share_name}.{schema_name}.{table_name}: '{location}'")

    if invalid_tables:
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            f"数据库中存在 {len(invalid_tables)} 个表的 location 格式无效"
            f"（必须为 cosn://bucket/key 格式）: "
            + "; ".join(invalid_tables[:10])
            + ("..." if len(invalid_tables) > 10 else ""),
        )


def _validate_cos_credentials(config: Config) -> None:
    """校验 COS 凭证完整性。

    COS 的 secret_id 和 secret_key 必须同时为空或同时非空，
    不允许只配置其中一个。

    Args:
        config: 全局配置对象。

    Raises:
        DeltaSharingError: 当 COS 凭证不配对时抛出。
    """
    cos_id = (config.cos.secret_id or "").strip()
    cos_key = (config.cos.secret_key or "").strip()

    has_id = bool(cos_id)
    has_key = bool(cos_key)

    if has_id != has_key:
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            "COS_SECRET_ID and COS_SECRET_KEY must both be set or both be empty",
        )

    if has_id and has_key:
        logger.info("COS 凭证已完整配置")
    else:
        logger.info("COS 凭证未配置，COS 功能将在后续请求中按需初始化")


def _validate_dlc_credentials(config: Config) -> None:
    """校验 DLC 凭证完整性。

    DLC 的 secret_id 和 secret_key 必须同时为空或同时非空，
    不允许只配置其中一个。

    Args:
        config: 全局配置对象。

    Raises:
        DeltaSharingError: 当 DLC 凭证不配对时抛出。
    """
    dlc_id = (config.dlc.secret_id or "").strip()
    dlc_key = (config.dlc.secret_key or "").strip()

    has_id = bool(dlc_id)
    has_key = bool(dlc_key)

    if has_id != has_key:
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            "DLC_SECRET_ID and DLC_SECRET_KEY must both be set or both be empty",
        )

    if has_id and has_key:
        logger.info("DLC 凭证已完整配置")
    else:
        logger.info("DLC 凭证未配置，DLC 功能降级不可用")


def _validate_database_url(config: Config) -> None:
    """校验数据库 URL 配置。

    数据库 URL 必须为非空字符串。

    Args:
        config: 全局配置对象。

    Raises:
        DeltaSharingError: 当数据库 URL 为空时抛出。
    """
    db_url = (config.database.url or "").strip()

    if not db_url:
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            "Database URL must be a non-empty string",
        )

    logger.info(f"数据库 URL 配置有效: {db_url}")


def _validate_pool_config(config: Config) -> None:
    """校验连接池配置参数合法性。

    pool_type 仅接受 "null_pool" 或 "queue_pool"，
    各数值参数需在合法范围内。

    Args:
        config: 全局配置对象。

    Raises:
        DeltaSharingError: 当连接池配置非法时抛出。
    """
    pool = config.database.pool
    valid_pool_types = ("null_pool", "queue_pool")
    if pool.pool_type not in valid_pool_types:
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            f"Invalid pool_type: '{pool.pool_type}'. Must be one of: {', '.join(valid_pool_types)}",
        )
    if not (1 <= pool.pool_size <= 100):
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            f"pool_size must be between 1 and 100, got {pool.pool_size}",
        )
    if not (0 <= pool.max_overflow <= 200):
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            f"max_overflow must be between 0 and 200, got {pool.max_overflow}",
        )
    if pool.pool_recycle != -1 and not (1 <= pool.pool_recycle <= 86400):
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            f"pool_recycle must be -1 or between 1 and 86400, got {pool.pool_recycle}",
        )
    if not (1 <= pool.pool_timeout <= 60):
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            f"pool_timeout must be between 1 and 60, got {pool.pool_timeout}",
        )

    logger.info(
        f"连接池配置有效: pool_type={pool.pool_type}, "
        f"pool_size={pool.pool_size}, max_overflow={pool.max_overflow}, "
        f"pool_recycle={pool.pool_recycle}s, pool_timeout={pool.pool_timeout}s, "
        f"pool_pre_ping={pool.pool_pre_ping}"
    )


def _validate_page_token_secret(config: Config) -> None:
    """校验 PAGE_TOKEN_SECRET 配置。

    production 模式（ENV=production 或 ENV 未设置）下，未配置 PAGE_TOKEN_SECRET
    时拒绝启动；development 模式（ENV=development）下生成随机密钥并输出 WARNING。

    Args:
        config: 全局配置对象。

    Raises:
        DeltaSharingError: production 模式下未配置 PAGE_TOKEN_SECRET 时抛出。
    """
    secret = (config.token.page_token_secret or "").strip()
    env = (os.environ.get("ENV", "") or "").strip().lower()

    if not secret:
        if env == "development":
            config.token.page_token_secret = secrets.token_hex(32)
            logger.warning(
                "PAGE_TOKEN_SECRET 未设置，已生成随机临时密钥。"
                "生产环境请通过环境变量 PAGE_TOKEN_SECRET 配置固定密钥，"
                "否则每次重启服务后所有旧 page token 将失效"
            )
        else:
            raise DeltaSharingError(
                ErrorCode.INVALID_PARAMETER_VALUE,
                "PAGE_TOKEN_SECRET is not configured. "
                "Please set the PAGE_TOKEN_SECRET environment variable "
                "before starting the server in production mode. "
                "Run 'scripts/setup_env.ps1' (Windows) or "
                "'scripts/setup_env.sh' (Linux) to generate a secure secret. "
                "To skip this check in development, set ENV=development.",
            )
    else:
        logger.info("PAGE_TOKEN_SECRET 已配置")


def _validate_all_config(config: Config) -> None:
    """执行所有配置校验。

    依次校验 COS 凭证、DLC 凭证、数据库 URL 和 COS 路径格式。
    任意一项校验失败即抛出 DeltaSharingError 并拒绝启动。

    Args:
        config: 全局配置对象。

    Raises:
        DeltaSharingError: 当任意配置校验失败时抛出。
    """
    _validate_cos_credentials(config)
    _validate_dlc_credentials(config)
    _validate_database_url(config)
    _validate_pool_config(config)
    _validate_cos_path_format(config)
    _validate_page_token_secret(config)
