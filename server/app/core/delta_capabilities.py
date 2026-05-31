"""
Delta Sharing Capabilities 模块

该模块处理 Delta Sharing 协议中的 delta-sharing-capabilities header。
支持的功能包括:
- responseFormat: 指定响应格式 (parquet 或 delta)
- readerFeatures: 客户端支持的 delta reader 特性
- includeEndStreamAction: 是否在响应中包含 EndStreamAction

参考协议文档: Delta Sharing Protocol - Delta Sharing Capabilities Header
"""

from dataclasses import dataclass, field
from typing import Optional, Set, Dict, Any
from enum import Enum


class ResponseFormat(str, Enum):
    """响应格式枚举"""

    PARQUET = "parquet"
    DELTA = "delta"


@dataclass
class DeltaSharingCapabilities:
    """Delta Sharing Capabilities 数据类

    用于解析和存储 delta-sharing-capabilities header 的内容。

    Attributes:
        response_format: 请求的响应格式，默认 parquet
        reader_features: 客户端支持的 reader features 集合
        include_end_stream_action: 是否在响应中包含 EndStreamAction
    """

    response_format: ResponseFormat = ResponseFormat.PARQUET
    reader_features: Set[str] = None
    include_end_stream_action: bool = False

    def __post_init__(self):
        if self.reader_features is None:
            self.reader_features = set()

    def to_response_header(self) -> str:
        """生成服务器端响应使用的 capabilities header 字符串。

        Returns:
            格式化的 capabilities header 值。
        """
        parts = [f"responseFormat={self.response_format.value}"]

        if self.reader_features:
            features_str = ",".join(sorted(self.reader_features))
            parts.append(f"readerFeatures={features_str}")

        parts.append(f"includeEndStreamAction={str(self.include_end_stream_action).lower()}")

        return ";".join(parts)


def parse_delta_sharing_capabilities(
    header_value: Optional[str],
) -> DeltaSharingCapabilities:
    """解析 delta-sharing-capabilities header 值。

    Header 格式示例:
    "responseFormat=delta;readerfeatures=deletionvectors,columnmapping;includeEndStreamAction=true"

    Args:
        header_value: delta-sharing-capabilities header 的原始值。

    Returns:
        DeltaSharingCapabilities 对象，包含解析后的能力信息。
    """
    capabilities = DeltaSharingCapabilities()
    temp_include_end_stream_action = False
    temp_response_format = None

    if not header_value:
        return capabilities

    parts = header_value.split(";")
    for part in parts:
        part = part.strip()
        if not part:
            continue

        if "=" not in part:
            continue

        key, _, value = part.partition("=")
        key = key.strip().lower()
        value = value.strip()

        if key == "responseformat":
            original_value = value.lower()
            if "," in original_value:
                formats = [f.strip() for f in original_value.split(",") if f.strip()]
                if ResponseFormat.PARQUET.value in formats:
                    temp_response_format = ResponseFormat.PARQUET
                elif ResponseFormat.DELTA.value in formats:
                    temp_response_format = ResponseFormat.DELTA
                else:
                    temp_response_format = ResponseFormat.PARQUET
            else:
                if original_value in [
                    ResponseFormat.PARQUET.value,
                    ResponseFormat.DELTA.value,
                ]:
                    temp_response_format = ResponseFormat(original_value)
                else:
                    temp_response_format = ResponseFormat.PARQUET

        elif key == "readerfeatures":
            features = [f.strip().lower() for f in value.split(",") if f.strip()]
            capabilities.reader_features = set(features)

        elif key == "includeendstreamaction":
            temp_include_end_stream_action = value.lower() == "true"

    if temp_include_end_stream_action and temp_response_format == ResponseFormat.PARQUET:
        capabilities.include_end_stream_action = False
        capabilities.response_format = ResponseFormat.PARQUET
    else:
        capabilities.include_end_stream_action = temp_include_end_stream_action
        capabilities.response_format = (
            temp_response_format if temp_response_format else ResponseFormat.PARQUET
        )

    return capabilities


def get_default_capabilities() -> DeltaSharingCapabilities:
    """获取默认的 Delta Sharing Capabilities。

    Returns:
        默认的 DeltaSharingCapabilities 对象。
    """
    return DeltaSharingCapabilities(
        response_format=ResponseFormat.PARQUET,
        reader_features=set(),
        include_end_stream_action=False,
    )


@dataclass
class EndStreamAction:
    """EndStreamAction 响应对象

    用于在流式响应结束时返回给客户端的控制信息。

    Attributes:
        refresh_token: 用于刷新预签名 URL 的令牌（可选）。
        next_page_token: 用于分页请求的下一页令牌（可选）。
        min_url_expiration_timestamp: 响应中所有 URL 的最早过期时间戳（可选）。
        error_message: 服务器错误信息（可选）。
    """

    refresh_token: Optional[str] = None
    next_page_token: Optional[str] = None
    min_url_expiration_timestamp: Optional[int] = None
    error_message: Optional[str] = None

    def to_json_dict(self) -> dict:
        """转换为 JSON 字典。

        Returns:
            可序列化的字典。
        """
        result = {}
        if self.refresh_token is not None:
            result["refreshToken"] = self.refresh_token
        if self.next_page_token is not None:
            result["nextPageToken"] = self.next_page_token
        if self.min_url_expiration_timestamp is not None:
            result["minUrlExpirationTimestamp"] = self.min_url_expiration_timestamp
        if self.error_message is not None:
            result["errorMessage"] = self.error_message
        return result

    def to_delta_dict(self) -> dict:
        """转换为 Delta 格式的字典。

        Returns:
            Delta 格式的 endStreamAction 字典。
        """
        inner = {}
        if self.refresh_token is not None:
            inner["refreshToken"] = self.refresh_token
        if self.next_page_token is not None:
            inner["nextPageToken"] = self.next_page_token
        if self.min_url_expiration_timestamp is not None:
            inner["minUrlExpirationTimestamp"] = self.min_url_expiration_timestamp
        if self.error_message is not None:
            inner["errorMessage"] = self.error_message
        return {"endStreamAction": inner}


@dataclass
class DeltaProtocol:
    """Delta Protocol 数据类

    用于生成 Delta 格式响应的 protocol wrapper。

    Attributes:
        min_reader_version: Delta 协议的最小读取器版本。
        min_writer_version: Delta 协议的最小写入器版本。
    """

    min_reader_version: int = 1
    min_writer_version: int = 2

    def to_delta_dict(self) -> dict:
        """转换为 Delta 格式的协议对象。

        返回的格式为 {"protocol": {"deltaProtocol": {...}}}。

        Returns:
            Delta 格式的 protocol 字典。
        """
        return {
            "protocol": {
                "deltaProtocol": {
                    "minReaderVersion": self.min_reader_version,
                    "minWriterVersion": self.min_writer_version,
                }
            }
        }


@dataclass
class DeltaMetadata:
    """Delta Metadata 数据类

    用于生成 Delta 格式响应的 metadata wrapper。

    Attributes:
        id: 表的唯一标识符。
        format: 文件格式信息。
        schema_string: 表的 schema JSON 字符串。
        partition_columns: 分区列列表。
        location: 表的位置。
        auxiliary_locations: 辅助位置列表。
        configuration: 表配置。
        size: 表大小。
        num_files: 文件数量。
    """

    id: str = ""
    format: Dict[str, str] = field(default_factory=lambda: {"provider": "parquet"})
    schema_string: str = "{}"
    partition_columns: list = field(default_factory=list)
    location: Optional[str] = None
    auxiliary_locations: list = field(default_factory=list)
    configuration: Dict[str, str] = field(default_factory=dict)
    size: Optional[int] = None
    num_files: Optional[int] = None

    def to_delta_dict(self) -> dict:
        """转换为 Delta 格式的 metadata 对象。

        返回的格式为 {"metaData": {"deltaMetadata": {...}, ...其他字段}}。

        Returns:
            Delta 格式的 metadata 字典。
        """
        return {
            "metaData": {
                "deltaMetadata": {
                    "id": self.id,
                    "format": self.format,
                    "schemaString": self.schema_string,
                    "partitionColumns": self.partition_columns,
                    "configuration": self.configuration,
                },
                "size": self.size,
                "numFiles": self.num_files,
                "location": self.location,
                "auxiliaryLocations": self.auxiliary_locations,
            }
        }


@dataclass
class DeltaFileAction:
    """Delta File Action 数据类

    用于生成 Delta 格式响应的 file wrapper，包装单个文件信息。

    Attributes:
        url: 文件的预签名 URL。
        id: 文件的唯一标识符。
        partition_values: 分区值字典。
        size: 文件大小。
        stats: 文件统计信息。
        version: 表版本。
        timestamp: 时间戳。
        expiration_timestamp: URL 过期时间戳。
    """

    url: str = ""
    id: str = ""
    partition_values: Dict[str, Any] = field(default_factory=dict)
    size: Optional[int] = None
    stats: Optional[str] = None
    version: Optional[int] = None
    timestamp: Optional[int] = None
    expiration_timestamp: Optional[int] = None

    def to_delta_dict(self) -> dict:
        """转换为 Delta 格式的文件对象。

        返回的格式为 {"file": {"id": ..., "size": ..., "expirationTimestamp": ..., "deltaSingleAction": {"add": {...}}}}。

        Returns:
            Delta 格式的 file 字典。
        """
        return {
            "file": {
                "id": self.id,
                "size": self.size,
                "expirationTimestamp": self.expiration_timestamp,
                "deltaSingleAction": {
                    "add": {
                        "path": self.url,
                        "partitionValues": self.partition_values,
                        "stats": self.stats,
                    }
                },
            }
        }
