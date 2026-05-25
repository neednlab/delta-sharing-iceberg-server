"""
Admin API - Recipient 管理端点

该模块提供 Recipient 实体的 REST API 端点：
- POST /recipients - 创建 recipient
- GET /recipients - 列出所有 recipient
- GET /recipients/{name} - 获取单个 recipient
- PUT /recipients/{name} - 更新 recipient
- DELETE /recipients/{name} - 软删除 recipient
"""

from typing import Optional

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field

from app.core.audit import get_audit_logger
from app.core.errors import ErrorCode, DeltaSharingError
from app.services.recipient_service import RecipientService
from app.utils.audit_utils import raise_audited_error
from loguru import logger

router = APIRouter(prefix="/recipients", tags=["admin-recipients"])


class CreateRecipientBody(BaseModel):
    """创建 Recipient 的 JSON 请求体（P0 修复：避免参数出现在 URL 中）。"""

    name: str = Field(..., description="Recipient 名称")
    comment: Optional[str] = Field(None, description="Recipient 描述")


class UpdateRecipientBody(BaseModel):
    """更新 Recipient 的 JSON 请求体（P0 修复：避免参数出现在 URL 中）。"""

    newName: Optional[str] = Field(None, description="新名称")
    comment: Optional[str] = Field(None, description="Recipient 描述")
    isActive: Optional[bool] = Field(None, description="激活状态")


@router.post("", status_code=201)
async def create_recipient(
    body: CreateRecipientBody,
    request: Request = None,
):
    """创建新的 Recipient（通过 JSON 请求体传递参数，避免参数出现在 URL 中）。"""
    audit_logger = get_audit_logger()
    service = RecipientService()
    name = body.name
    comment = body.comment
    try:
        recipient = service.create_recipient(name=name, comment=comment)
        return recipient
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_CREATE_RECIPIENT",
            request=request,
            category="admin",
            recipient_name=name,
        )
    except Exception:
        logger.exception(f"Unexpected error creating recipient '{name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500),
            "ADMIN_CREATE_RECIPIENT",
            request=request,
            category="admin",
            recipient_name=name,
        )


@router.get("")
async def list_recipients(
    maxResults: Optional[int] = Query(None, alias="maxResults", ge=1, le=1000),
    pageToken: Optional[str] = Query(None, alias="pageToken"),
    request: Request = None,
):
    """列出所有 Recipient，支持分页。"""
    audit_logger = get_audit_logger()
    service = RecipientService()
    try:
        return service.list_recipients(max_results=maxResults, page_token=pageToken)
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_LIST_RECIPIENTS",
            request=request,
            category="admin",
        )
    except Exception:
        logger.exception("Unexpected error listing recipients")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500),
            "ADMIN_LIST_RECIPIENTS",
            request=request,
            category="admin",
        )


@router.get("/{name}")
async def get_recipient(
    name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """获取指定 Recipient 的详细信息。"""
    audit_logger = get_audit_logger()
    service = RecipientService()
    try:
        recipient = service.get_recipient_by_name(name)
        if not recipient:
            raise DeltaSharingError(
                ErrorCode.RECIPIENT_NOT_FOUND,
                f"Recipient '{name}' not found",
                status_code=404,
            )
        return recipient
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_GET_RECIPIENT",
            request=request,
            category="admin",
            recipient_name=name,
        )
    except Exception:
        logger.exception(f"Unexpected error getting recipient '{name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500),
            "ADMIN_GET_RECIPIENT",
            request=request,
            category="admin",
            recipient_name=name,
        )


@router.put("/{name}")
async def update_recipient(
    body: UpdateRecipientBody,
    name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """更新 Recipient（通过 JSON 请求体传递参数，避免参数出现在 URL 中）。"""
    audit_logger = get_audit_logger()
    service = RecipientService()
    try:
        recipient = service.update_recipient(
            name=name,
            new_name=body.newName,
            comment=body.comment,
            is_active=body.isActive,
        )
        if not recipient:
            raise DeltaSharingError(
                ErrorCode.RECIPIENT_NOT_FOUND,
                f"Recipient '{name}' not found",
                status_code=404,
            )
        return recipient
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_UPDATE_RECIPIENT",
            request=request,
            category="admin",
            recipient_name=name,
        )
    except Exception:
        logger.exception(f"Unexpected error updating recipient '{name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500),
            "ADMIN_UPDATE_RECIPIENT",
            request=request,
            category="admin",
            recipient_name=name,
        )


@router.delete("/{name}", status_code=204)
async def delete_recipient(
    name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    request: Request = None,
):
    """软删除 Recipient（设置 is_active = 0）。"""
    audit_logger = get_audit_logger()
    service = RecipientService()
    try:
        deleted = service.delete_recipient(name)
        if not deleted:
            raise DeltaSharingError(
                ErrorCode.RECIPIENT_NOT_FOUND,
                f"Recipient '{name}' not found",
                status_code=404,
            )
        return None
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_DELETE_RECIPIENT",
            request=request,
            category="admin",
            recipient_name=name,
        )
    except Exception:
        logger.exception(f"Unexpected error deleting recipient '{name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500),
            "ADMIN_DELETE_RECIPIENT",
            request=request,
            category="admin",
            recipient_name=name,
        )
