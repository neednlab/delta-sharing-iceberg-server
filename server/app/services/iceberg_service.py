"""
Iceberg 服务模块

该模块提供 Iceberg 表的核心操作功能，包括：
- IcebergSchemaConverter: Iceberg schema 转换工具，将 Iceberg schema 转换为 Delta Sharing 格式
- IcebergService: Iceberg 表元数据和数据文件管理服务

主要功能：
- 获取表元数据和 schema 信息
- 获取当前快照和历史快照
- 读取数据文件和清单列表
- 检查是否存在删除文件
"""

import json
import re
import io
import uuid
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger

from pyiceberg.schema import Schema as IcebergSchema
from pyiceberg.types import (
    BinaryType,
    BooleanType,
    DateType,
    DecimalType,
    DoubleType,
    FixedType,
    FloatType,
    IntegerType,
    ListType,
    LongType,
    MapType,
    NestedField,
    PrimitiveType,
    StringType,
    StructType,
    TimeType,
    TimestampType,
    TimestamptzType,
    UUIDType,
)


class _ShortType(PrimitiveType):
    """短整型占位类型（pyiceberg 未内置 short/byte 类型，此处自定义以支持协议规范的序列化）"""

    pass


class _ByteType(PrimitiveType):
    """字节整型占位类型"""

    pass


from avro.datafile import DataFileReader
from avro.io import DatumReader
import fastavro

from app.core.config import get_config
from app.core.cos_client import get_cos_client
from app.core.dlc_client import init_dlc_client, DLCClientWrapper, DLCAPIError
from app.core.database import get_database
from app.core.errors import DeltaSharingError, ErrorCode
from app.core.cache import (
    _metadata_location_cache,
    _metadata_content_cache,
    _manifest_list_cache,
    _manifest_cache,
    _sync_flag_cache,
)


class IcebergSchemaConverter:
    """Iceberg Schema 转换器

    将 Iceberg schema 转换为 Delta Sharing 协议兼容的 JSON schema 格式。

    Methods:
        convert_schema: 将 Iceberg schema 转换为 JSON 字符串。
        convert_primitive: 转换基本类型字段。
        convert_struct: 转换结构体类型字段。
        convert_list: 转换列表类型字段。
        convert_map: 转换映射类型字段。
    """

    @staticmethod
    def _parse_field_type(type_str: str) -> Any:
        """解析字段类型字符串为 Iceberg 类型对象。

        Args:
            type_str: 类型字符串（如 "int", "string", "decimal(10,2)"）。

        Returns:
            对应的 Iceberg 类型对象。
        """
        type_str = type_str.strip()
        if type_str in ("bool", "boolean"):
            return BooleanType()
        elif type_str in ("int", "integer"):
            return IntegerType()
        elif type_str == "short":
            return _ShortType()
        elif type_str == "byte":
            return _ByteType()
        elif type_str in ("long", "bigint"):
            return LongType()
        elif type_str in ("float", "float32"):
            return FloatType()
        elif type_str in ("double", "float64"):
            return DoubleType()
        elif type_str == "date":
            return DateType()
        elif type_str in ("timestamp", "timestamp_ms"):
            return TimestampType()
        elif type_str in ("timestamptz", "timestamptz_ms"):
            return TimestamptzType()
        elif type_str == "time":
            return TimeType()
        elif type_str == "uuid":
            return UUIDType()
        elif type_str == "string":
            return StringType()
        elif type_str in ("binary", "fixed"):
            return BinaryType()
        elif type_str.startswith("decimal") or type_str.startswith("numeric"):
            match = re.match(r"(?:decimal|numeric)\(\s*(\d+)\s*,\s*(\d+)\s*\)", type_str)
            if match:
                precision = int(match.group(1))
                scale = int(match.group(2))
                return DecimalType(precision=precision, scale=scale)
            return DecimalType(precision=10, scale=2)
        elif type_str == "struct":
            return StructType(fields=[])
        elif type_str == "list":
            return ListType(element_id=0, element_type=StringType(), element_required=True)
        elif type_str == "map":
            return MapType(
                key_id=0,
                key_type=StringType(),
                value_id=1,
                value_type=StringType(),
                value_required=True,
            )
        return StringType()

    @staticmethod
    def _parse_field_type_any(type_value: Any) -> Any:
        """解析任意格式的字段类型值为 Iceberg 类型对象。

        支持两种格式：
        1. 简单字符串：如 "int", "string", "decimal(10,2)"
        2. Iceberg 元数据 JSON 嵌套 dict：如 {"type": "list", "element": "string", ...}

        Args:
            type_value: 类型值（字符串或嵌套 dict）。

        Returns:
            对应的 Iceberg 类型对象。
        """
        if isinstance(type_value, str):
            return IcebergSchemaConverter._parse_field_type(type_value)

        if not isinstance(type_value, dict):
            return StringType()

        type_name = type_value.get("type", "")

        if type_name == "fixed":
            return FixedType(length=type_value.get("length", 0))
        elif type_name == "list":
            element_type = IcebergSchemaConverter._parse_field_type_any(
                type_value.get("element", "string")
            )
            element_id = type_value.get("element-id", type_value.get("element_id", 0))
            element_required = type_value.get(
                "element-required", type_value.get("element_required", True)
            )
            return ListType(
                element_id=element_id,
                element_type=element_type,
                element_required=element_required,
            )
        elif type_name == "struct":
            fields_list = []
            for idx, f in enumerate(type_value.get("fields", [])):
                sub_type = IcebergSchemaConverter._parse_field_type_any(f.get("type", "string"))
                fields_list.append(
                    NestedField(
                        field_id=f.get("id", idx + 1),
                        name=f.get("name", f"field_{idx}"),
                        field_type=sub_type,
                        required=f.get("required", False),
                    )
                )
            return StructType(fields=tuple(fields_list))
        elif type_name == "map":
            key_type = IcebergSchemaConverter._parse_field_type_any(type_value.get("key", "string"))
            value_type = IcebergSchemaConverter._parse_field_type_any(
                type_value.get("value", "string")
            )
            key_id = type_value.get("key-id", type_value.get("key_id", 0))
            value_id = type_value.get("value-id", type_value.get("value_id", 1))
            value_required = type_value.get(
                "value-required", type_value.get("value_required", True)
            )
            return MapType(
                key_id=key_id,
                key_type=key_type,
                value_id=value_id,
                value_type=value_type,
                value_required=value_required,
            )
        elif type_name == "decimal" or type_name == "numeric":
            return DecimalType(
                precision=type_value.get("precision", 10),
                scale=type_value.get("scale", 2),
            )

        return IcebergSchemaConverter._parse_field_type(type_name)

    @staticmethod
    def _type_value(field_type: Any) -> Any:
        """递归获取字段类型在协议中的 type 属性值。

        基本类型返回类型名字符串（如 "integer", "string"），
        复杂类型返回嵌套的 type 对象（如 {"type": "struct", "fields": [...]}）。

        Args:
            field_type: Iceberg 类型对象（StructType/ListType/MapType/基本类型等）。

        Returns:
            协议兼容的类型值（字符串或嵌套 dict）。
        """
        if isinstance(field_type, StructType):
            fields = []
            for sub_field in field_type.fields:
                fields.append(
                    {
                        "name": sub_field.name,
                        "type": IcebergSchemaConverter._type_value(sub_field.field_type),
                        "nullable": not sub_field.required,
                        "metadata": {},
                    }
                )
            return {"type": "struct", "fields": fields}
        elif isinstance(field_type, ListType):
            return {
                "type": "array",
                "elementType": IcebergSchemaConverter._type_value(field_type.element_type),
                "containsNull": not field_type.element_field.required,
            }
        elif isinstance(field_type, MapType):
            return {
                "type": "map",
                "keyType": IcebergSchemaConverter._type_value(field_type.key_type),
                "valueType": IcebergSchemaConverter._type_value(field_type.value_type),
                "valueContainsNull": not field_type.value_required,
            }

        if isinstance(field_type, BooleanType):
            return "boolean"
        elif isinstance(field_type, IntegerType):
            return "integer"
        elif isinstance(field_type, _ShortType):
            return "short"
        elif isinstance(field_type, _ByteType):
            return "byte"
        elif isinstance(field_type, LongType):
            return "long"
        elif isinstance(field_type, FloatType):
            return "float"
        elif isinstance(field_type, DoubleType):
            return "double"
        elif isinstance(field_type, DateType):
            return "date"
        elif isinstance(field_type, TimestampType):
            return "timestamp"
        elif isinstance(field_type, TimestamptzType):
            return "timestamp"
        elif isinstance(field_type, TimeType):
            return "long"
        elif isinstance(field_type, UUIDType):
            return "string"
        elif isinstance(field_type, StringType):
            return "string"
        elif isinstance(field_type, BinaryType):
            return "binary"
        elif isinstance(field_type, FixedType):
            return "binary"
        elif isinstance(field_type, DecimalType):
            return f"decimal({field_type.precision},{field_type.scale})"

        return "string"

    @staticmethod
    def convert_primitive(field: NestedField) -> Dict[str, Any]:
        """转换基本类型字段。

        Args:
            field: Iceberg 嵌套字段对象。

        Returns:
            符合协议规范的字段字典，type 属性为类型名字符串。
        """
        return {
            "type": IcebergSchemaConverter._type_value(field.field_type),
            "name": field.name,
            "nullable": not field.required,
            "metadata": {},
        }

    @staticmethod
    def convert_struct(
        struct_type: StructType, name: str, is_nullable: bool = False
    ) -> Dict[str, Any]:
        """转换结构体类型字段。

        Args:
            struct_type: Iceberg 结构体类型。
            name: 字段名称。
            is_nullable: 是否可为空。

        Returns:
            符合协议规范的字段字典，type 属性为嵌套的 struct type 对象。
        """
        return {
            "type": IcebergSchemaConverter._type_value(struct_type),
            "name": name,
            "nullable": is_nullable,
            "metadata": {},
        }

    @staticmethod
    def convert_list(list_type: ListType, name: str, is_nullable: bool = False) -> Dict[str, Any]:
        """转换列表类型字段。

        Args:
            list_type: Iceberg 列表类型。
            name: 字段名称。
            is_nullable: 是否可为空。

        Returns:
            符合协议规范的字段字典，type 属性为嵌套的 array type 对象，
            elementType 为递归生成的类型值（基本类型为字符串，复杂类型为嵌套对象）。
        """
        return {
            "type": IcebergSchemaConverter._type_value(list_type),
            "name": name,
            "nullable": is_nullable,
            "metadata": {},
        }

    @staticmethod
    def convert_map(map_type: MapType, name: str, is_nullable: bool = False) -> Dict[str, Any]:
        """转换映射类型字段。

        Args:
            map_type: Iceberg 映射类型。
            name: 字段名称。
            is_nullable: 是否可为空。

        Returns:
            符合协议规范的字段字典，type 属性为嵌套的 map type 对象，
            keyType/valueType 为递归生成的类型值（基本类型为字符串，
            复杂类型为嵌套对象）。
        """
        return {
            "type": IcebergSchemaConverter._type_value(map_type),
            "name": name,
            "nullable": is_nullable,
            "metadata": {},
        }

    @classmethod
    def convert_schema(cls, iceberg_schema: IcebergSchema) -> str:
        """将 Iceberg schema 转换为 JSON 字符串。

        Args:
            iceberg_schema: Iceberg schema 对象。

        Returns:
            JSON 格式的 schema 字符串。
        """
        fields = []
        for field in iceberg_schema.fields:
            if isinstance(field.field_type, StructType):
                fields.append(cls.convert_struct(field.field_type, field.name, not field.required))
            elif isinstance(field.field_type, ListType):
                fields.append(cls.convert_list(field.field_type, field.name, not field.required))
            elif isinstance(field.field_type, MapType):
                fields.append(cls.convert_map(field.field_type, field.name, not field.required))
            else:
                fields.append(cls.convert_primitive(field))

        schema_json = {"type": "struct", "fields": fields}

        return json.dumps(schema_json)


class IcebergService:
    """Iceberg 服务类

    该类提供 Iceberg 表的核心操作功能，包括：
    - 表元数据获取（通过 DLC API 或 COS）
    - 快照管理（当前快照、历史快照）
    - 数据文件和清单列表读取
    - 删除文件检查

    Attributes:
        config: 全局配置实例。
        cos_client: COS 客户端实例。
        db: 数据库实例。
        _dlc_client: DLC 客户端实例。

    Note:
        使用 contextvars 实现请求级缓存：同一请求内的多次查询会复用缓存，
        但跨请求不会共享缓存，确保每次请求都能获取最新的 metadata_location。
    """

    def __init__(self):
        """初始化 Iceberg 服务。"""
        self.config = get_config()
        self.cos_client = get_cos_client()
        self.db = get_database()
        self._dlc_client: Optional[DLCClientWrapper] = None
        self._init_dlc_client()

        # 延迟导入避免循环依赖
        from app.services.version_service import VersionService

        self._version_service = VersionService()

    def _init_dlc_client(self) -> None:
        """初始化 DLC 客户端。"""
        if self.config.dlc.secret_id and self.config.dlc.secret_key:
            logger.info(
                f"Initializing DLC client with region='{self.config.dlc.region}', endpoint='{self.config.dlc.endpoint}'"
            )
            self._dlc_client = init_dlc_client(self.config.dlc)
        else:
            logger.warning(
                "DLC credentials not configured. Set DLC_SECRET_ID, DLC_SECRET_KEY, DLC_REGION environment variables."
            )

    def _get_table_cache_key(self, share_name: str, schema_name: str, table_name: str) -> str:
        """生成表缓存键。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。

        Returns:
            缓存键字符串，格式为 "share.schema.table"。
        """
        return f"{share_name}.{schema_name}.{table_name}"

    def _get_metadata_location_via_dlc(
        self, share_name: str, schema_name: str, table_name: str
    ) -> Optional[str]:
        """通过 DLC API 获取表的元数据位置。

        使用请求级缓存：同一请求内的多次查询会复用缓存，
        但跨请求不会共享缓存，确保每次请求都能获取最新的 metadata_location。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。

        Returns:
            元数据位置 URL，如果获取失败则返回 None。
        """
        cache_key = self._get_table_cache_key(share_name, schema_name, table_name)
        cached = _metadata_location_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using request-cached metadata_location for table {cache_key}")
            return cached

        if not self._dlc_client:
            return None

        table_config = self._get_table_config(share_name, schema_name, table_name)
        if not table_config:
            return None

        database_name = (
            table_config.get("metastore_db")
            if isinstance(table_config, dict)
            else table_config.metastore_db
        )
        if not database_name:
            database_name = schema_name

        table_name_for_dlc = (
            table_config.get("metastore_table")
            if isinstance(table_config, dict)
            else table_config.metastore_table
        )
        if not table_name_for_dlc:
            table_name_for_dlc = table_name

        try:
            logger.info(
                f"Calling DLC DescribeTable API: database='{database_name}', table='{table_name_for_dlc}'"
            )
            api_response = self._dlc_client.describe_table(database_name, table_name_for_dlc)
            metadata_location = DLCClientWrapper.extract_metadata_location(api_response)
            if metadata_location:
                _metadata_location_cache.set(cache_key, metadata_location)
                logger.info(f"DLC API returned metadata_location: {metadata_location}")
            else:
                logger.warning(f"DLC API response missing metadata_location: {api_response}")
            return metadata_location
        except DLCAPIError as e:
            logger.exception(f"DLC API call failed for {share_name}.{schema_name}.{table_name}")
            raise DeltaSharingError(
                error_code=ErrorCode.DLC_API_ERROR,
                message=f"DLC API error for {share_name}.{schema_name}.{table_name}: {str(e)}",
                status_code=502,
            )
        except Exception as e:
            logger.exception(
                f"Unexpected error calling DLC API for {share_name}.{schema_name}.{table_name}"
            )
            raise DeltaSharingError(
                error_code=ErrorCode.DLC_API_ERROR,
                message=f"DLC API error for {share_name}.{schema_name}.{table_name}: {str(e)}",
                status_code=502,
            )

    def _convert_cos_path(self, cos_path: str) -> str:
        """转换 COS 路径格式。

        将 cosn://bucket/key 格式转换为 key 格式。

        Args:
            cos_path: COS 路径。

        Returns:
            转换后的 key 字符串。
        """
        if cos_path.startswith("cosn://"):
            path_part = cos_path[len("cosn://") :]
            parts = path_part.split("/", 1)
            if len(parts) > 1:
                return parts[1]
            return ""
        return cos_path

    def _parse_cos_path(self, cos_path: str) -> tuple[str, str]:
        """解析 COS 路径。

        将 cosn://bucket/key 格式解析为 (bucket, key) 元组。

        Args:
            cos_path: COS 路径，格式为 cosn://bucket/key。

        Returns:
            (bucket, key) 元组。

        Raises:
            ValueError: 当 cos_path 格式无效时抛出。
        """
        if not cos_path:
            raise ValueError("cos_path is empty")
        if cos_path.startswith("cosn://"):
            path_part = cos_path[len("cosn://") :]
            parts = path_part.split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
            return bucket, key
        raise ValueError(f"Invalid cos_path format: {cos_path}")

    def _get_metadata_json_path(self, cos_path: str) -> str:
        """获取元数据 JSON 文件路径。

        Args:
            cos_path: COS 路径。

        Returns:
            元数据 JSON 文件路径。
        """
        if cos_path.startswith("cosn://"):
            path_part = cos_path[len("cosn://") :]
            parts = path_part.split("/", 1)
            if len(parts) > 1:
                key = parts[1]
            else:
                key = ""
            return key
        if cos_path.endswith("/"):
            return cos_path.rstrip("/")
        return cos_path

    def _load_metadata_from_cos(
        self,
        cos_path: str,
        share_name: Optional[str] = None,
        schema_name: Optional[str] = None,
        table_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从 COS 加载表元数据。

        Args:
            cos_path: 表在 COS 中的路径。
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。

        Returns:
            元数据字典。

        Raises:
            DeltaSharingError: 参数缺失或获取元数据失败时抛出。
        """
        if not share_name or not schema_name or not table_name:
            raise DeltaSharingError(
                error_code=ErrorCode.TABLE_NOT_FOUND,
                message="DLC API requires share_name, schema_name, and table_name",
                status_code=400,
            )

        metadata_location = self._get_metadata_location_via_dlc(share_name, schema_name, table_name)
        if not metadata_location:
            raise DeltaSharingError(
                error_code=ErrorCode.TABLE_NOT_FOUND,
                message=f"Cannot obtain metadata_location from DLC API for table {share_name}.{schema_name}.{table_name}. "
                f"Check DLC_SECRET_ID, DLC_SECRET_KEY, DLC_REGION environment variables are configured correctly.",
                status_code=404,
            )

        metadata = self._load_metadata_from_location(metadata_location)

        # 每次元数据加载后自动同步所有 snapshot 到 snapshot_version 表
        self._sync_all_snapshots_to_version_table(share_name, schema_name, table_name, metadata)

        return metadata

    def _load_metadata_from_location(self, metadata_location: str) -> Dict[str, Any]:
        """从指定位置加载元数据（带请求级缓存）。

        优先从请求级缓存读取已下载的 metadata JSON 内容，
        缓存未命中时才从 COS 下载，命中时直接返回缓存的解析结果。

        Args:
            metadata_location: 元数据文件位置（cosn://bucket/key 格式）。

        Returns:
            元数据字典。

        Raises:
            DeltaSharingError: 访问或解析元数据文件失败时抛出。
        """
        bucket, metadata_key = self._parse_cos_path(metadata_location)
        cache_key = f"{bucket}/{metadata_key}"

        # 请求级缓存检查：同一请求内同一 metadata 文件仅下载一次
        cached = _metadata_content_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT: metadata key={cache_key}")
            return cached

        logger.debug(f"Cache MISS: metadata key={cache_key}  → downloading from COS")

        try:
            response = self.cos_client.get_object(bucket, metadata_key)
        except Exception as e:
            raise DeltaSharingError(
                error_code=ErrorCode.TABLE_NOT_FOUND,
                message=f"Failed to access metadata file at {metadata_location}: {str(e)}",
                status_code=404,
            )

        if response is None:
            raise DeltaSharingError(
                error_code=ErrorCode.TABLE_NOT_FOUND,
                message=f"Metadata file not found at {metadata_location}",
                status_code=404,
            )

        try:
            if isinstance(response, bytes):
                metadata_str = response.decode("utf-8")
            else:
                metadata_str = response

            metadata = json.loads(metadata_str)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise DeltaSharingError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Failed to parse metadata JSON from {metadata_location}: {str(e)}",
                status_code=500,
            )

        # 将解析结果存入请求级缓存
        _metadata_content_cache.set(cache_key, metadata)
        return metadata

    def _sync_all_snapshots_to_version_table(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        metadata: Dict[str, Any],
    ) -> None:
        """将 metadata JSON 中所有 snapshot 同步到 snapshot_version 表。

        每次元数据加载后自动调用，遍历 snapshots 数组按 timestamp-ms 升序
        逐个调用 get_or_allocate_version() 幂等写入。已存在的 snapshot 会被跳过。
        利用请求级 _sync_flag_cache 缓存标记，同一请求内同一表仅同步一次。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            metadata: Iceberg 元数据字典，包含 snapshots 数组。
        """
        cache_key = self._get_table_cache_key(share_name, schema_name, table_name)

        # 请求级去重：同一请求内同一表仅同步一次
        if _sync_flag_cache.get(cache_key) is not None:
            logger.debug(f"Snapshot sync already performed for {cache_key}, skipping")
            return

        snapshots = metadata.get("snapshots", [])
        if not snapshots:
            logger.debug(f"No snapshots found in metadata for {cache_key}, skipping sync")
            _sync_flag_cache.set(cache_key, True)
            return

        # 按 timestamp-ms 升序排序，确保最早 snapshot 获得最小 version
        sorted_snapshots = sorted(snapshots, key=lambda s: s.get("timestamp-ms", 0) or 0)

        synced_count = 0
        for snapshot in sorted_snapshots:
            snapshot_id = snapshot.get("snapshot-id")
            timestamp_ms = int(snapshot.get("timestamp-ms", 0) or 0)
            if snapshot_id is not None:
                version = self._version_service.get_or_allocate_version(
                    share_name, schema_name, table_name, snapshot_id, timestamp_ms
                )
                logger.debug(
                    f"Snapshot sync: {cache_key} snapshot_id={snapshot_id} → version={version}"
                )
                synced_count += 1

        logger.info(
            f"Snapshot sync completed for {cache_key}: "
            f"{synced_count} snapshots processed (total in metadata: {len(sorted_snapshots)})"
        )
        _sync_flag_cache.set(cache_key, True)

    def get_current_snapshot_id(
        self, share_name: str, schema_name: str, table_name: str
    ) -> Optional[int]:
        """获取当前快照 ID。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。

        Returns:
            当前快照 ID，如果不存在则返回 None。
        """
        table_config = self._get_table_config(share_name, schema_name, table_name)
        if not table_config:
            return None

        metadata = self._load_metadata_from_cos(
            table_config["location"], share_name, schema_name, table_name
        )

        current_snapshot_id = metadata.get("current-snapshot-id")
        if current_snapshot_id is None:
            snapshots = metadata.get("snapshots", [])
            if snapshots:
                current_snapshot_id = snapshots[-1].get("snapshot-id")

        return current_snapshot_id

    def get_snapshot_by_id(
        self, share_name: str, schema_name: str, table_name: str, snapshot_id: int
    ) -> Optional[Dict[str, Any]]:
        """根据 ID 获取指定快照。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            snapshot_id: 快照 ID。

        Returns:
            快照信息字典，如果未找到则返回 None。
        """
        table_config = self._get_table_config(share_name, schema_name, table_name)
        if not table_config:
            return None

        metadata = self._load_metadata_from_cos(
            table_config["location"], share_name, schema_name, table_name
        )

        snapshots = metadata.get("snapshots", [])
        for snapshot in snapshots:
            if snapshot.get("snapshot-id") == snapshot_id:
                return snapshot

        return None

    def get_current_snapshot(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        table_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取表的当前快照。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            table_config: 预加载的表配置字典，若为 None 则内部加载。
            metadata: 预加载的 Iceberg 元数据字典，若为 None 则内部加载。

        Returns:
            快照信息字典，如果未找到则返回 None。
        """
        if table_config is None:
            table_config = self._get_table_config(share_name, schema_name, table_name)
        if not table_config:
            return None

        if metadata is None:
            metadata = self._load_metadata_from_cos(
                table_config["location"], share_name, schema_name, table_name
            )

        current_snapshot_id = metadata.get("current-snapshot-id")
        snapshots = metadata.get("snapshots", [])
        if current_snapshot_id is None:
            if snapshots:
                current_snapshot_id = snapshots[-1].get("snapshot-id")
                return snapshots[-1]

        current_snapshot_id_int = (
            int(current_snapshot_id) if current_snapshot_id is not None else None
        )
        for snapshot in snapshots:
            snapshot_id = snapshot.get("snapshot-id")
            if snapshot_id is not None and int(snapshot_id) == current_snapshot_id_int:
                return snapshot

        return None

    def get_schema_string(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        table_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """获取表的 schema 字符串。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            table_config: 预加载的表配置字典，若为 None 则内部加载。
            metadata: 预加载的 Iceberg 元数据字典，若为 None 则内部加载。

        Returns:
            JSON 格式的 schema 字符串，如果获取失败则返回 None。
        """
        if table_config is None:
            table_config = self._get_table_config(share_name, schema_name, table_name)
        if not table_config:
            return None

        if metadata is None:
            metadata = self._load_metadata_from_cos(
                table_config["location"], share_name, schema_name, table_name
            )

        schemas = metadata.get("schemas", [])
        current_schema_id = metadata.get("current-schema-id")

        if current_schema_id is None and schemas:
            current_schema_id = schemas[0].get("schema-id")

        for schema in schemas:
            if schema.get("schema-id") == current_schema_id:
                fields = schema.get("fields", [])
                fields_list = []
                for f in fields:
                    try:
                        field_type = IcebergSchemaConverter._parse_field_type_any(f["type"])
                        fields_list.append(
                            NestedField(
                                field_id=f["id"],
                                name=f["name"],
                                field_type=field_type,
                                required=f.get("required", False),
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to parse field '{}' (id={}) in table {}.{}.{}: {}",
                            f.get("name", "unknown"),
                            f.get("id", "unknown"),
                            share_name,
                            schema_name,
                            table_name,
                            e,
                        )

                iceberg_schema = IcebergSchema(
                    schema_id=current_schema_id, fields=tuple(fields_list)
                )

                return IcebergSchemaConverter.convert_schema(iceberg_schema)

        return None

    def get_partition_columns(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        table_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """获取表的分区列。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            table_config: 预加载的表配置字典，若为 None 则内部加载。
            metadata: 预加载的 Iceberg 元数据字典，若为 None 则内部加载。

        Returns:
            分区列名称列表。
        """
        if table_config is None:
            table_config = self._get_table_config(share_name, schema_name, table_name)
        if not table_config:
            return []

        if metadata is None:
            metadata = self._load_metadata_from_cos(
                table_config["location"], share_name, schema_name, table_name
            )

        partition_specs = metadata.get("partition-specs", [])
        default_spec_id = metadata.get("default-spec-id")

        for spec in partition_specs:
            if spec.get("spec-id") == default_spec_id:
                fields = spec.get("fields", [])
                return [f.get("name", f"column_{i}") for i, f in enumerate(fields)]

        partition_spec = metadata.get("partition-spec")
        if partition_spec:
            fields = partition_spec.get("fields", [])
            return [f.get("name", f"column_{i}") for i, f in enumerate(fields)]

        return []

    def _get_cached_metadata(
        self, share_name: str, schema_name: str, table_name: str
    ) -> Optional[Dict[str, Any]]:
        """从请求级缓存中获取已加载的 metadata JSON 内容。

        根据表的 metadata_location（优先从 _metadata_location_cache 获取，
        缓存未命中时通过 DLC API 获取）构建缓存键，从 _metadata_content_cache
        中获取已缓存的 metadata dict。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。

        Returns:
            缓存的 metadata 字典，如果缓存未命中则返回 None。
        """
        cache_key_for_location = self._get_table_cache_key(share_name, schema_name, table_name)
        metadata_location = _metadata_location_cache.get(cache_key_for_location)

        if not metadata_location:
            metadata_location = self._get_metadata_location_via_dlc(
                share_name, schema_name, table_name
            )

        if not metadata_location:
            return None

        bucket, metadata_key = self._parse_cos_path(metadata_location)
        cache_key = f"{bucket}/{metadata_key}"
        return _metadata_content_cache.get(cache_key)

    def get_table_metadata(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        table_config: Optional[Dict[str, Any]] = None,
        preloaded_data_files: Optional[List[Dict[str, Any]]] = None,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取表的完整元数据。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            table_config: 预加载的表配置字典，若为 None 则内部加载。
            preloaded_data_files: 预加载的数据文件列表。当调用方在之前已通过
                get_data_files() 获取了数据文件列表时，可通过此参数传入，
                避免方法内部重复调用 get_data_files() 导致的额外 manifest 扫描。
                若为 None，方法内部将自行调用 get_data_files() 获取。
            snapshot: 预加载的快照信息字典，若为 None 则内部通过
                get_current_snapshot() 获取。

        Returns:
            包含表元数据的字典，包含 id、format、schema_string、partition_columns、
            location、auxiliary_locations、access_modes、configuration、size、num_files。
        """
        if table_config is None:
            table_config = self._get_table_config(share_name, schema_name, table_name)
        if not table_config:
            return None

        metadata = self._load_metadata_from_cos(
            table_config["location"], share_name, schema_name, table_name
        )

        if snapshot is None:
            snapshot = self.get_current_snapshot(
                share_name,
                schema_name,
                table_name,
                table_config=table_config,
                metadata=metadata,
            )
        if not snapshot:
            return None

        snapshot_id = snapshot.get("snapshot-id")

        schema_string = self.get_schema_string(
            share_name,
            schema_name,
            table_name,
            table_config=table_config,
            metadata=metadata,
        )
        if not schema_string:
            return None

        partition_columns = self.get_partition_columns(
            share_name,
            schema_name,
            table_name,
            table_config=table_config,
            metadata=metadata,
        )

        table_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{share_name}.{schema_name}.{table_name}"))

        if preloaded_data_files is not None:
            data_files = preloaded_data_files
        else:
            data_files, _ = self.get_data_files(
                share_name,
                schema_name,
                table_name,
                snapshot_id,
                table_config=table_config,
                metadata=metadata,
            )

        total_size = sum(f.get("file_size", 0) for f in data_files)
        num_files = len(data_files)

        configuration = metadata.get("properties", {})

        return {
            "id": table_id,
            "format": "parquet",
            "schema_string": schema_string,
            "partition_columns": partition_columns,
            "location": table_config.get("location"),
            "auxiliary_locations": [],
            "access_modes": ["url"],
            "configuration": configuration,
            "size": total_size,
            "num_files": num_files,
        }

    def _parse_avro_manifest(self, bucket: str, manifest_path: str) -> List[Dict[str, Any]]:
        """解析 Avro 格式的清单文件（带请求级缓存）。

        优先从请求级缓存读取已解析的 manifest 条目列表，
        缓存未命中时才从 COS 下载并 fastavro 解析。

        Args:
            bucket: COS 存储桶名称。
            manifest_path: 清单文件路径（cosn://bucket/key 格式）。

        Returns:
            清单条目列表。
        """
        manifest_key = self._convert_cos_path(manifest_path)
        cache_key = f"{bucket}/{manifest_key}"

        # 请求级缓存检查：同一请求内同一 manifest 文件仅下载一次
        cached = _manifest_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT: manifest key={cache_key}")
            return cached

        logger.debug(f"Cache MISS: manifest key={cache_key}  → downloading from COS")

        entries = []
        manifest_bytes = self.cos_client.get_object(bucket, manifest_key)
        if not manifest_bytes:
            return []

        try:
            bio = io.BytesIO(manifest_bytes)
            reader = fastavro.reader(bio)
            for entry in reader:
                entries.append(entry)
        except Exception as fastavro_err:
            logger.warning(
                f"fastavro failed to parse manifest {manifest_path}: {str(fastavro_err)}"
            )
            try:
                with DataFileReader(io.BytesIO(manifest_bytes), DatumReader()) as reader:
                    for entry in reader:
                        entries.append(dict(entry))
            except Exception as avro_err:
                logger.exception(f"Both fastavro and avro failed to parse manifest {manifest_path}")
                raise DeltaSharingError(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to parse manifest file: {manifest_path}",
                    status_code=500,
                    details={
                        "fastavro_error": str(fastavro_err),
                        "avro_error": str(avro_err),
                    },
                )

        if entries:
            logger.debug(
                f"Parsed {len(entries)} entries from manifest {manifest_path}, first entry keys: {entries[0].keys() if entries else 'none'}"
            )
            first_entry = entries[0]
            logger.debug(f"First entry: {first_entry}")

        # 将解析结果存入请求级缓存
        _manifest_cache.set(cache_key, entries)
        return entries

    def _get_manifest_list_entries(self, bucket: str, manifest_list_path: str) -> List[str]:
        """获取清单列表中的所有清单文件路径（带请求级缓存）。

        优先从请求级缓存读取已解析的 manifest-list 内容，
        缓存未命中时才从 COS 下载并 Avro 解析。

        Args:
            bucket: COS 存储桶名称。
            manifest_list_path: 清单列表文件路径（cosn://bucket/key 格式）。

        Returns:
            清单文件路径列表。
        """
        manifest_list_key = self._convert_cos_path(manifest_list_path)
        cache_key = f"{bucket}/{manifest_list_key}"

        # 请求级缓存检查：同一请求内同一 manifest-list 仅下载一次
        cached = _manifest_list_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache HIT: manifest_list key={cache_key}")
            return cached

        logger.debug(f"Cache MISS: manifest_list key={cache_key}  → downloading from COS")

        manifest_paths = []
        manifest_bytes = self.cos_client.get_object(bucket, manifest_list_key)
        if not manifest_bytes:
            return []

        try:
            bio = io.BytesIO(manifest_bytes)
            reader = fastavro.reader(bio)
            for entry in reader:
                manifest_path = entry.get("manifest_path")
                if manifest_path:
                    manifest_paths.append(manifest_path)
        except Exception as fastavro_err:
            logger.warning(
                f"fastavro failed to parse manifest list {manifest_list_path}: {str(fastavro_err)}"
            )
            try:
                with DataFileReader(io.BytesIO(manifest_bytes), DatumReader()) as reader:
                    for entry in reader:
                        manifest_path = entry.get("manifest_path")
                        if manifest_path:
                            manifest_paths.append(manifest_path)
            except Exception as avro_err:
                logger.exception(
                    f"Both fastavro and avro failed to parse manifest list {manifest_list_path}"
                )
                raise DeltaSharingError(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to parse manifest list file: {manifest_list_path}",
                    status_code=500,
                    details={
                        "fastavro_error": str(fastavro_err),
                        "avro_error": str(avro_err),
                    },
                )

        # 将解析结果存入请求级缓存
        _manifest_list_cache.set(cache_key, manifest_paths)
        return manifest_paths

    def _get_field_id_mapping(self, metadata: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
        """构建字段 ID 到字段名称和类型的映射。

        从 Iceberg 表元数据的 schemas 中获取当前 schema 的字段信息，
        构建 {field_id: {"name": "col_name", "type": "int"}} 格式的映射。

        Args:
            metadata: Iceberg 表元数据字典。

        Returns:
            字段 ID 到字段信息的映射字典。
        """
        mapping: Dict[int, Dict[str, Any]] = {}
        schemas = metadata.get("schemas", [])
        current_schema_id = metadata.get("current-schema-id")
        if current_schema_id is None and schemas:
            current_schema_id = schemas[0].get("schema-id")

        for schema in schemas:
            if schema.get("schema-id") == current_schema_id:
                for f in schema.get("fields", []):
                    field_id = f.get("id")
                    if field_id is not None:
                        mapping[int(field_id)] = {
                            "name": f.get("name", f"col_{field_id}"),
                            "type": f.get("type", "string"),
                        }
                break
        return mapping

    @staticmethod
    def _decode_lower_upper_bound(raw_value, field_type: str):
        """解析 Iceberg manifest 中的 lower_bounds/upper_bounds 二进制值。

        Iceberg 将 min/max 统计信息以二进制格式存储在 manifest 中。
        本函数根据字段类型解码这些二进制值。

        Args:
            raw_value: 原始二进制值（bytes 或 bytearray）。
            field_type: Iceberg 字段类型字符串（如 "int", "long", "string" 等）。

        Returns:
            解码后的 Python 值，如果解码失败则返回 None。
        """
        if raw_value is None:
            return None
        if not isinstance(raw_value, (bytes, bytearray)):
            return raw_value

        try:
            import struct

            if field_type in ("int", "integer"):
                if len(raw_value) >= 4:
                    return struct.unpack("<i", raw_value[:4])[0]
            elif field_type in ("long", "bigint"):
                if len(raw_value) >= 8:
                    return struct.unpack("<q", raw_value[:8])[0]
            elif field_type == "time":
                if len(raw_value) >= 8:
                    return struct.unpack("<q", raw_value[:8])[0]
            elif field_type in ("float", "float32"):
                if len(raw_value) >= 4:
                    return struct.unpack("<f", raw_value[:4])[0]
            elif field_type in ("double", "float64"):
                if len(raw_value) >= 8:
                    return struct.unpack("<d", raw_value[:8])[0]
            elif field_type == "string":
                return raw_value.decode("utf-8")
            elif field_type in ("uuid", "binary", "fixed"):
                return raw_value.hex()
            elif field_type == "date":
                if len(raw_value) >= 4:
                    return struct.unpack("<i", raw_value[:4])[0]
            elif field_type in (
                "timestamp",
                "timestamp_ms",
                "timestamptz",
                "timestamptz_ms",
            ):
                if len(raw_value) >= 8:
                    return struct.unpack("<q", raw_value[:8])[0]
            elif field_type == "boolean":
                return raw_value[0] != 0 if raw_value else False
        except (struct.error, UnicodeDecodeError, IndexError) as e:
            logger.debug(f"Failed to decode bound for type {field_type}: {e}")
        return None

    @staticmethod
    def _normalize_bound_map(raw_value):
        """将 Avro 反序列化的 bound map 转换为统一的 {field_id: value} dict 格式。

        fastavro 可能将 Avro map 类型反序列化为 Python dict 或 list 格式：
        - dict: {1: b'\\x01\\x00\\x00\\x00', 2: b'...'}  (key → value 直接映射)
        - list: [{'key': 1, 'value': b'\\x01\\x00\\x00\\x00'}, ...]  (key-value 记录列表)

        本方法统一处理两种格式，始终返回 dict 格式。

        Args:
            raw_value: fastavro 反序列化后的原始 bound 值。

        Returns:
            {field_id: value} 格式的字典，如果无法解析则返回空字典。
        """
        if isinstance(raw_value, dict):
            result = {}
            for k, v in raw_value.items():
                try:
                    result[int(k)] = v
                except (ValueError, TypeError):
                    pass
            return result
        if isinstance(raw_value, list):
            result = {}
            for item in raw_value:
                if isinstance(item, dict) and "key" in item and "value" in item:
                    try:
                        result[int(item["key"])] = item["value"]
                    except (ValueError, TypeError):
                        pass
            return result
        return {}

    def get_data_files(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        snapshot_id: int,
        table_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """获取指定快照的数据文件列表，同时检测是否存在删除文件。

        在单次 manifest 遍历中同时完成数据文件收集和删除文件检测，
        避免对 manifest-list 和全量 manifest 的重复扫描。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            snapshot_id: 快照 ID。
            table_config: 预加载的表配置字典，若为 None 则内部加载。
            metadata: 预加载的 Iceberg 元数据字典，若为 None 则内部加载。

        Returns:
            (data_files, has_delete_files) 元组：
            - data_files: 数据文件信息列表，每个文件包含 file_path、file_size、
              record_count、partition_values、min_values、max_values、null_count。
            - has_delete_files: 是否检测到删除文件（content=1 或 content=2 的 entry）。
        """
        if table_config is None:
            table_config = self._get_table_config(share_name, schema_name, table_name)
        if not table_config:
            return [], False

        if metadata is None:
            metadata = self._load_metadata_from_cos(
                table_config["location"], share_name, schema_name, table_name
            )

        # 构建字段 ID 到名称和类型的映射，用于解码文件统计信息
        field_id_mapping = self._get_field_id_mapping(metadata)

        snapshots = metadata.get("snapshots", [])
        target_snapshot = None
        snapshot_id_int = int(snapshot_id) if snapshot_id is not None else None
        for snapshot in snapshots:
            snap_id = snapshot.get("snapshot-id")
            if snap_id is not None and int(snap_id) == snapshot_id_int:
                target_snapshot = snapshot
                break

        if not target_snapshot:
            return [], False

        manifest_list_location = target_snapshot.get("manifest-list")
        if not manifest_list_location:
            return [], False

        bucket, _ = self._parse_cos_path(manifest_list_location)
        manifest_paths = self._get_manifest_list_entries(bucket, manifest_list_location)

        data_files = []
        has_delete_files = False

        table_location = table_config.get("location", "").rstrip("/")

        for manifest_path in manifest_paths:
            entries = self._parse_avro_manifest(bucket, manifest_path)
            for entry in entries:
                # 同步检测删除文件：content=1 为 position delete，content=2 为 equality delete
                content = entry.get("content")
                if content == 1 or content == 2:
                    has_delete_files = True

                entry_status = entry.get("status")
                if entry_status == 2:
                    continue

                data_file = entry.get("data_file")
                if not data_file or not isinstance(data_file, dict):
                    continue

                file_path = data_file.get("file_path")
                if not file_path:
                    logger.warning(f"No file_path found in data_file: {data_file}")
                    continue

                if not file_path.startswith("cosn://"):
                    file_path = f"{table_location}/data/{file_path}"

                partition_values = data_file.get("partition", {})
                if not isinstance(partition_values, dict):
                    partition_values = {}

                # 提取文件级统计信息（lower_bounds, upper_bounds, null_value_counts）
                min_values = {}
                max_values = {}
                null_counts = {}

                raw_lower_bounds = data_file.get("lower_bounds")
                raw_upper_bounds = data_file.get("upper_bounds")
                raw_null_counts = data_file.get("null_value_counts")

                lower_bounds = self._normalize_bound_map(raw_lower_bounds)
                upper_bounds = self._normalize_bound_map(raw_upper_bounds)
                null_value_counts = self._normalize_bound_map(raw_null_counts)

                for fid, raw_val in lower_bounds.items():
                    field_info = field_id_mapping.get(fid)
                    if field_info:
                        col_name = field_info["name"]
                        decoded = self._decode_lower_upper_bound(raw_val, field_info["type"])
                        if decoded is not None:
                            min_values[col_name] = decoded

                for fid, raw_val in upper_bounds.items():
                    field_info = field_id_mapping.get(fid)
                    if field_info:
                        col_name = field_info["name"]
                        decoded = self._decode_lower_upper_bound(raw_val, field_info["type"])
                        if decoded is not None:
                            max_values[col_name] = decoded

                for fid, count in null_value_counts.items():
                    field_info = field_id_mapping.get(fid)
                    if field_info:
                        null_counts[field_info["name"]] = count

                logger.debug(
                    f"[STATS_DIAG] file={file_path} | "
                    f"min_values={min_values} | "
                    f"max_values={max_values} | "
                    f"null_counts={null_counts} | "
                    f"partition={partition_values}"
                )

                data_files.append(
                    {
                        "file_path": file_path,
                        "file_size": data_file.get("file_size_in_bytes", 0),
                        "record_count": data_file.get("record_count", 0),
                        "partition_values": partition_values,
                        "min_values": min_values,
                        "max_values": max_values,
                        "null_count": null_counts,
                    }
                )

        logger.info(
            f"Total data files found: {len(data_files)} "
            f"for table {share_name}.{schema_name}.{table_name}"
        )
        return data_files, has_delete_files

    def build_file_objects(
        self,
        filtered_files: List[Dict[str, Any]],
        table_config: Dict[str, Any],
        snapshot: Dict[str, Any],
        current_version: int,
        query_version: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """构建查询响应的文件对象列表。

        为每个过滤后的数据文件生成预签名 COS URL、SHA256 ID、
        统计信息和过期时间戳，组装为符合 Delta Sharing 协议的文件对象。

        注意: COS 预签名 URL 生成是纯本地 HMAC-SHA1 计算，零网络 I/O，
        因此使用简单串行循环而非线程池并发，避免不必要的调度开销。

        支持时间旅行查询：当 query_version 不为 None 时，
        File 对象的 version 字段使用 query_version（历史版本号），
        timestamp 使用历史快照的时间戳。

        Args:
            filtered_files: 过滤后的数据文件列表。
            table_config: 表配置字典，包含 bucket、region 等信息。
            snapshot: 当前快照字典，包含 timestamp 信息。
            current_version: 当前表版本号。
            query_version: 时间旅行查询时的历史版本号（可选）。

        Returns:
            文件对象字典列表，每个包含 url、id、partitionValues、
            size、stats、version、timestamp、expirationTimestamp。
        """
        if not filtered_files:
            return []

        expiration_hours = self.config.presigned_url.expiration_hours
        expiration_timestamp = int((datetime.now().timestamp() + expiration_hours * 3600) * 1000)

        bucket = table_config.get("bucket", "")

        display_version = query_version if query_version is not None else current_version

        file_objects = []
        for f in filtered_files:
            file_path = f.get("file_path")
            if not file_path:
                continue

            key = self._convert_cos_path(file_path)
            url = self.cos_client.generate_presigned_url(
                bucket=bucket,
                key=key,
                method="GET",
                expiration_hours=expiration_hours,
            )

            file_id = hashlib.sha256(file_path.encode()).hexdigest()

            stats_dict = {}
            if "record_count" in f:
                stats_dict["numRecords"] = f["record_count"]
            if "min_values" in f:
                stats_dict["minValues"] = f["min_values"]
            if "max_values" in f:
                stats_dict["maxValues"] = f["max_values"]
            if "null_count" in f:
                stats_dict["nullCount"] = f["null_count"]

            stats_str = json.dumps(stats_dict) if stats_dict else None

            file_obj = {
                "url": url,
                "id": file_id,
                "partitionValues": f.get("partition_values", {}),
                "size": f.get("file_size"),
                "stats": stats_str,
                "version": display_version,
                "timestamp": int(snapshot.get("timestamp-ms", 0)),
                "expirationTimestamp": expiration_timestamp,
            }

            file_objects.append(file_obj)

        logger.info(f"Built {len(file_objects)} file objects (expiration_hours={expiration_hours})")
        return file_objects

    def _get_table_config(
        self, share_name: str, schema_name: str, table_name: str
    ) -> Optional[Dict[str, Any]]:
        """获取表配置信息。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。

        Returns:
            包含 location、metastore_db、metastore_table、bucket、region 的字典。
        """
        from app.core.config import get_table_config

        config = get_table_config(share_name, schema_name, table_name)
        if config:
            location = config.location
            if location:
                bucket, _ = self._parse_cos_path(location)
            else:
                bucket = ""
            return {
                "location": location,
                "metastore_db": config.metastore_db,
                "metastore_table": config.metastore_table,
                "bucket": bucket,
                "region": self.config.cos.region,
            }
        return None
