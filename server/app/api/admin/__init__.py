"""
Admin API 路由模块

该模块包含 Delta Sharing Server 的管理 REST API，用于管理：
- Recipient 实体（创建、查询、更新、软删除）
- Share 授权（授权、撤销、查询）
- Share 实体管理（创建、删除、重命名、资产管理）
- Token 管理（生成、撤销、查询）

所有管理 API 路径前缀为 /delta-sharing/admin/v1
"""

from fastapi import APIRouter

from app.api.admin.recipients import router as recipients_router
from app.api.admin.shares import router as shares_router
from app.api.admin.tokens import router as tokens_router
from app.api.admin.share_management import router as share_management_router
from app.api.admin.sync import router as sync_router
from app.api.admin.audit_logs import router as audit_logs_router
from app.api.admin.config import router as config_router

admin_router = APIRouter(prefix="/admin/v1", tags=["admin"])

admin_router.include_router(recipients_router)
admin_router.include_router(shares_router)
admin_router.include_router(tokens_router)
admin_router.include_router(share_management_router)
admin_router.include_router(sync_router)
admin_router.include_router(audit_logs_router)
admin_router.include_router(config_router)

__all__ = ["admin_router"]
