"""
Admin API - Share 实体管理端点

该模块提供 Share 实体的 REST API 端点：
- POST /admin/v1/shares - 创建 Share
- GET /admin/v1/shares - 列出所有 Share
- GET /admin/v1/shares/{share_name} - 获取单个 Share
- DELETE /admin/v1/shares/{share_name} - 删除 Share
- PUT /admin/v1/shares/{share_name}/rename - 重命名 Share
- POST /admin/v1/shares/{share_name}/objects - 添加 Schema 或 Table 到 Share
- GET /admin/v1/shares/{share_name}/objects - 列出 Share 下的所有资产
- PUT /admin/v1/shares/{share_name}/objects/{object_type}/{object_name} - 更新资产
- DELETE /admin/v1/shares/{share_name}/objects/{object_type}/{object_name} - 删除资产
"""

from typing import Optional, Dict, List
from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel

from app.core.audit import get_audit_logger
from app.core.errors import ErrorCode, DeltaSharingError
from app.core.dlc_client import get_dlc_client, DLCConfigError, DLCAPIError
from app.repositories.share_repository import ShareRepository
from app.utils.audit_utils import raise_audited_error
from loguru import logger

router = APIRouter(prefix="/shares", tags=["admin-share-management"])


class CreateShareRequest(BaseModel):
    name: str
    display_name: Optional[str] = None
    comment: Optional[str] = None
    properties: Optional[Dict[str, str]] = None


class UpdateShareRequest(BaseModel):
    display_name: Optional[str] = None
    comment: Optional[str] = None
    properties: Optional[Dict[str, str]] = None


class RenameShareRequest(BaseModel):
    new_name: str


class AddSchemaRequest(BaseModel):
    schema_name: str
    metastore_db: str = ""


class AddTableRequest(BaseModel):
    schema_name: str
    table_name: str
    location: str = ""
    metastore_db: str = ""
    metastore_table: Optional[str] = None
    auxiliary_locations: Optional[List[str]] = None


class UpdateAssetRequest(BaseModel):
    schema_name: Optional[str] = None
    metastore_db: Optional[str] = None
    location: Optional[str] = None
    metastore_table: Optional[str] = None
    auxiliary_locations: Optional[List[str]] = None
    new_schema_name: Optional[str] = None


@router.post("", status_code=201)
async def create_share(create_request: CreateShareRequest, request: Request = None):
    """创建新的 Share。

    Args:
        create_request: 创建 Share 请求体。
        request: HTTP 请求对象。

    Returns:
        创建的 Share 对象。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()
    try:
        share = repo.create_share(
            name=create_request.name,
            display_name=create_request.display_name,
            comment=create_request.comment,
            properties=create_request.properties,
        )
        return share
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_CREATE_SHARE",
            request=request,
            category="admin",
            share=create_request.name,
        )
    except Exception:
        logger.exception(f"Unexpected error creating share '{create_request.name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_CREATE_SHARE",
            request=request,
            category="admin",
            share=create_request.name,
        )


@router.get("")
async def list_shares(request: Request = None):
    """列出所有 Share。

    Args:
        request: HTTP 请求对象。

    Returns:
        Share 列表。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()
    try:
        shares = repo.list_shares()
        return {"items": shares}
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_LIST_SHARES",
            request=request,
            category="admin",
        )
    except Exception:
        logger.exception("Unexpected error listing shares")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_LIST_SHARES",
            request=request,
            category="admin",
        )


@router.get("/{share_name}")
async def get_share(
    share_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """获取单个 Share。

    Args:
        share_name: Share 名称。
        request: HTTP 请求对象。

    Returns:
        Share 对象。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()
    try:
        share = repo.get_share(share_name)
        if not share:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{share_name}' not found",
                status_code=404,
            )
        return share
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_GET_SHARE",
            request=request,
            category="admin",
            share=share_name,
        )
    except Exception:
        logger.exception(f"Unexpected error getting share '{share_name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_GET_SHARE",
            request=request,
            category="admin",
            share=share_name,
        )


@router.delete("/{share_name}", status_code=204)
async def delete_share(
    share_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """删除 Share。

    Args:
        share_name: Share 名称。
        request: HTTP 请求对象。

    Returns:
        无内容响应。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()
    try:
        deleted = repo.delete_share(share_name)
        if not deleted:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{share_name}' not found",
                status_code=404,
            )
        return None
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_DELETE_SHARE",
            request=request,
            category="admin",
            share=share_name,
        )
    except Exception:
        logger.exception(f"Unexpected error deleting share '{share_name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_DELETE_SHARE",
            request=request,
            category="admin",
            share=share_name,
        )


@router.put("/{share_name}/rename")
async def rename_share(
    rename_request: RenameShareRequest,
    share_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """重命名 Share。

    Args:
        share_name: 当前 Share 名称。
        rename_request: 重命名请求体。
        request: HTTP 请求对象。

    Returns:
        更新后的 Share 对象。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()
    try:
        share = repo.rename_share(share_name, rename_request.new_name)
        if not share:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{share_name}' not found",
                status_code=404,
            )
        return share
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_RENAME_SHARE",
            request=request,
            category="admin",
            share=share_name,
        )
    except Exception:
        logger.exception(f"Unexpected error renaming share '{share_name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_RENAME_SHARE",
            request=request,
            category="admin",
            share=share_name,
        )


class AddShareObjectRequest(BaseModel):
    schema_name: Optional[str] = None
    table_name: Optional[str] = None
    metastore_db: str = ""
    location: Optional[str] = None
    metastore_table: Optional[str] = None
    auxiliary_locations: Optional[List[str]] = None


@router.post("/{share_name}/objects", status_code=201)
async def add_share_object(
    add_request: AddShareObjectRequest,
    share_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """添加 Schema 或 Table 到 Share。

    当仅传入 schema_name（不带 table_name）时，视为添加 Schema 资产。
    如果 schema 关联了 DLC Database (metastore_db)，则自动从 DLC 同步所有 Table。
    当仅传入 table_name（不带 schema_name）时，视为直接添加 Table 到 Share。

    Args:
        share_name: Share 名称。
        add_request: 添加资产请求体。
        request: HTTP 请求对象。

    Returns:
        创建的资产对象，包含 schema 信息和同步的 table 数量。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()

    try:
        share = repo.get_share(share_name)
        if not share:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{share_name}' not found",
                status_code=404,
            )

        if add_request.table_name:
            if add_request.location and not add_request.location.startswith("cosn:"):
                raise DeltaSharingError(
                    ErrorCode.INVALID_REQUEST,
                    'Location must start with "cosn:" (e.g., cosn://bucket-name/path/to/table)',
                    status_code=400,
                )
            effective_metastore_table = (
                add_request.metastore_table
                if add_request.metastore_table
                else add_request.table_name
            )
            effective_metastore_db = (
                add_request.metastore_db
                if add_request.metastore_db
                else add_request.schema_name
            )
            table = repo.create_table(
                share_name=share_name,
                schema_name=add_request.schema_name or "",
                table_name=add_request.table_name,
                location=add_request.location,
                metastore_db=effective_metastore_db,
                metastore_table=effective_metastore_table,
                auxiliary_locations=add_request.auxiliary_locations,
                linked_schema_id=None,
            )
            return {"type": "table", "data": table}
        elif add_request.schema_name:
            metastore_db = (
                add_request.metastore_db
                if add_request.metastore_db
                else add_request.schema_name
            )
            schema = repo.create_schema(
                share_name=share_name,
                schema_name=add_request.schema_name,
                metastore_db=metastore_db,
            )

            result = {
                "type": "schema",
                "data": schema,
                "tables_synced": 0,
                "tables_skipped": 0,
                "tables_deleted": 0,
            }

            if add_request.metastore_db:
                dlc_client = get_dlc_client()
                if dlc_client is None:
                    raise DeltaSharingError(
                        ErrorCode.DLC_NOT_CONFIGURED,
                        "DLC client not configured",
                        status_code=500,
                    )

                try:
                    dlc_response = dlc_client.describe_tables(add_request.metastore_db)
                except DLCConfigError as e:
                    raise DeltaSharingError(
                        ErrorCode.DLC_NOT_CONFIGURED,
                        str(e),
                        status_code=500,
                    )
                except DLCAPIError as e:
                    raise DeltaSharingError(
                        ErrorCode.DLC_API_ERROR,
                        str(e),
                        status_code=500,
                    )

                table_list = dlc_response.get("table_list", [])

                dlc_table_names = [
                    table_info.get("name", "") for table_info in table_list
                ]

                if table_list:
                    tables_to_create = []
                    for table_info in table_list:
                        tables_to_create.append(
                            {
                                "name": table_info.get("name"),
                                "location": table_info.get("location"),
                                "metastore_db": add_request.metastore_db,
                                "metastore_table": table_info.get("name"),
                                "auxiliary_locations": None,
                            }
                        )

                    batch_result = repo.create_tables_batch(
                        share_name=share_name,
                        schema_name=add_request.schema_name,
                        tables=tables_to_create,
                    )
                    result["tables_synced"] = batch_result["inserted_count"]
                    result["tables_skipped"] = batch_result["skipped_count"]
                else:
                    result["tables_synced"] = 0

                stale_deleted = repo.delete_stale_schema_tables(
                    share_name=share_name,
                    schema_name=add_request.schema_name,
                    dlc_table_names=dlc_table_names,
                )
                result["tables_deleted"] = stale_deleted

            return result
        else:
            raise DeltaSharingError(
                ErrorCode.INVALID_REQUEST,
                "Either schema_name (for schema) or schema_name+table_name (for table) is required",
            )
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_ADD_SHARE_OBJECT",
            request=request,
            category="admin",
            share=share_name,
        )
    except Exception:
        logger.exception(f"Unexpected error adding object to share '{share_name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_ADD_SHARE_OBJECT",
            request=request,
            category="admin",
            share=share_name,
        )


@router.get("/{share_name}/objects")
async def list_share_objects(
    share_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """列出 Share 下的所有 Schema 和 Table。

    Args:
        share_name: Share 名称。
        request: HTTP 请求对象。

    Returns:
        包含 schemas 和 tables 列表的响应。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()

    try:
        share = repo.get_share(share_name)
        if not share:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{share_name}' not found",
                status_code=404,
            )

        objects = repo.list_share_objects(share_name)
        return objects
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_LIST_SHARE_OBJECTS",
            request=request,
            category="admin",
            share=share_name,
        )
    except Exception:
        logger.exception(f"Unexpected error listing objects for share '{share_name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_LIST_SHARE_OBJECTS",
            request=request,
            category="admin",
            share=share_name,
        )


@router.get("/{share_name}/tables/direct")
async def list_direct_bound_tables(
    share_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """列出直接绑定到 Share 的 Table 列表（不通过 Schema）。

    Args:
        share_name: Share 名称。
        request: HTTP 请求对象。

    Returns:
        直接绑定到 Share 的 Table 列表。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()

    try:
        share = repo.get_share(share_name)
        if not share:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{share_name}' not found",
                status_code=404,
            )

        tables = repo.get_direct_bound_tables(share_name)
        return {"items": tables}
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_LIST_DIRECT_BOUND_TABLES",
            request=request,
            category="admin",
            share=share_name,
        )
    except Exception:
        logger.exception(
            f"Unexpected error listing direct bound tables for share '{share_name}'"
        )
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_LIST_DIRECT_BOUND_TABLES",
            request=request,
            category="admin",
            share=share_name,
        )


@router.put("/{share_name}/objects/{object_type}/{object_name}")
async def update_share_object(
    update_request: UpdateAssetRequest,
    share_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    object_type: str = Path(..., max_length=10, pattern=r"^(schema|table)$"),
    object_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """更新 Share 中的 Schema 或 Table。

    Args:
        share_name: Share 名称。
        object_type: 对象类型，'schema' 或 'table'。
        object_name: Schema 或 Table 名称。
        update_request: 更新请求体。
        request: HTTP 请求对象。

    Returns:
        更新后的对象。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()

    try:
        share = repo.get_share(share_name)
        if not share:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{share_name}' not found",
                status_code=404,
            )

        if object_type.lower() == "schema":
            schema = repo.update_schema(
                share_name=share_name,
                schema_name=object_name,
                metastore_db=update_request.metastore_db,
            )
            if not schema:
                raise DeltaSharingError(
                    ErrorCode.SCHEMA_NOT_FOUND,
                    f"Schema '{object_name}' not found in share '{share_name}'",
                    status_code=404,
                )
            return schema
        elif object_type.lower() == "table":
            if update_request.location and not update_request.location.startswith(
                "cosn:"
            ):
                raise DeltaSharingError(
                    ErrorCode.INVALID_REQUEST,
                    'Location must start with "cosn:" (e.g., cosn://bucket-name/path/to/table)',
                    status_code=400,
                )
            table = repo.update_table(
                share_name=share_name,
                schema_name=update_request.schema_name or "",
                table_name=object_name,
                location=update_request.location,
                metastore_db=update_request.metastore_db,
                metastore_table=update_request.metastore_table,
                auxiliary_locations=update_request.auxiliary_locations,
                new_schema_name=update_request.new_schema_name,
            )
            if not table:
                raise DeltaSharingError(
                    ErrorCode.TABLE_NOT_FOUND,
                    f"Table '{object_name}' not found in share '{share_name}'",
                    status_code=404,
                )
            return table
        else:
            raise DeltaSharingError(
                ErrorCode.INVALID_REQUEST,
                f"Invalid object type: {object_type}. Must be 'schema' or 'table'.",
            )
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_UPDATE_SHARE_OBJECT",
            request=request,
            category="admin",
            share=share_name,
        )
    except Exception:
        logger.exception(
            f"Unexpected error updating {object_type} '{object_name}' in share '{share_name}'"
        )
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_UPDATE_SHARE_OBJECT",
            request=request,
            category="admin",
            share=share_name,
        )


@router.delete("/{share_name}/objects/{object_type}/{object_name}", status_code=204)
async def delete_share_object(
    share_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    object_type: str = Path(..., max_length=10, pattern=r"^(schema|table)$"),
    object_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    schema_name: str = Query("", description="Schema 名称（删除 Table 时需要）"),
    request: Request = None,
):
    """删除 Share 中的 Schema 或 Table。

    Args:
        share_name: Share 名称。
        object_type: 对象类型，'schema' 或 'table'。
        object_name: Schema 或 Table 名称。
        schema_name: Schema 名称（删除 Table 时用于在指定 Schema 下定位）。
        request: HTTP 请求对象。

    Returns:
        无内容响应。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()

    try:
        share = repo.get_share(share_name)
        if not share:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{share_name}' not found",
                status_code=404,
            )

        if object_type.lower() == "schema":
            deleted = repo.delete_schema(share_name, object_name)
            if not deleted:
                raise DeltaSharingError(
                    ErrorCode.SCHEMA_NOT_FOUND,
                    f"Schema '{object_name}' not found in share '{share_name}'",
                    status_code=404,
                )
        elif object_type.lower() == "table":
            deleted = repo.delete_table(share_name, schema_name, object_name)
            if not deleted:
                raise DeltaSharingError(
                    ErrorCode.TABLE_NOT_FOUND,
                    f"Table '{object_name}' not found in share '{share_name}'",
                    status_code=404,
                )
        else:
            raise DeltaSharingError(
                ErrorCode.INVALID_REQUEST,
                f"Invalid object type: {object_type}. Must be 'schema' or 'table'.",
            )

        return None
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_DELETE_SHARE_OBJECT",
            request=request,
            category="admin",
            share=share_name,
        )
    except Exception:
        logger.exception(
            f"Unexpected error deleting {object_type} '{object_name}' from share '{share_name}'"
        )
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_DELETE_SHARE_OBJECT",
            request=request,
            category="admin",
            share=share_name,
        )
