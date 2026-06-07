"""
查询路由模块

该模块定义了 Delta Sharing 的表查询 API 端点。
包括：
- POST /shares/{share}/schemas/{schema}/tables/{table}/query - 查询表数据

返回表文件列表和预签名 URL，支持谓词下推过滤。

支持 delta-sharing-capabilities header，用于指定响应格式和客户端能力。
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Path, Request, Depends
from loguru import logger

from app.core.errors import DeltaSharingError, ErrorCode
from app.core.audit import get_audit_logger
from app.core.config import get_config
from app.core.delta_capabilities import parse_delta_sharing_capabilities
from app.utils.request_utils import get_client_ip
from app.utils.audit_utils import raise_audited_error, QueryAuditContext
from app.utils.response_utils import generate_ndjson_response
from app.utils.time_utils import parse_iso8601_timestamp
from app.services.iceberg_service import get_iceberg_service
from app.services.share_service import ShareService
from app.repositories.recipient_share_repository import RecipientShareRepository
from app.services.version_service import VersionService
from app.services.predicate_service import PredicateService
from app.services.table_service import TableService
from app.models.query import Protocol, Metadata, QueryRequest
from app.core.authentication import get_current_recipient

router = APIRouter(prefix="", tags=["query"])

share_service = ShareService()
auth_repo = RecipientShareRepository()
version_service = VersionService()
predicate_service = PredicateService()
table_service = TableService()


@router.post("/shares/{share}/schemas/{schema}/tables/{table}/query")
async def query_table(
    share: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    schema: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    table: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    query_request: QueryRequest = QueryRequest(),
    request: Request = None,
    delta_sharing_capabilities: Optional[str] = Header(None, alias="delta-sharing-capabilities"),
    recipient_id: str = Depends(get_current_recipient),
):
    """查询表数据文件。

    返回表的数据文件列表，每个文件包含预签名访问 URL。
    支持 delta-sharing-capabilities header，用于指定响应格式和客户端能力。

    Args:
        share: Share 名称。
        schema: Schema 名称。
        table: 表名称。
        query_request: 查询请求体，包含 predicateHints、jsonPredicateHints、limitHint、
                        version、timestamp、startingVersion、endingVersion 等参数。
        request: HTTP 请求对象。
        delta_sharing_capabilities: Delta Sharing Capabilities header，用于指定响应格式等。

    Returns:
        StreamingResponse: NDJSON 格式的查询响应。

    Raises:
        HTTPException: Share、Schema 或 Table 不存在时返回 404 错误。
        HTTPException: 表包含不支持的删除文件时返回 400 错误。
    """
    predicateHints = query_request.predicateHints
    jsonPredicateHints = query_request.jsonPredicateHints
    limitHint = query_request.limitHint
    query_version = query_request.version
    query_timestamp = query_request.timestamp
    startingVersion = query_request.startingVersion
    endingVersion = query_request.endingVersion
    audit_logger = get_audit_logger()
    config = get_config()

    capabilities = parse_delta_sharing_capabilities(delta_sharing_capabilities)

    access_result = auth_repo.check_access_with_share_validation(share, recipient_id)
    if access_result is None:
        error = DeltaSharingError(
            error_code=ErrorCode.SHARE_NOT_FOUND,
            message=f"Share not found: {share}",
            status_code=404,
        )
        raise_audited_error(
            audit_logger,
            error,
            "POST_QUERY",
            request,
            operation_type="query",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    if not access_result["authorized"]:
        error = DeltaSharingError(
            error_code=ErrorCode.SHARE_ACCESS_DENIED,
            message=f"Access denied to share: {share}",
            status_code=403,
        )
        raise_audited_error(
            audit_logger,
            error,
            "POST_QUERY",
            request,
            operation_type="query",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    table_config = table_service.get_table_config(share, schema, table)
    if table_config is None:
        # get_table_config() 返回 None 表示 schema/table 不存在
        # 额外查询 schema_exists() 区分 404 原因（仅在错误路径触发）
        if not share_service.schema_exists(share, schema):
            error = DeltaSharingError(
                error_code=ErrorCode.SCHEMA_NOT_FOUND,
                message=f"Schema not found: {schema}",
                status_code=404,
            )
            raise_audited_error(
                audit_logger,
                error,
                "POST_QUERY",
                request,
                operation_type="query",
                share=share,
                schema=schema,
                table=table,
                recipient_id=recipient_id,
            )
        error = DeltaSharingError(
            error_code=ErrorCode.TABLE_NOT_FOUND,
            message=f"Table not found: {table}",
            status_code=404,
        )
        raise_audited_error(
            audit_logger,
            error,
            "POST_QUERY",
            request,
            operation_type="query",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )

    try:
        # 时间旅行查询参数解析：version 优先于 timestamp
        query_display_version = None

        if query_version is not None:
            # 按 version 查找快照（逆向查询）
            snapshot_info = version_service.get_by_version(share, schema, table, query_version)
            if snapshot_info is None:
                error = DeltaSharingError(
                    error_code=ErrorCode.INVALID_REQUEST,
                    message=f"Version {query_version} not found for table: {share}.{schema}.{table}",
                    status_code=400,
                )
                raise_audited_error(
                    audit_logger,
                    error,
                    "POST_QUERY",
                    request,
                    operation_type="query",
                    share=share,
                    schema=schema,
                    table=table,
                    recipient_id=recipient_id,
                )

            snapshot = get_iceberg_service().get_snapshot_by_id(
                share, schema, table, snapshot_info["snapshot_id"]
            )
            if snapshot is None:
                error = DeltaSharingError(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message=f"Snapshot {snapshot_info['snapshot_id']} not found in metadata for table: {table}",
                    status_code=500,
                )
                raise_audited_error(
                    audit_logger,
                    error,
                    "POST_QUERY",
                    request,
                    operation_type="query",
                    share=share,
                    schema=schema,
                    table=table,
                    recipient_id=recipient_id,
                )
            query_display_version = snapshot_info["version"]

        elif query_timestamp is not None:
            # 按 timestamp 查找快照
            try:
                timestamp_ms = parse_iso8601_timestamp(query_timestamp)
            except ValueError as e:
                error = DeltaSharingError(
                    error_code=ErrorCode.INVALID_REQUEST,
                    message=f"Invalid timestamp format: {query_timestamp}. "
                    f"Expected ISO8601 format (e.g., 2022-01-01T00:00:00Z). Error: {str(e)}",
                    status_code=400,
                )
                raise_audited_error(
                    audit_logger,
                    error,
                    "POST_QUERY",
                    request,
                    operation_type="query",
                    share=share,
                    schema=schema,
                    table=table,
                    recipient_id=recipient_id,
                )

            snapshot_info = version_service.get_version_by_timestamp(
                share, schema, table, timestamp_ms
            )
            if snapshot_info is None:
                error = DeltaSharingError(
                    error_code=ErrorCode.INVALID_REQUEST,
                    message=f"No snapshot found at or before timestamp: {query_timestamp} "
                    f"for table: {share}.{schema}.{table}",
                    status_code=400,
                )
                raise_audited_error(
                    audit_logger,
                    error,
                    "POST_QUERY",
                    request,
                    operation_type="query",
                    share=share,
                    schema=schema,
                    table=table,
                    recipient_id=recipient_id,
                )

            snapshot = get_iceberg_service().get_snapshot_by_id(
                share, schema, table, snapshot_info["snapshot_id"]
            )
            if snapshot is None:
                error = DeltaSharingError(
                    error_code=ErrorCode.INTERNAL_ERROR,
                    message=f"Snapshot {snapshot_info['snapshot_id']} not found in metadata for table: {table}",
                    status_code=500,
                )
                raise_audited_error(
                    audit_logger,
                    error,
                    "POST_QUERY",
                    request,
                    operation_type="query",
                    share=share,
                    schema=schema,
                    table=table,
                    recipient_id=recipient_id,
                )
            query_display_version = snapshot_info["version"]

        else:
            # 默认：使用当前最新快照
            snapshot = get_iceberg_service().get_current_snapshot(
                share, schema, table, table_config=table_config
            )
            if snapshot is None:
                raise_audited_error(
                    audit_logger,
                    DeltaSharingError(
                        error_code=ErrorCode.TABLE_NOT_FOUND,
                        message=f"No snapshot found for table: {table}",
                        status_code=404,
                    ),
                    "POST_QUERY",
                    request,
                    operation_type="query",
                    share=share,
                    schema=schema,
                    table=table,
                    recipient_id=recipient_id,
                )

        snapshot_id = snapshot.get("snapshot-id")
        if snapshot_id is None:
            error = DeltaSharingError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Snapshot missing snapshot-id field",
                status_code=500,
            )
            raise_audited_error(
                audit_logger,
                error,
                "POST_QUERY",
                request,
                operation_type="query",
                share=share,
                schema=schema,
                table=table,
                recipient_id=recipient_id,
            )

        current_version = version_service.get_or_allocate_version(
            share, schema, table, snapshot_id, int(snapshot.get("timestamp-ms", 0))
        )

        data_files, has_delete_files = get_iceberg_service().get_data_files(
            share, schema, table, snapshot_id, table_config=table_config
        )

        if has_delete_files:
            error = DeltaSharingError(
                error_code=ErrorCode.TABLE_NOT_SUPPORTED,
                message="Table contains delete files which are not supported",
                status_code=400,
            )
            raise_audited_error(
                audit_logger,
                error,
                "POST_QUERY",
                request,
                operation_type="query",
                share=share,
                schema=schema,
                table=table,
                delta_table_version=snapshot_id,
                iceberg_snapshot_id=snapshot_id,
                recipient_id=recipient_id,
            )
        partition_columns = get_iceberg_service().get_partition_columns(
            share, schema, table, table_config=table_config
        )

        parsed_predicates = predicate_service.parse_predicate_hints(predicateHints)

        json_predicate = None
        if jsonPredicateHints:
            try:
                json_predicate = json.loads(jsonPredicateHints)
            except json.JSONDecodeError:
                # 注意: 此处的 raise_audited_error() 抛出的是 HTTPException，
                # 不会进入外层 except DeltaSharingError 分支，因此不会产生双重审计日志。
                raise_audited_error(
                    audit_logger,
                    DeltaSharingError(
                        ErrorCode.INVALID_REQUEST,
                        "Invalid jsonPredicateHints: not valid JSON",
                        status_code=400,
                    ),
                    "POST_QUERY",
                    request,
                    operation_type="query",
                    share=share,
                    schema=schema,
                    table=table,
                    recipient_id=recipient_id,
                )

        # 调试记录客户端发送的谓词参数，用于排查 file pruning 问题
        logger.debug(
            f"Query predicate: table={share}.{schema}.{table} | "
            f"predicateHints={predicateHints} | "
            f"jsonPredicateHints={jsonPredicateHints[:300] if jsonPredicateHints else 'None'} | "
            f"partition_columns={partition_columns} | "
            f"total_files={len(data_files)}"
        )

        # 统一谓词过滤：分区裁剪 + 文件级统计过滤合并为单次调用
        filtered_files = predicate_service.filter_files(
            data_files=data_files,
            json_predicate=json_predicate,
            predicate_hints=parsed_predicates,
            partition_columns=partition_columns,
        )

        if limitHint and len(filtered_files) > limitHint:
            filtered_files = filtered_files[:limitHint]

        file_objects = get_iceberg_service().build_file_objects(
            filtered_files,
            table_config,
            snapshot,
            current_version,
            query_version=query_display_version,
        )

        metadata_response = get_iceberg_service().get_table_metadata(
            share,
            schema,
            table,
            table_config=table_config,
            preloaded_data_files=data_files,
        )

        if metadata_response is None:
            error = DeltaSharingError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Table metadata not found",
                status_code=500,
            )
            raise_audited_error(
                audit_logger,
                error,
                "POST_QUERY",
                request,
                operation_type="query",
                share=share,
                schema=schema,
                table=table,
                recipient_id=recipient_id,
            )

        protocol_obj = Protocol(minReaderVersion=1)

        metadata_obj = Metadata(
            id=metadata_response.get("id", f"{share}.{schema}.{table}"),
            format={"provider": "parquet"},
            schemaString=metadata_response.get("schema_string", "{}"),
            partitionColumns=metadata_response.get("partition_columns") or [],
            location=metadata_response.get("location"),
            auxiliaryLocations=metadata_response.get("auxiliary_locations") or [],
            accessModes=["url"],
            configuration=metadata_response.get("configuration") or {},
            size=metadata_response.get("size"),
            numFiles=metadata_response.get("num_files"),
        )

        min_expiration = file_objects[0]["expirationTimestamp"] if file_objects else None

        file_paths = None
        if config.logging.audit_log_level == "DEBUG":
            file_paths = [f.get("file_path") for f in filtered_files if f.get("file_path")]

        audit_ctx = QueryAuditContext(
            share=share,
            schema=schema,
            table=table,
            delta_table_version=current_version,
            iceberg_snapshot_id=snapshot_id,
            files_returned=len(file_objects),
            recipient_id=recipient_id,
            query_version=query_version,
            query_timestamp=query_timestamp,
            query_starting_version=startingVersion,
            query_ending_version=endingVersion,
            file_paths=file_paths,
        )
        audit_logger.log(
            operation="POST_QUERY",
            category="data_plane",
            operation_type="query",
            http_status_code=200,
            client_ip=get_client_ip(request) if request else None,
            user_agent=request.headers.get("User-Agent") if request else None,
            share=audit_ctx.share,
            schema=audit_ctx.schema,
            table=audit_ctx.table,
            delta_table_version=audit_ctx.delta_table_version,
            iceberg_snapshot_id=audit_ctx.iceberg_snapshot_id,
            files_returned=audit_ctx.files_returned,
            recipient_id=audit_ctx.recipient_id,
            query_version=audit_ctx.query_version,
            query_timestamp=audit_ctx.query_timestamp,
            query_starting_version=audit_ctx.query_starting_version,
            query_ending_version=audit_ctx.query_ending_version,
            file_paths=audit_ctx.file_paths,
        )

        response_version = (
            query_display_version if query_display_version is not None else current_version
        )

        return generate_ndjson_response(
            protocol_obj,
            metadata_obj,
            file_objects,
            config,
            response_version,
            capabilities=capabilities,
            min_url_expiration=min_expiration,
            response_format=capabilities.response_format,
        )

    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "POST_QUERY",
            request,
            operation_type="query",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during query")
        unexpected = DeltaSharingError(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="Internal server error",
            status_code=500,
            details={"error_type": type(e).__name__},
        )
        raise_audited_error(
            audit_logger,
            unexpected,
            "POST_QUERY",
            request,
            operation_type="query",
            share=share,
            schema=schema,
            table=table,
            recipient_id=recipient_id,
        )
