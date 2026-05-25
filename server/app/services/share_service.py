"""
Share 服务模块

该模块提供 Share、Schema 和 Table 的列表查询功能。
支持分页查询和名称过滤。
"""

import uuid
from typing import Optional, Dict, Any
from app.core.config import (
    get_all_shares,
    get_share_all_tables,
    get_share_schemas,
    get_schema_tables,
)
from app.core.authentication import normalize_name
from app.core.errors import DeltaSharingError, ErrorCode
from app.utils.page_token_utils import (
    encode_page_token as _encode_page_token,
    decode_page_token as _decode_page_token,
)


def _generate_table_id(share_name: str, schema_name: str, table_name: str) -> str:
    """生成表的 UUID 格式 ID。

    Args:
        share_name: Share 名称。
        schema_name: Schema 名称。
        table_name: 表名称。

    Returns:
        基于表名称的 UUID 字符串。
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{share_name}.{schema_name}.{table_name}"))


def _generate_share_id(share_name: str) -> str:
    """生成 Share 的 UUID 格式 ID。

    Args:
        share_name: Share 名称。

    Returns:
        基于 Share 名称的 UUID 字符串。
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"share:{share_name}"))


class ShareService:
    """Share 服务类

    该类提供 Delta Sharing 中 Share、Schema 和 Table 的列表查询功能。
    从配置中读取共享资源信息，支持分页返回。

    Methods:
        list_shares: 列出所有 Share。
        list_schemas: 列出指定 Share 下的所有 Schema。
        list_tables: 列出指定 Schema 下的所有 Table。
        list_all_tables: 列出指定 Share 下的所有 Table（跨 Schema）。
        share_exists: 检查 Share 是否存在。
        schema_exists: 检查 Schema 是否存在。
        table_exists: 检查 Table 是否存在。
    """

    def list_shares(
        self,
        max_results: Optional[int] = None,
        page_token: Optional[str] = None,
        recipient_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """列出所有可用的 Share。

        Args:
            max_results: 最大返回数量。
            page_token: 分页令牌（不透明的令牌字符串）。
            recipient_id: 可选的 recipient ID，用于过滤授权的 shares。

        Returns:
            包含 items 和 next_page_token 的字典。
        """
        all_shares = get_all_shares()

        if recipient_id:
            from app.services.authorization_service import AuthorizationService

            auth_service = AuthorizationService()
            authorized_shares = auth_service.get_recipient_shares(recipient_id)
            share_names = sorted([s for s in all_shares.keys() if s in authorized_shares])
        else:
            share_names = sorted(all_shares.keys())

        offset = 0
        if page_token:
            decoded_offset = _decode_page_token(page_token)
            if decoded_offset is not None:
                offset = decoded_offset
                share_names = share_names[offset:]

        if max_results and max_results > 0:
            shares_subset = share_names[offset : offset + max_results]
            next_offset = offset + len(shares_subset)
            next_token = _encode_page_token(next_offset) if next_offset < len(share_names) else None
        else:
            shares_subset = share_names[offset:]
            next_token = None

        items = []
        for name in shares_subset:
            share_config = all_shares[name]
            item = {"name": name}
            if share_config.id:
                item["id"] = share_config.id
            if share_config.display_name:
                item["displayName"] = share_config.display_name
            if share_config.comment:
                item["comment"] = share_config.comment
            if share_config.properties:
                item["properties"] = share_config.properties
            items.append(item)

        return {"items": items, "next_page_token": next_token}

    def list_schemas(
        self, share_name: str, max_results: Optional[int] = None, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """列出指定 Share 下的所有 Schema。

        Args:
            share_name: Share 名称。
            max_results: 最大返回数量。
            page_token: 分页令牌（不透明的令牌字符串）。

        Returns:
            包含 items 和 next_page_token 的字典，如果 Share 不存在则返回 None。
        """
        share_name_lower = normalize_name(share_name)
        schemas = get_share_schemas(share_name_lower)

        if not schemas:
            raise DeltaSharingError(
                error_code=ErrorCode.SCHEMA_NOT_FOUND,
                message=f"No schemas found in share: {share_name}",
                status_code=404,
            )

        schema_names = sorted(schemas.keys())

        offset = 0
        if page_token:
            decoded_offset = _decode_page_token(page_token)
            if decoded_offset is not None:
                offset = decoded_offset
                schema_names = schema_names[offset:]

        if max_results and max_results > 0:
            schemas_subset = schema_names[:max_results]
            next_offset = offset + len(schemas_subset)
            next_token = _encode_page_token(next_offset) if next_offset < len(schemas) else None
        else:
            schemas_subset = schema_names
            next_token = None

        items = [{"name": name, "share": share_name} for name in schemas_subset]

        return {"items": items, "next_page_token": next_token}

    def list_tables(
        self,
        share_name: str,
        schema_name: str,
        max_results: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """列出指定 Schema 下的所有 Table。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            max_results: 最大返回数量。
            page_token: 分页令牌（不透明的令牌字符串）。

        Returns:
            包含 items 和 next_page_token 的字典，如果 Schema 不存在则返回 None。
        """
        share_name_lower = normalize_name(share_name)
        schema_name_lower = normalize_name(schema_name)

        tables = get_schema_tables(share_name_lower, schema_name_lower)

        if not tables:
            raise DeltaSharingError(
                error_code=ErrorCode.TABLE_NOT_FOUND,
                message=f"No tables found in schema: {schema_name}",
                status_code=404,
            )

        table_names = sorted(tables.keys())

        offset = 0
        if page_token:
            decoded_offset = _decode_page_token(page_token)
            if decoded_offset is not None:
                offset = decoded_offset
                table_names = table_names[offset:]

        if max_results and max_results > 0:
            tables_subset = table_names[:max_results]
            next_offset = offset + len(tables_subset)
            next_token = _encode_page_token(next_offset) if next_offset < len(tables) else None
        else:
            tables_subset = table_names
            next_token = None

        items = [
            {
                "name": name,
                "schema": schema_name,
                "share": share_name,
                "id": _generate_table_id(share_name, schema_name, name),
                "shareId": _generate_share_id(share_name),
            }
            for name in tables_subset
        ]

        for i, name in enumerate(tables_subset):
            table_config = tables[name.lower()]
            if table_config.location:
                items[i]["location"] = table_config.location
            if table_config.auxiliary_locations:
                items[i]["auxiliaryLocations"] = table_config.auxiliary_locations
            if table_config.access_modes:
                items[i]["accessModes"] = table_config.access_modes

        return {"items": items, "next_page_token": next_token}

    def list_all_tables(
        self, share_name: str, max_results: Optional[int] = None, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """列出指定 Share 下所有 Schema 中的所有 Table。

        支持直绑表（linked_schema_id 为 NULL）和关联表（linked_schema_id 指向
        shared_schemas 实体）。直绑表的 schema_name 取自 shared_tables.schema_name
        字段，关联表的 schema_name 取自 shared_schemas.schema_name 字段。

        Args:
            share_name: Share 名称。
            max_results: 最大返回数量。
            page_token: 分页令牌（不透明的令牌字符串）。

        Returns:
            包含 items 和 next_page_token 的字典，如果 Share 下没有任何表则返回 None。
        """
        share_name_lower = normalize_name(share_name)
        all_tables_nested = get_share_all_tables(share_name_lower)

        if not all_tables_nested:
            raise DeltaSharingError(
                error_code=ErrorCode.TABLE_NOT_FOUND,
                message=f"No tables found in share: {share_name}",
                status_code=404,
            )

        all_tables = []
        for schema_name_lower, tables_dict in all_tables_nested.items():
            for table_name_lower, table_config in tables_dict.items():
                table_item = {
                    "name": table_name_lower,
                    "schema": schema_name_lower,
                    "share": share_name,
                    "id": _generate_table_id(share_name, schema_name_lower, table_name_lower),
                    "shareId": _generate_share_id(share_name),
                }
                if table_config.location:
                    table_item["location"] = table_config.location
                if table_config.auxiliary_locations:
                    table_item["auxiliaryLocations"] = table_config.auxiliary_locations
                if table_config.access_modes:
                    table_item["accessModes"] = table_config.access_modes
                all_tables.append(table_item)

        all_tables.sort(key=lambda x: (x["schema"], x["name"]))

        total_tables = len(all_tables)
        offset = 0
        if page_token:
            decoded_offset = _decode_page_token(page_token)
            if decoded_offset is not None:
                offset = decoded_offset
                all_tables = all_tables[offset:]

        if max_results and max_results > 0:
            tables_subset = all_tables[:max_results]
            next_offset = offset + len(tables_subset)
            next_token = _encode_page_token(next_offset) if next_offset < total_tables else None
        else:
            tables_subset = all_tables
            next_token = None

        return {"items": tables_subset, "next_page_token": next_token}

    def share_exists(self, share_name: str) -> bool:
        """检查 Share 是否存在。

        Args:
            share_name: Share 名称。

        Returns:
            如果存在返回 True，否则返回 False。
        """
        share_name_lower = normalize_name(share_name)
        all_shares = get_all_shares()
        return share_name_lower in all_shares

    def schema_exists(self, share_name: str, schema_name: str) -> bool:
        """检查 Schema 是否存在于指定 Share 中。

        同时支持 shared_schemas 实体 schema 和直绑表的虚拟 schema
        （linked_schema_id 为 NULL，通过 shared_tables.schema_name 字段归类的表）。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。

        Returns:
            如果存在返回 True，否则返回 False。
        """
        share_name_lower = normalize_name(share_name)
        all_tables = get_share_all_tables(share_name_lower)
        return schema_name.lower() in all_tables if all_tables else False

    def table_exists(self, share_name: str, schema_name: str, table_name: str) -> bool:
        """检查 Table 是否存在于指定 Schema 中。

        同时支持关联表（linked_schema_id 指向 shared_schemas 实体）和直绑表
        （linked_schema_id 为 NULL，通过 shared_tables.schema_name 字段归类）。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。

        Returns:
            如果存在返回 True，否则返回 False。
        """
        share_name_lower = normalize_name(share_name)
        schema_name_lower = normalize_name(schema_name)
        all_tables = get_share_all_tables(share_name_lower)
        if not all_tables or schema_name_lower not in all_tables:
            return False
        return table_name.lower() in all_tables[schema_name_lower]
