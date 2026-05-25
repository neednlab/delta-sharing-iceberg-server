"""
健康检查路由模块

该模块定义了服务器的健康检查和变更通知 API 端点。
包括：
- GET /health - 健康检查端点
- GET /delta-sharing/changes - 变更通知端点（未实现）
"""

from fastapi import APIRouter, Request, HTTPException
from app.core.errors import DeltaSharingError, ErrorCode
from app.core.audit import get_audit_logger

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(request: Request = None):
    """健康检查端点。

    用于检查服务器是否正常运行。同时记录审计日志。

    Returns:
        dict: 包含状态信息的字典。
    """
    audit_logger = get_audit_logger()
    audit_logger.log(
        operation="HEALTH_CHECK",
        category="health",
        operation_type="health",
        http_method="GET",
        http_path="/health",
        http_status_code=200,
    )
    return {"status": "healthy"}


@router.get("/delta-sharing/changes")
async def get_changes(request: Request):
    """变更通知端点。

    该端点尚未实现，返回内部错误。

    Args:
        request: HTTP 请求对象。

    Returns:
        HTTPException: 总是返回 500 错误。

    Raises:
        HTTPException: 始终抛出 500 错误。
    """
    error = DeltaSharingError(
        error_code=ErrorCode.INTERNAL_ERROR,
        message="The /changes endpoint is not supported by this server",
        status_code=500,
    )
    raise HTTPException(status_code=500, detail=error.to_dict())
