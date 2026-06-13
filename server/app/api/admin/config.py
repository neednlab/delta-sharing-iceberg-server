"""
Admin API - 前端配置暴露端点

该模块提供前端需要的配置子集，包括：
- Token 配额限制 (max_tokens_per_recipient)
- Token 轮换周期 (rotation_period_hours)
- Token 默认过期时间 (default_expiration_hours)

端点路径: GET /admin/v1/config
"""

from fastapi import APIRouter, Depends, Request

from app.core.admin_auth import get_current_admin
from app.core.audit import get_audit_logger
from app.core.config import get_config
from app.core.errors import ErrorCode, DeltaSharingError
from app.utils.audit_utils import raise_audited_error
from loguru import logger

router = APIRouter(
    tags=["admin-config"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/config")
async def get_app_config(request: Request = None):
    """获取前端需要的应用配置子集。

    仅返回 token 相关的前端必需配置，不暴露服务器的完整 config.yaml 内容，
    以保证安全性。

    Returns:
        dict: 包含 token 配置子集的 JSON 响应。
        格式: {"token": {"max_tokens_per_recipient": <int>,
                         "rotation_period_hours": <int>,
                         "default_expiration_hours": <int>}}
    """
    audit_logger = get_audit_logger()
    try:
        config = get_config()
        return {
            "token": {
                "max_tokens_per_recipient": config.token.max_tokens_per_recipient,
                "rotation_period_hours": config.token.rotation_period_hours,
                "default_expiration_hours": config.token.expiration_hours,
            }
        }
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_GET_CONFIG",
            request=request,
            category="admin",
        )
    except Exception:
        logger.exception("Unexpected error getting app config")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500),
            "ADMIN_GET_CONFIG",
            request=request,
            category="admin",
        )
