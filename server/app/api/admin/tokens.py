"""
Admin API - Token 管理端点

该模块提供 Token 管理的 REST API 端点：
- POST /recipients/{name}/token - 为 recipient 生成新 token（响应包含 profileContent）
- GET /recipients/{name}/tokens - 列出 recipient 的所有 token
- DELETE /recipients/{name}/tokens/{token} - 撤销指定 token
"""

from typing import Optional

from fastapi import APIRouter, Path, Query, Request

from app.core.audit import get_audit_logger
from app.core.errors import ErrorCode, DeltaSharingError
from app.repositories.token_repository import TokenRepository
from app.services.recipient_service import RecipientService
from app.services.token_service import TokenService
from app.utils.audit_utils import raise_audited_error
from loguru import logger

router = APIRouter(prefix="/recipients", tags=["admin-tokens"])


@router.post("/{name}/token", status_code=201)
async def create_token(
    name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    require_authorized_shares: bool = Query(
        True, alias="requireAuthorizedShares", description="是否要求有授权的 share"
    ),
    expiration_hours: Optional[int] = Query(
        None,
        alias="expirationHours",
        description="Token过期小时数，None表示使用配置默认值，0表示永不过期",
    ),
    request: Request = None,
):
    """为 recipient 生成新的 Bearer Token。

    生成 token 前会验证：
    1. recipient 必须存在且处于激活状态
    2. recipient 必须至少有一个授权的 share（除非 requireAuthorizedShares=false）
    3. token 数量不能超过配额限制（默认最多 2 个）

    Token 明文仅在创建时返回一次，同时响应中直接包含完整的 Profile 内容。
    Profile 内容不持久化到数据库，调用者必须立即保存为 .share 文件。

    Args:
        name: Recipient 名称。
        require_authorized_shares: 是否要求有授权的 share。
        expiration_hours: Token过期小时数，None使用配置默认值，0表示永不过期。

    Returns:
        包含 bearerToken、tokenPrefix、expiresAt、profileContent 和提示信息。

    Raises:
        HTTPException: 如果验证失败。
    """
    audit_logger = get_audit_logger()
    recipient_service = RecipientService()
    token_service = TokenService()

    try:
        recipient = recipient_service.get_recipient_by_name(name)
        if not recipient:
            raise DeltaSharingError(
                ErrorCode.RECIPIENT_NOT_FOUND,
                f"Recipient '{name}' not found",
                status_code=404,
            )

        token_data = token_service.generate_token(
            recipient_id=recipient["recipient_id"],
            require_authorized_shares=require_authorized_shares,
            expiration_hours=expiration_hours,
        )
        return {
            "bearerToken": token_data["token"],
            "tokenPrefix": token_data["token_prefix"],
            "recipient_id": recipient["recipient_id"],
            "expiresAt": token_data["expires_at"],
            "profileContent": token_data["profile_data"],
            "message": "Token created. Save the profileContent as a .share file NOW - it will NOT be downloadable again.",
        }
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_CREATE_TOKEN",
            request=request,
            category="admin",
            recipient_name=name,
        )
    except Exception:
        logger.exception(f"Unexpected error creating token for recipient '{name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500),
            "ADMIN_CREATE_TOKEN",
            request=request,
            category="admin",
            recipient_name=name,
        )


@router.get("/{name}/tokens")
async def list_tokens(
    name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    includeExpired: bool = Query(
        False, alias="includeExpired", description="是否包含已过期的 token"
    ),
    request: Request = None,
):
    """列出 recipient 的所有 token。

    Args:
        name: Recipient 名称。
        include_expired: 是否包含已过期的 token。

    Returns:
        token 列表响应。

    Raises:
        HTTPException: 如果 recipient 不存在。
    """
    audit_logger = get_audit_logger()
    recipient_service = RecipientService()
    token_service = TokenService()

    try:
        recipient = recipient_service.get_recipient_by_name(name)
        if not recipient:
            raise DeltaSharingError(
                ErrorCode.RECIPIENT_NOT_FOUND,
                f"Recipient '{name}' not found",
                status_code=404,
            )

        tokens = token_service.list_recipient_tokens(
            recipient_id=recipient["recipient_id"],
            include_expired=includeExpired,
        )
        return {"items": tokens}
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_LIST_TOKENS",
            request=request,
            category="admin",
            recipient_name=name,
        )
    except Exception:
        logger.exception(f"Unexpected error listing tokens for recipient '{name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500),
            "ADMIN_LIST_TOKENS",
            request=request,
            category="admin",
            recipient_name=name,
        )


@router.delete("/{name}/tokens/{token_hash}", status_code=204)
async def revoke_token(
    name: str = Path(..., max_length=256, pattern=r"^[a-zA-Z0-9_\-\.]+$"),
    token_hash: str = Path(..., max_length=64, pattern=r"^[a-fA-F0-9]{64}$"),
    request: Request = None,
):
    """撤销指定的 token。

    通过 token_hash（SHA-256 哈希值）撤销 token。

    Args:
        name: Recipient 名称。
        token_hash: 要撤销的 token 的 SHA-256 哈希值。

    Returns:
        无内容响应。

    Raises:
        HTTPException: 如果 recipient 或 token 不存在。
    """
    audit_logger = get_audit_logger()
    recipient_service = RecipientService()
    token_repo = TokenRepository()

    try:
        recipient = recipient_service.get_recipient_by_name(name)
        if not recipient:
            raise DeltaSharingError(
                ErrorCode.RECIPIENT_NOT_FOUND,
                f"Recipient '{name}' not found",
                status_code=404,
            )

        success = token_repo.revoke(token_hash)
        if not success:
            raise DeltaSharingError(
                ErrorCode.INVALID_TOKEN,
                "Token not found",
                status_code=404,
            )
        return None
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_REVOKE_TOKEN",
            request=request,
            category="admin",
            recipient_name=name,
            token_hash=token_hash,
        )
    except Exception:
        logger.exception(f"Unexpected error revoking token for recipient '{name}'")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500),
            "ADMIN_REVOKE_TOKEN",
            request=request,
            category="admin",
            recipient_name=name,
            token_hash=token_hash,
        )
