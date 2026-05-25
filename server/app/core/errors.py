"""
错误定义模块

该模块定义了 Delta Sharing Server 中使用的所有错误类型和错误代码。
包括标准错误代码枚举和自定义异常类。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Dict, Any


class ErrorCode(Enum):
    """Delta Sharing 错误代码枚举

    定义了服务器可能返回的所有错误类型。

    Attributes:
        AUTHENTICATION_HEADER_MISSING: 认证头缺失。
        AUTHENTICATION_HEADER_INVALID: 认证头格式无效。
        INVALID_TOKEN: Token 无效。
        TOKEN_EXPIRED: Token 已过期。
        TOKEN_REVOKED: Token 已被撤销。
        TOKEN_MALFORMED: Token 格式错误。
        ACCESS_DENIED: 访问被拒绝。
        SHARE_NOT_FOUND: Share 不存在。
        SCHEMA_NOT_FOUND: Schema 不存在。
        TABLE_NOT_FOUND: 表不存在。
        TABLE_NOT_SUPPORTED: 表格式不支持。
        INVALID_REQUEST: 无效的请求。
        INTERNAL_ERROR: 内部服务器错误。
        COS_ACCESS_ERROR: COS 存储访问错误。
        RECIPIENT_NOT_FOUND: Recipient 不存在。
        RECIPIENT_ALREADY_EXISTS: Recipient 已存在。
        RECIPIENT_INACTIVE: Recipient 未激活。
        SHARE_ACCESS_DENIED: Share 访问被拒绝。
        AUTHORIZATION_ALREADY_EXISTS: 授权已存在。
        AUTHORIZATION_NOT_FOUND: 授权不存在。
        MAX_TOKENS_EXCEEDED: Token 数量超出限制。
        NO_SHARES_ASSIGNED: 未分配 Share。
        SHARE_ALREADY_EXISTS: Share 已存在。
        SCHEMA_ALREADY_EXISTS: Schema 已存在。
        TABLE_ALREADY_EXISTS: Table 已存在。
    """

    AUTHENTICATION_HEADER_MISSING = "AUTHENTICATION_HEADER_MISSING"
    AUTHENTICATION_HEADER_INVALID = "AUTHENTICATION_HEADER_INVALID"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    TOKEN_MALFORMED = "TOKEN_MALFORMED"
    ACCESS_DENIED = "ACCESS_DENIED"
    SHARE_NOT_FOUND = "SHARE_NOT_FOUND"
    SCHEMA_NOT_FOUND = "SCHEMA_NOT_FOUND"
    TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
    TABLE_NOT_SUPPORTED = "TABLE_NOT_SUPPORTED"
    INVALID_REQUEST = "INVALID_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    COS_ACCESS_ERROR = "COS_ACCESS_ERROR"
    RECIPIENT_NOT_FOUND = "RECIPIENT_NOT_FOUND"
    RECIPIENT_ALREADY_EXISTS = "RECIPIENT_ALREADY_EXISTS"
    RECIPIENT_INACTIVE = "RECIPIENT_INACTIVE"
    SHARE_ACCESS_DENIED = "SHARE_ACCESS_DENIED"
    AUTHORIZATION_ALREADY_EXISTS = "AUTHORIZATION_ALREADY_EXISTS"
    AUTHORIZATION_NOT_FOUND = "AUTHORIZATION_NOT_FOUND"
    MAX_TOKENS_EXCEEDED = "MAX_TOKENS_EXCEEDED"
    NO_SHARES_ASSIGNED = "NO_SHARES_ASSIGNED"
    SHARE_ALREADY_EXISTS = "SHARE_ALREADY_EXISTS"
    SCHEMA_ALREADY_EXISTS = "SCHEMA_ALREADY_EXISTS"
    TABLE_ALREADY_EXISTS = "TABLE_ALREADY_EXISTS"
    DLC_NOT_CONFIGURED = "DLC_NOT_CONFIGURED"
    DLC_API_ERROR = "DLC_API_ERROR"
    INVALID_PARAMETER_VALUE = "INVALID_PARAMETER_VALUE"
    RESOURCE_DOES_NOT_EXIST = "RESOURCE_DOES_NOT_EXIST"


class DeltaSharingError(Exception):
    """Delta Sharing 自定义异常类

    该异常类用于表示 Delta Sharing Server 运行过程中发生的所有错误。
    包含错误代码、消息、HTTP 状态码和详细信息。

    Attributes:
        error_code: 错误代码。
        message: 错误消息。
        status_code: HTTP 状态码。
        details: 额外的错误详情字典。
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        """初始化 DeltaSharingError 异常。

        Args:
            error_code: 错误代码枚举值。
            message: 错误消息描述。
            status_code: HTTP 状态码，默认为 400。
            details: 额外的错误详情字典，默认为空字典。
        """
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """将异常转换为字典格式。

        用于生成 API 错误响应的 JSON 格式。
        委托 build_error_dict() 构造标准格式字典。

        Returns:
            包含 errorCode、message 和可选 details 的字典。
        """
        return build_error_dict(self.error_code, self.message, self.details)


class TokenQuotaExceededError(DeltaSharingError):
    """Token 配额超出异常

    当 recipient 持有的有效 token 数量超过限制时抛出。
    自动绑定 ErrorCode.MAX_TOKENS_EXCEEDED 和 HTTP 409 状态码，
    并携带 details.max_tokens 字段记录配额上限。
    """

    def __init__(self, message: str = "Token quota exceeded", max_tokens: int = 2):
        """初始化异常。

        Args:
            message: 错误消息。
            max_tokens: 最大 token 配额。
        """
        super().__init__(
            ErrorCode.MAX_TOKENS_EXCEEDED,
            message,
            status_code=409,
            details={"max_tokens": max_tokens},
        )


class RecipientInactiveError(DeltaSharingError):
    """Recipient 未激活异常

    当尝试为未激活的 recipient 生成 token 时抛出。
    自动绑定 ErrorCode.RECIPIENT_INACTIVE 和 HTTP 400 状态码。
    """

    def __init__(self, message: str = "Recipient is inactive"):
        """初始化异常。

        Args:
            message: 错误消息。
        """
        super().__init__(
            ErrorCode.RECIPIENT_INACTIVE,
            message,
            status_code=400,
        )


class NoSharesAssignedError(DeltaSharingError):
    """未分配 Share 异常

    当 recipient 没有任何授权的 share 时抛出。
    自动绑定 ErrorCode.NO_SHARES_ASSIGNED 和 HTTP 400 状态码。
    """

    def __init__(self, message: str = "No shares assigned to recipient"):
        """初始化异常。

        Args:
            message: 错误消息。
        """
        super().__init__(
            ErrorCode.NO_SHARES_ASSIGNED,
            message,
            status_code=400,
        )


def build_error_dict(
    error_code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """创建标准错误响应字典。

    这是一个纯数据构造器，用于快速创建标准格式的错误响应字典，
    供 DeltaSharingError.to_dict() 等方法内部使用。

    Args:
        error_code: 错误代码枚举值。
        message: 错误消息。
        details: 额外的错误详情字典（可选）。

    Returns:
        标准格式的错误响应字典，包含 errorCode 和 message 字段，
        可选 details 字段。
    """
    response = {"errorCode": error_code.value, "message": message}
    if details:
        response["details"] = details
    return response
