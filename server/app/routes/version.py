"""
版本路由模块

该模块定义了 Delta Sharing 的表版本查询 API 端点。
包括：
- GET /shares/{share}/schemas/{schema}/tables/{table}/version - 获取表版本

支持通过时间戳查询特定版本。
"""

from fastapi import APIRouter, Path, Request, Query, Response, Depends
from typing import Optional

from app.core.errors import DeltaSharingError, ErrorCode
from app.core.audit import get_audit_logger
from app.services.iceberg_service import IcebergService
from app.services.share_service import ShareService
from app.services.version_service import VersionService
from app.services.authorization_service import AuthorizationService
from app.core.authentication import get_current_recipient
from app.utils.request_utils import get_client_ip
from app.utils.audit_utils import raise_audited_error
from app.utils.time_utils import parse_iso8601_timestamp


router = APIRouter(prefix="", tags=["version"])

iceberg_service = IcebergService()
share_service = ShareService()
version_service = VersionService()
authorization_service = AuthorizationService()


@router.get("/shares/{share}/schemas/{schema}/tables/{table}/version")
async def get_table_version(
    share: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    schema: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    table: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    startingTimestamp: Optional[str] = Query(None, alias="startingTimestamp"),
    timestamp: Optional[str] = Query(None, alias="timestamp"),
    request: Request = None,
    recipient_id: str = Depends(get_current_recipient),
):
    """获取表的当前版本或指定时间戳的版本。

    Args:
        share: Share 名称。
        schema: Schema 名称。
        table: 表名称。
        startingTimestamp: 起始时间戳(ISO8601格式),返回此时间之后的最早版本。
        timestamp: 精确时间戳(ISO8601格式),返回最接近但不超过此时间戳的版本。
        request: HTTP 请求对象。

    Returns:
        Response: 包含 Delta-Table-Version 头的响应。

    Raises:
        HTTPException: Share、Schema 或 Table 不存在时返回 404 错误。
        HTTPException: 时间戳对应的版本不存在时返回 400 错误。
    """
    audit_logger = get_audit_logger()

    if not share_service.share_exists(share):
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SHARE_NOT_FOUND,
                message=f"Share not found: {share}",
                status_code=404,
            ),
            "GET_VERSION",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    if not authorization_service.check_share_access(recipient_id, share):
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SHARE_ACCESS_DENIED,
                message=f"Access denied to share: {share}",
                status_code=403,
            ),
            "GET_VERSION",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    if not share_service.schema_exists(share, schema):
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SCHEMA_NOT_FOUND,
                message=f"Schema not found: {schema}",
                status_code=404,
            ),
            "GET_VERSION",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    if not share_service.table_exists(share, schema, table):
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.TABLE_NOT_FOUND,
                message=f"Table not found: {table}",
                status_code=404,
            ),
            "GET_VERSION",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    snapshot_id = None
    version = None

    if timestamp is not None:
        timestamp_ms = parse_iso8601_timestamp(timestamp)
        snapshot_info = version_service.get_version_by_timestamp(share, schema, table, timestamp_ms)
        if snapshot_info is None:
            raise_audited_error(
                audit_logger,
                DeltaSharingError(
                    error_code=ErrorCode.INVALID_REQUEST,
                    message=f"No snapshot found for timestamp: {timestamp}",
                    status_code=400,
                ),
                "GET_VERSION",
                request,
                operation_type="metadata",
                share=share,
                schema=schema,
                table=table,
                recipient_id=recipient_id,
            )
        snapshot_id = snapshot_info["snapshot_id"]
        version = snapshot_info["version"]
    elif startingTimestamp is not None:
        starting_timestamp_ms = parse_iso8601_timestamp(startingTimestamp)
        snapshot_info = version_service.get_version_by_timestamp(
            share, schema, table, starting_timestamp_ms
        )
        if snapshot_info is None:
            raise_audited_error(
                audit_logger,
                DeltaSharingError(
                    error_code=ErrorCode.INVALID_REQUEST,
                    message=f"No snapshot found for starting timestamp: {startingTimestamp}",
                    status_code=400,
                ),
                "GET_VERSION",
                request,
                operation_type="metadata",
                share=share,
                schema=schema,
                table=table,
                recipient_id=recipient_id,
            )
        snapshot_id = snapshot_info["snapshot_id"]
        version = snapshot_info["version"]
    else:
        snapshot = iceberg_service.get_current_snapshot(share, schema, table)
        if snapshot is None:
            raise_audited_error(
                audit_logger,
                DeltaSharingError(
                    error_code=ErrorCode.TABLE_NOT_FOUND,
                    message=f"No snapshot found for table: {table}",
                    status_code=404,
                ),
                "GET_VERSION",
                request,
                operation_type="metadata",
                share=share,
                schema=schema,
                table=table,
                recipient_id=recipient_id,
            )

        snapshot_id = snapshot.get("snapshot-id")
        current_version = version_service.get_or_allocate_version(
            share, schema, table, snapshot_id, int(snapshot.get("timestamp", 0))
        )

        version = current_version

    response_headers = {"Delta-Table-Version": str(version)}

    audit_logger.log(
        operation="GET_VERSION",
        category="data_plane",
        operation_type="metadata",
        share=share,
        schema=schema,
        table=table,
        delta_table_version=version,
        iceberg_snapshot_id=snapshot_id,
        http_status_code=200,
        client_ip=get_client_ip(request) if request else None,
        user_agent=request.headers.get("User-Agent") if request else None,
        recipient_id=recipient_id,
    )

    return Response(content="", status_code=200, headers=response_headers)
