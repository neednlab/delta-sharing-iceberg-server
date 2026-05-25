"""
Query 模型模块

该模块定义了 Delta Sharing 查询请求和响应的数据模型。
包括协议版本、元数据、表文件信息等。
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class QueryRequest(BaseModel):
    """查询请求模型

    客户端发送的表查询请求参数。
    符合 Delta Sharing 协议 Query Table API 规范。

    Attributes:
        predicateHints: 谓词提示列表（JSON 字符串数组格式）。
        jsonPredicateHints: JSON 格式的谓词提示字符串。
        limitHint: 返回文件数量限制提示。
        version: 表版本号，用于时间旅行查询。
        timestamp: 时间戳字符串，用于时间旅行查询。
        startingVersion: 起始版本号，用于CDF查询。
        endingVersion: 结束版本号，用于CDF查询。
    """

    predicateHints: Optional[List[str]] = None
    jsonPredicateHints: Optional[str] = None
    limitHint: Optional[int] = None
    version: Optional[int] = None
    timestamp: Optional[str] = None
    startingVersion: Optional[int] = None
    endingVersion: Optional[int] = None


class Protocol(BaseModel):
    """协议版本模型

    定义 Delta Sharing 协议的版本信息。

    Attributes:
        minReaderVersion: 最小读取器版本号，默认为 1。
    """

    minReaderVersion: int = 1


class Metadata(BaseModel):
    """表元数据模型

    包含表的结构信息和格式配置。
    符合 Delta Sharing 协议规范。

    Attributes:
        id: 表的唯一标识符。
        format: 数据格式配置，默认为 {"provider": "parquet"}。
        schemaString: 表 schema 的 JSON 字符串表示。
        partitionColumns: 分区列名称列表。
        location: 表的根目录路径。
        auxiliaryLocations: 辅助存储位置列表。
        accessModes: 支持的访问模式列表（url 和/或 dir）。
        configuration: 表配置选项映射。
        size: 表的大小（字节）。
        numFiles: 表的文件数量。
    """

    id: str
    format: Dict[str, Any] = {"provider": "parquet"}
    schemaString: str
    partitionColumns: List[str] = []
    location: Optional[str] = None
    auxiliaryLocations: Optional[List[str]] = None
    accessModes: Optional[List[str]] = None
    configuration: Optional[Dict[str, str]] = None
    size: Optional[int] = None
    numFiles: Optional[int] = None


class FileData(BaseModel):
    """文件数据模型

    表示表中单个数据文件的信息。
    符合 Delta Sharing 协议 File 对象规范。

    Attributes:
        url: 文件的预签名访问 URL。
        id: 文件的唯一标识符。
        partitionValues: 分区值字典。
        size: 文件大小（字节）。
        stats: 文件统计信息的 JSON 字符串，包含 numRecords、minValues、maxValues、nullCount 等。
        version: 表版本号，时间旅行查询时返回。
        timestamp: 文件时间戳（毫秒），时间旅行查询时返回。
        expirationTimestamp: URL 过期时间戳（毫秒）。
    """

    url: str
    id: str
    partitionValues: Dict[str, Any] = {}
    size: Optional[int] = None
    stats: Optional[str] = None
    version: Optional[int] = None
    timestamp: Optional[int] = None
    expirationTimestamp: Optional[int] = None


class QueryResponse(BaseModel):
    """查询响应模型

    包含完整查询响应的所有信息：协议、元数据和文件列表。

    Attributes:
        protocol: 协议版本信息。
        metadata: 表元数据信息。
        files: 数据文件列表。
    """

    protocol: Protocol
    metadata: Metadata
    files: List[FileData]
