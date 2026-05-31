"""
Share 模型模块

该模块定义了 Delta Sharing 的核心资源模型：Share、Schema 和 Table。
这些是 Delta Sharing 协议中用于组织和管理数据共享的基本结构。
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Share(BaseModel):
    """Share 模型

    Share 是数据共享的最高层容器，用于组织相关的 Schema。

    Attributes:
        name: Share 的名称。
        id: Share 的唯一标识符（可选）。
        display_name: 显示名称（可选）。
        comment: 描述说明（可选）。
        properties: 键值对属性（可选）。
    """

    name: str
    id: Optional[str] = Field(default=None, alias="id")
    display_name: Optional[str] = Field(default=None, alias="displayName")
    comment: Optional[str] = Field(default=None, alias="comment")
    properties: Optional[Dict[str, str]] = Field(default=None, alias="properties")

    model_config = {"populate_by_name": True}


class ShareResponse(BaseModel):
    """Get Share 响应模型

    根据 Delta Sharing 协议，Get Share API 返回包含 share 对象的包装。

    Attributes:
        share: Share 对象。
    """

    share: Share


class Schema(BaseModel):
    """Schema 模型

    Schema 是 Share 下的中间层容器，用于组织相关的 Table。

    Attributes:
        name: Schema 的名称。
        share: 所属 Share 的名称。
    """

    name: str
    share: str


class Table(BaseModel):
    """Table 模型

    Table 是 Share 和 Schema 下的数据表，包含实际的共享数据。

    Attributes:
        name: 表的名称。
        schema: 所属 Schema 的名称。
        share: 所属 Share 的名称。
        id: 表的唯一标识符（UUID 格式）。
        share_id: 所属 Share 的唯一标识符（可选）。
        location: 表的存储位置路径（可选）。
        auxiliary_locations: 辅助存储位置列表（可选）。
        access_modes: 支持的访问模式列表（可选）。
    """

    name: str
    schema: str
    share: str
    id: str = Field(alias="id")
    share_id: Optional[str] = Field(default=None, alias="shareId")
    location: Optional[str] = Field(default=None, alias="location")
    auxiliary_locations: Optional[List[str]] = Field(
        default=None, alias="auxiliaryLocations"
    )
    access_modes: Optional[List[str]] = Field(default=None, alias="accessModes")

    model_config = {"populate_by_name": True}


class TableMetadata(BaseModel):
    """表元数据模型

    包含 Iceberg 表的详细元数据信息。

    Attributes:
        id: 表的唯一标识符。
        format: 数据格式，默认为 "parquet"。
        schema_string: 表结构的 JSON 字符串表示。
        partition_columns: 分区列名称列表。
        access_mode: 访问模式，默认为 "URL"。
    """

    id: str
    format: str = "parquet"
    schema_string: str
    partition_columns: List[str] = []
    access_mode: str = "URL"


class ShareListResponse(BaseModel):
    """Share 列表响应模型

    Attributes:
        items: Share 对象列表。
        next_page_token: 下一页令牌（如果有分页）。
    """

    items: List[Share]
    next_page_token: Optional[str] = None


class SchemaListResponse(BaseModel):
    """Schema 列表响应模型

    Attributes:
        items: Schema 对象列表。
        next_page_token: 下一页令牌（如果有分页）。
    """

    items: List[Schema]
    next_page_token: Optional[str] = None


class TableListResponse(BaseModel):
    """Table 列表响应模型

    Attributes:
        items: Table 对象列表。
        next_page_token: 下一页令牌（如果有分页）。
    """

    items: List[Table]
    next_page_token: Optional[str] = None


class AllTablesListResponse(BaseModel):
    """所有表列表响应模型

    用于列出某个 Share 下所有 Schema 中的表。

    Attributes:
        items: Table 对象列表。
        next_page_token: 下一页令牌（如果有分页）。
    """

    items: List[Table]
    next_page_token: Optional[str] = None
