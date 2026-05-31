"""
Admin API - DLC 表同步端点

该模块提供 DLC 表同步的 REST API 端点：
- POST /admin/v1/sync/tables - 同步 DLC 表到指定 Schema
"""

from typing import Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.audit import get_audit_logger
from app.core.errors import ErrorCode, DeltaSharingError
from app.core.dlc_client import get_dlc_client, DLCConfigError, DLCAPIError
from app.repositories.share_repository import ShareRepository
from app.utils.audit_utils import raise_audited_error
from loguru import logger

router = APIRouter(prefix="/sync", tags=["admin-sync"])


class SyncTablesRequest(BaseModel):
    share_name: str
    schema_name: str
    dlc_database: Optional[str] = None
    mode: str = "append"


@router.post("/tables", status_code=200)
async def sync_tables(request_data: SyncTablesRequest, request: Request = None):
    """同步 DLC 表到指定 Schema。

    支持全量替换(full)和增量追加(append)两种模式。

    Args:
        request_data: 同步请求体，包含 share_name、schema_name、dlc_database 和 mode。
        request: HTTP 请求对象。

    Returns:
        同步结果，包含同步的表数量、跳过的表数量和删除的表数量。
    """
    audit_logger = get_audit_logger()
    repo = ShareRepository()

    try:
        share = repo.get_share(request_data.share_name)
        if not share:
            raise DeltaSharingError(
                ErrorCode.SHARE_NOT_FOUND,
                f"Share '{request_data.share_name}' not found",
                status_code=404,
            )

        schema = repo.get_schema(request_data.share_name, request_data.schema_name)
        if not schema:
            raise DeltaSharingError(
                ErrorCode.SCHEMA_NOT_FOUND,
                f"Schema '{request_data.schema_name}' not found in share '{request_data.share_name}'",
                status_code=404,
            )

        dlc_database = request_data.dlc_database or schema.get("metastore_db")
        if not dlc_database:
            raise DeltaSharingError(
                ErrorCode.INVALID_REQUEST,
                "DLC database not specified. Provide dlc_database or set metastore_db on schema.",
                status_code=400,
            )

        dlc_client = get_dlc_client()
        if dlc_client is None:
            raise DeltaSharingError(
                ErrorCode.DLC_NOT_CONFIGURED,
                "DLC client not configured",
                status_code=500,
            )

        try:
            dlc_response = dlc_client.describe_tables(dlc_database)
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
        total_count = dlc_response.get("total_count", len(table_list))

        # 提取 DLC 中当前存在的表名列表（用于后续清理过期表）
        dlc_table_names = [table_info.get("name", "") for table_info in table_list]

        deleted_count = 0
        if request_data.mode == "full":
            deleted_count = repo.delete_schema_tables(
                request_data.share_name, request_data.schema_name
            )

        if table_list:
            tables_to_create = []
            for table_info in table_list:
                tables_to_create.append(
                    {
                        "name": table_info.get("name"),
                        "location": table_info.get("location"),
                        "metastore_db": dlc_database,
                        "metastore_table": table_info.get("name"),
                        "auxiliary_locations": None,
                    }
                )

            batch_result = repo.create_tables_batch(
                share_name=request_data.share_name,
                schema_name=request_data.schema_name,
                tables=tables_to_create,
            )

            # append 模式下清理 DLC 中已删除的过期表
            if request_data.mode != "full":
                stale_deleted = repo.delete_stale_schema_tables(
                    share_name=request_data.share_name,
                    schema_name=request_data.schema_name,
                    dlc_table_names=dlc_table_names,
                )
                deleted_count = stale_deleted

            return {
                "mode": request_data.mode,
                "dlc_database": dlc_database,
                "total_count": total_count,
                "synced_count": batch_result["inserted_count"],
                "skipped_count": batch_result["skipped_count"],
                "deleted_count": deleted_count,
            }
        else:
            # DLC 中没有任何表时，清理所有本地已有的过期表
            if request_data.mode != "full":
                deleted_count = repo.delete_stale_schema_tables(
                    share_name=request_data.share_name,
                    schema_name=request_data.schema_name,
                    dlc_table_names=[],
                )

            return {
                "mode": request_data.mode,
                "dlc_database": dlc_database,
                "total_count": 0,
                "synced_count": 0,
                "skipped_count": 0,
                "deleted_count": deleted_count,
            }

    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_SYNC_TABLES",
            request=request,
            category="admin",
            share=request_data.share_name,
            schema=request_data.schema_name,
        )
    except Exception:
        logger.exception(
            f"Unexpected error syncing tables for "
            f"share '{request_data.share_name}' schema '{request_data.schema_name}'"
        )
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_SYNC_TABLES",
            request=request,
            category="admin",
            share=request_data.share_name,
            schema=request_data.schema_name,
        )
