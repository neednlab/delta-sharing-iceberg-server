"""
业务服务模块

该模块包含 Delta Sharing Server 的核心业务逻辑服务：
- ShareService: Share、Schema、Table 的列表查询服务
- TableService: 表配置管理服务
- IcebergService: Iceberg 表元数据和数据文件管理服务
- RecipientService: Recipient 实体的完整生命周期管理
- AuthorizationService: Recipient-Share 授权关系管理
- TokenService: Bearer Token 配额管理和验证

底层数据访问层（Repository）：
- RecipientShareRepository: recipient_shares 表的 CRUD
- RecipientRepository: recipients 表的 CRUD
"""

from app.services.share_service import ShareService
from app.services.table_service import TableService
from app.services.iceberg_service import IcebergService
from app.services.predicate_service import PredicateService
from app.services.recipient_service import RecipientService
from app.services.authorization_service import AuthorizationService
from app.services.token_service import (
    TokenService,
)

# Token 服务相关异常已迁移至 app.core.errors 统一管理
from app.core.errors import (
    TokenQuotaExceededError,
    RecipientInactiveError,
    NoSharesAssignedError,
)

__all__ = [
    "ShareService",
    "TableService",
    "IcebergService",
    "PredicateService",
    "RecipientService",
    "AuthorizationService",
    "TokenService",
    "TokenQuotaExceededError",
    "RecipientInactiveError",
    "NoSharesAssignedError",
]
