"""
Admin API - Share 授权管理端点

该模块提供 Recipient-Share 授权关系的 REST API 端点：
- POST /recipients/{name}/shares - 授权 share 给 recipient
- GET /recipients/{name}/shares - 列出 recipient 被授权的所有 share
- DELETE /recipients/{name}/shares/{share_name} - 撤销 recipient 对 share 的访问权限
"""

from typing import Optional

from fastapi import APIRouter, Path, Query, Request

from app.core.audit import get_audit_logger
from app.core.errors import ErrorCode, DeltaSharingError
from app.services.authorization_service import AuthorizationService
from app.utils.audit_utils import raise_audited_error
from loguru import logger

router = APIRouter(prefix="/recipients", tags=["admin-shares"])


@router.post("/{name}/shares", status_code=201)
async def grant_share_to_recipient(
    name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    share_name: str = Query(..., description="要授权的 Share 名称"),
    granted_by: Optional[str] = Query(None, alias="grantedBy", description="授权人"),
    request: Request = None,
):
    """将 share 授权给 recipient。

    Args:
        name: Recipient 名称。
        share_name: Share 名称。
        granted_by: 授权人（可选）。

    Returns:
        授权记录对象。

    Raises:
        HTTPException: 如果 recipient 或 share 不存在，或授权已存在。
    """
    audit_logger = get_audit_logger()
    service = AuthorizationService()
    try:
        auth_record = service.grant_share_to_recipient(
            recipient_name=name,
            share_name=share_name,
            granted_by=granted_by,
        )
        return auth_record
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_GRANT_SHARE",
            request=request,
            category="admin",
            recipient_name=name,
            share_name=share_name,
        )
    except Exception:
        logger.exception(
            f"Unexpected error granting share '{share_name}' to recipient '{name}'"
        )
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_GRANT_SHARE",
            request=request,
            category="admin",
            recipient_name=name,
            share_name=share_name,
        )


@router.get("/{name}/shares")
async def list_recipient_shares(
    name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """列出 recipient 被授权的所有 share。

    Args:
        name: Recipient 名称。

    Returns:
        授权记录列表。

    Raises:
        HTTPException: 如果 recipient 不存在。
    """
    audit_logger = get_audit_logger()
    service = AuthorizationService()
    try:
        shares = service.list_recipient_shares(name)
        return {"items": shares}
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_LIST_RECIPIENT_SHARES",
            request=request,
            category="admin",
            recipient_name=name,
        )
    except Exception:
        logger.exception(f"Unexpected error listing shares for recipient '{name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_LIST_RECIPIENT_SHARES",
            request=request,
            category="admin",
            recipient_name=name,
        )


@router.delete("/{name}/shares/{share_name}", status_code=204)
async def revoke_share_from_recipient(
    name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    share_name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """撤销 recipient 对 share 的访问权限。

    Args:
        name: Recipient 名称。
        share_name: Share 名称。

    Raises:
        HTTPException: 如果 recipient 或授权不存在。
    """
    audit_logger = get_audit_logger()
    service = AuthorizationService()
    try:
        revoked = service.revoke_share_from_recipient(name, share_name)
        if not revoked:
            raise DeltaSharingError(
                ErrorCode.AUTHORIZATION_NOT_FOUND,
                f"Authorization not found for recipient '{name}' and share '{share_name}'",
                status_code=404,
            )
        return None
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_REVOKE_SHARE",
            request=request,
            category="admin",
            recipient_name=name,
            share_name=share_name,
        )
    except Exception:
        logger.exception(
            f"Unexpected error revoking share '{share_name}' from recipient '{name}'"
        )
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_REVOKE_SHARE",
            request=request,
            category="admin",
            recipient_name=name,
            share_name=share_name,
        )
