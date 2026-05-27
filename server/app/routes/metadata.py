"""
元数据路由模块

该模块定义了 Delta Sharing 的表元数据获取 API 端点。
包括：
- GET /shares/{share}/schemas/{schema}/tables/{table}/metadata - 获取表元数据

返回表结构、schema、分区信息等。

支持 delta-sharing-capabilities header，用于指定响应格式和客户端能力。
"""

import json
from fastapi import APIRouter, Header, Path, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from loguru import logger

from app.core.errors import DeltaSharingError, ErrorCode
from app.core.audit import get_audit_logger
from app.core.delta_capabilities import (
    parse_delta_sharing_capabilities,
    EndStreamAction,
)
from app.services.iceberg_service import IcebergService
from app.services.share_service import ShareService
from app.services.authorization_service import AuthorizationService
from app.services.version_service import VersionService
from app.models.share import TableMetadata
from app.core.authentication import get_current_recipient
from app.utils.audit_utils import raise_audited_error
from app.utils.request_utils import get_client_ip

router = APIRouter(prefix="", tags=["metadata"])

iceberg_service = IcebergService()
share_service = ShareService()
authorization_service = AuthorizationService()
version_service = VersionService()


@router.get(
    "/shares/{share}/schemas/{schema}/tables/{table}/metadata", response_model=TableMetadata
)
async def get_table_metadata(
    share: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    schema: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    table: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
    delta_sharing_capabilities: Optional[str] = Header(None, alias="delta-sharing-capabilities"),
    recipient_id: str = Depends(get_current_recipient),
):
    """获取指定表的元数据。

    返回 Iceberg 表的结构信息，包括 schema、分区列等。
    支持 delta-sharing-capabilities header，用于指定响应格式和客户端能力。

    Args:
        share: Share 名称。
        schema: Schema 名称。
        table: 表名称。
        request: HTTP 请求对象。
        delta_sharing_capabilities: Delta Sharing Capabilities header，用于指定响应格式等。

    Returns:
        StreamingResponse: 包含协议和元数据的流式响应。

    Raises:
        HTTPException: Share、Schema 或 Table 不存在时返回 404 错误。
    """
    audit_logger = get_audit_logger()

    capabilities = parse_delta_sharing_capabilities(delta_sharing_capabilities)

    if not share_service.share_exists(share):
        error = DeltaSharingError(
            error_code=ErrorCode.SHARE_NOT_FOUND,
            message=f"Share not found: {share}",
            status_code=404,
        )
        raise_audited_error(
            audit_logger,
            error,
            "GET_METADATA",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    if not authorization_service.check_share_access(recipient_id, share):
        error = DeltaSharingError(
            error_code=ErrorCode.SHARE_ACCESS_DENIED,
            message=f"Access denied to share: {share}",
            status_code=403,
        )
        raise_audited_error(
            audit_logger,
            error,
            "GET_METADATA",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    if not share_service.schema_exists(share, schema):
        error = DeltaSharingError(
            error_code=ErrorCode.SCHEMA_NOT_FOUND,
            message=f"Schema not found: {schema}",
            status_code=404,
        )
        raise_audited_error(
            audit_logger,
            error,
            "GET_METADATA",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    if not share_service.table_exists(share, schema, table):
        error = DeltaSharingError(
            error_code=ErrorCode.TABLE_NOT_FOUND,
            message=f"Table not found: {table}",
            status_code=404,
        )
        raise_audited_error(
            audit_logger,
            error,
            "GET_METADATA",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    try:
        snapshot = iceberg_service.get_current_snapshot(share, schema, table)
        if snapshot is None:
            raise_audited_error(
                audit_logger,
                DeltaSharingError(
                    error_code=ErrorCode.TABLE_NOT_FOUND,
                    message=f"No snapshot found for table: {table}",
                    status_code=404,
                ),
                "GET_METADATA",
                request,
                operation_type="metadata",
                share=share,
                schema=schema,
                table=table,
                recipient_id=recipient_id,
            )

        snapshot_id = snapshot.get("snapshot-id")
        current_version = version_service.get_or_allocate_version(
            share, schema, table, snapshot_id, int(snapshot.get("timestamp-ms", 0))
        )

        metadata = iceberg_service.get_table_metadata(share, schema, table)

        if metadata is None:
            raise_audited_error(
                audit_logger,
                DeltaSharingError(
                    error_code=ErrorCode.TABLE_NOT_FOUND,
                    message=f"Cannot load metadata for table: {table}",
                    status_code=404,
                ),
                "GET_METADATA",
                request,
                operation_type="metadata",
                share=share,
                schema=schema,
                table=table,
                recipient_id=recipient_id,
            )

        audit_logger.log(
            operation="GET_METADATA",
            category="data_plane",
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            delta_table_version=current_version,
            iceberg_snapshot_id=snapshot_id,
            http_status_code=200,
            client_ip=get_client_ip(request) if request else None,
            user_agent=request.headers.get("User-Agent") if request else None,
            recipient_id=recipient_id,
        )

        def generate_metadata_response():
            protocol_obj = {"protocol": {"minReaderVersion": 1}}
            metadata_obj = {
                "metaData": {
                    "id": metadata.get("id", f"{share}.{schema}.{table}"),
                    "format": {"provider": metadata.get("format", "parquet")},
                    "schemaString": metadata.get("schema_string", "{}"),
                    "partitionColumns": metadata.get("partition_columns") or [],
                    "location": metadata.get("location"),
                    "auxiliaryLocations": metadata.get("auxiliary_locations") or [],
                    "accessModes": ["url"],
                    "configuration": metadata.get("configuration") or {},
                    "size": metadata.get("size"),
                    "numFiles": metadata.get("num_files"),
                }
            }
            yield json.dumps(protocol_obj) + "\n"
            yield json.dumps(metadata_obj) + "\n"

            if capabilities.include_end_stream_action:
                end_stream_action = EndStreamAction()
                yield json.dumps(end_stream_action.to_json_dict()) + "\n"

        response_headers = {
            "Delta-Table-Version": str(current_version),
            "Content-Type": "application/x-ndjson; charset=utf-8",
            "Delta-Sharing-Capabilities": capabilities.to_response_header(),
        }

        return StreamingResponse(
            generate_metadata_response(), status_code=200, headers=response_headers
        )

    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "GET_METADATA",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in GET_METADATA")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error",
                status_code=500,
            ),
            "GET_METADATA",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )
