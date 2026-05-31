"""
Shares 路由模块

该模块定义了 Delta Sharing 的 Share、Schema 和 Table 列表相关 API 端点。
包括：
- GET /shares - 列出所有 Share
- GET /shares/{share}/schemas - 列出 Share 下的所有 Schema
- GET /shares/{share}/schemas/{schema}/tables - 列出 Schema 下的所有 Table
- GET /shares/{share}/all-tables - 列出 Share 下的所有 Table（跨 Schema）

所有端点都支持基于 Recipient-Share 授权的权限控制。
"""

from typing import Optional
from fastapi import APIRouter, Path, Query, Request, Depends, HTTPException

from app.core.errors import DeltaSharingError, ErrorCode
from app.core.audit import get_audit_logger
from app.services.share_service import ShareService
from app.repositories.recipient_share_repository import RecipientShareRepository
from app.models.share import (
    ShareListResponse,
    ShareResponse,
    SchemaListResponse,
    TableListResponse,
    AllTablesListResponse,
)
from app.core.authentication import get_current_recipient
from app.utils.request_utils import get_client_ip
from app.utils.audit_utils import raise_audited_error
from app.core.config import get_all_shares
from loguru import logger

router = APIRouter(prefix="", tags=["shares"])

share_service = ShareService()
auth_repo = RecipientShareRepository()


@router.get("/shares", response_model=ShareListResponse)
async def list_shares(
    maxResults: Optional[int] = Query(None, alias="maxResults", ge=1, le=1000),
    pageToken: Optional[str] = Query(None, alias="pageToken"),
    request: Request = None,
    recipient_id: str = Depends(get_current_recipient),
):
    """列出所有可用的 Share。

    根据 recipient 的授权返回被授权的 share 列表（当 use_database=true 时）。

    Args:
        maxResults: 最大返回数量。
        pageToken: 分页令牌。
        request: HTTP 请求对象。
        recipient_id: 通过认证获取的 recipient ID。

    Returns:
        ShareListResponse: 包含 Share 列表的响应。
    """
    audit_logger = get_audit_logger()

    try:
        result = share_service.list_shares(
            max_results=maxResults, page_token=pageToken, recipient_id=recipient_id
        )

        audit_logger.log(
            operation="LIST_SHARES",
            category="data_plane",
            operation_type="share_list",
            http_status_code=200,
            client_ip=get_client_ip(request) if request else None,
            user_agent=request.headers.get("User-Agent") if request else None,
            recipient_id=recipient_id,
        )

        return ShareListResponse(**result)

    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "LIST_SHARES",
            request,
            operation_type="share_list",
            recipient_id=recipient_id,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in LIST_SHARES")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error",
                status_code=500,
            ),
            "LIST_SHARES",
            request,
            operation_type="share_list",
            recipient_id=recipient_id,
        )


@router.get("/shares/{share}", response_model=ShareResponse)
async def get_share(
    share: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
    recipient_id: str = Depends(get_current_recipient),
):
    """获取指定 Share 的详细信息。

    根据 Delta Sharing 协议，返回包含 share 对象的响应。

    Args:
        share: Share 名称。
        request: HTTP 请求对象。
        recipient_id: 通过认证获取的 recipient ID。

    Returns:
        ShareResponse: 包含 Share 信息的响应。

    Raises:
        HTTPException: Share 不存在或无权限访问时返回 404 错误。
    """
    audit_logger = get_audit_logger()

    access_result = auth_repo.check_access_with_share_validation(share, recipient_id)
    if access_result is None:
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SHARE_NOT_FOUND,
                message=f"Share not found: {share}",
                status_code=404,
            ),
            "GET_SHARE",
            request,
            operation_type="share_list",
            share=share,
            recipient_id=recipient_id,
        )

    if not access_result["authorized"]:
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SHARE_ACCESS_DENIED,
                message=f"Access denied to share: {share}",
                status_code=403,
            ),
            "GET_SHARE",
            request,
            operation_type="share_list",
            share=share,
            recipient_id=recipient_id,
        )

    all_shares = get_all_shares()
    share_config = all_shares.get(share.lower())
    share_object = {"name": share}
    if share_config:
        if share_config.id:
            share_object["id"] = share_config.id
        if share_config.display_name:
            share_object["displayName"] = share_config.display_name
        if share_config.comment:
            share_object["comment"] = share_config.comment
        if share_config.properties:
            share_object["properties"] = share_config.properties

    audit_logger.log(
        operation="GET_SHARE",
        category="data_plane",
        operation_type="share_list",
        share=share,
        http_status_code=200,
        client_ip=get_client_ip(request) if request else None,
        user_agent=request.headers.get("User-Agent") if request else None,
        recipient_id=recipient_id,
    )

    return ShareResponse(share=share_object)


@router.get("/shares/{share}/schemas", response_model=SchemaListResponse)
async def list_schemas(
    share: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    maxResults: Optional[int] = Query(None, alias="maxResults", ge=1, le=1000),
    pageToken: Optional[str] = Query(None, alias="pageToken"),
    request: Request = None,
    recipient_id: str = Depends(get_current_recipient),
):
    """列出指定 Share 下的所有 Schema。

    Args:
        share: Share 名称。
        maxResults: 最大返回数量。
        pageToken: 分页令牌。
        request: HTTP 请求对象。
        recipient_id: 通过认证获取的 recipient ID。

    Returns:
        SchemaListResponse: 包含 Schema 列表的响应。

    Raises:
        HTTPException: Share 不存在或无权限访问时返回 404 错误。
    """
    audit_logger = get_audit_logger()

    access_result = auth_repo.check_access_with_share_validation(share, recipient_id)
    if access_result is None:
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SHARE_NOT_FOUND,
                message=f"Share not found: {share}",
                status_code=404,
            ),
            "LIST_SCHEMAS",
            request,
            operation_type="metadata",
            share=share,
            recipient_id=recipient_id,
        )

    if not access_result["authorized"]:
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SHARE_ACCESS_DENIED,
                message=f"Access denied to share: {share}",
                status_code=403,
            ),
            "LIST_SCHEMAS",
            request,
            operation_type="metadata",
            share=share,
            recipient_id=recipient_id,
        )

    try:
        result = share_service.list_schemas(
            share_name=share, max_results=maxResults, page_token=pageToken
        )

        audit_logger.log(
            operation="LIST_SCHEMAS",
            category="data_plane",
            operation_type="metadata",
            share=share,
            http_status_code=200,
            client_ip=get_client_ip(request) if request else None,
            user_agent=request.headers.get("User-Agent") if request else None,
            recipient_id=recipient_id,
        )

        return SchemaListResponse(**result)

    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "LIST_SCHEMAS",
            request,
            operation_type="metadata",
            share=share,
            recipient_id=recipient_id,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in LIST_SCHEMAS")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error",
                status_code=500,
            ),
            "LIST_SCHEMAS",
            request,
            operation_type="metadata",
            share=share,
            recipient_id=recipient_id,
        )


@router.get("/shares/{share}/all-tables", response_model=AllTablesListResponse)
async def list_all_tables(
    share: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    maxResults: Optional[int] = Query(None, alias="maxResults", ge=1, le=1000),
    pageToken: Optional[str] = Query(None, alias="pageToken"),
    request: Request = None,
    recipient_id: str = Depends(get_current_recipient),
):
    """列出指定 Share 下所有 Schema 中的所有 Table。

    Args:
        share: Share 名称。
        maxResults: 最大返回数量。
        pageToken: 分页令牌。
        request: HTTP 请求对象。
        recipient_id: 通过认证获取的 recipient ID。

    Returns:
        AllTablesListResponse: 包含所有 Table 列表的响应。

    Raises:
        HTTPException: Share 不存在或无权限访问时返回 404 错误。
    """
    audit_logger = get_audit_logger()

    access_result = auth_repo.check_access_with_share_validation(share, recipient_id)
    if access_result is None:
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SHARE_NOT_FOUND,
                message=f"Share not found: {share}",
                status_code=404,
            ),
            "LIST_ALL_TABLES",
            request,
            operation_type="metadata",
            share=share,
            recipient_id=recipient_id,
        )

    if not access_result["authorized"]:
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SHARE_ACCESS_DENIED,
                message=f"Access denied to share: {share}",
                status_code=403,
            ),
            "LIST_ALL_TABLES",
            request,
            operation_type="metadata",
            share=share,
            recipient_id=recipient_id,
        )

    try:
        result = share_service.list_all_tables(
            share_name=share, max_results=maxResults, page_token=pageToken
        )

        audit_logger.log(
            operation="LIST_ALL_TABLES",
            category="data_plane",
            operation_type="metadata",
            share=share,
            http_status_code=200,
            client_ip=get_client_ip(request) if request else None,
            user_agent=request.headers.get("User-Agent") if request else None,
            recipient_id=recipient_id,
        )

        return AllTablesListResponse(**result)

    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "LIST_ALL_TABLES",
            request,
            operation_type="metadata",
            share=share,
            recipient_id=recipient_id,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in LIST_ALL_TABLES")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error",
                status_code=500,
            ),
            "LIST_ALL_TABLES",
            request,
            operation_type="metadata",
            share=share,
            recipient_id=recipient_id,
        )


@router.get("/shares/{share}/schemas/{schema}/tables", response_model=TableListResponse)
async def list_tables(
    share: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    schema: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    maxResults: Optional[int] = Query(None, alias="maxResults", ge=1, le=1000),
    pageToken: Optional[str] = Query(None, alias="pageToken"),
    request: Request = None,
    recipient_id: str = Depends(get_current_recipient),
):
    """列出指定 Schema 下的所有 Table。

    Args:
        share: Share 名称。
        schema: Schema 名称。
        maxResults: 最大返回数量。
        pageToken: 分页令牌。
        request: HTTP 请求对象。
        recipient_id: 通过认证获取的 recipient ID。

    Returns:
        TableListResponse: 包含 Table 列表的响应。

    Raises:
        HTTPException: Share 或 Schema 不存在或无权限访问时返回 404 错误。
    """
    audit_logger = get_audit_logger()

    access_result = auth_repo.check_access_with_share_validation(share, recipient_id)
    if access_result is None:
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SHARE_NOT_FOUND,
                message=f"Share not found: {share}",
                status_code=404,
            ),
            "LIST_TABLES",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            recipient_id=recipient_id,
        )

    if not access_result["authorized"]:
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                error_code=ErrorCode.SHARE_ACCESS_DENIED,
                message=f"Access denied to share: {share}",
                status_code=403,
            ),
            "LIST_TABLES",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
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
            "LIST_TABLES",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            recipient_id=recipient_id,
        )

    try:
        result = share_service.list_tables(
            share_name=share,
            schema_name=schema,
            max_results=maxResults,
            page_token=pageToken,
        )

        audit_logger.log(
            operation="LIST_TABLES",
            category="data_plane",
            operation_type="metadata",
            share=share,
            schema=schema,
            http_status_code=200,
            client_ip=get_client_ip(request) if request else None,
            user_agent=request.headers.get("User-Agent") if request else None,
            recipient_id=recipient_id,
        )

        return TableListResponse(**result)

    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "LIST_TABLES",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            recipient_id=recipient_id,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in LIST_TABLES")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error",
                status_code=500,
            ),
            "LIST_TABLES",
            request,
            operation_type="metadata",
            share=share,
            schema=schema,
            recipient_id=recipient_id,
        )
