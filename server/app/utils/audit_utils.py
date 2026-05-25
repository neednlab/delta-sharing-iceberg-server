"""
审计日志错误处理工具模块

封装 routes 层中反复出现的「构造 DeltaSharingError → 写入审计日志 → 抛出 HTTPException」
三步骤为单次调用，供 query.py 和 metadata.py 复用。
"""

from dataclasses import dataclass
from typing import Optional, List
from fastapi import HTTPException, Request
from app.core.errors import DeltaSharingError
from app.utils.request_utils import get_client_ip


@dataclass
class QueryAuditContext:
    """查询审计上下文数据类。

    封装查询请求的审计日志所需的所有上下文字段，
    替代查询路由中 18+ 个独立参数，提升可读性和可维护性。

    Attributes:
        share: Share 名称。
        schema: Schema 名称。
        table: 表名称。
        delta_table_version: Delta 表版本号。
        iceberg_snapshot_id: Iceberg 快照 ID。
        files_returned: 返回的文件数量。
        recipient_id: 接收者 ID。
        query_version: 查询版本号（时间旅行）。
        query_timestamp: 查询时间戳（时间旅行）。
        query_starting_version: 查询起始版本（CDF）。
        query_ending_version: 查询结束版本（CDF）。
        file_paths: 返回的文件路径列表（DEBUG 日志级别时填充）。
    """

    share: str
    schema: str
    table: str
    delta_table_version: int
    iceberg_snapshot_id: int
    files_returned: int
    recipient_id: str
    query_version: Optional[int] = None
    query_timestamp: Optional[str] = None
    query_starting_version: Optional[int] = None
    query_ending_version: Optional[int] = None
    file_paths: Optional[List[str]] = None

    def to_audit_dict(self) -> dict:
        """转换为审计日志参数字典，过滤 None 值字段。

        Returns:
            包含所有非 None 字段的字典。
        """
        return {k: v for k, v in self.__dict__.items() if v is not None}


def raise_audited_error(
    audit_logger,
    error: DeltaSharingError,
    operation: str,
    request: Request | None = None,
    category: str = "data_plane",
    **kwargs,
) -> None:
    """记录审计日志后抛出带错误详情的 HTTPException。

    自动从 request 对象提取 client_ip 和 user_agent 字段，
    其余字段通过 **kwargs 透传至 audit_logger.log()。

    Args:
        audit_logger: 审计日志记录器实例。
        error: DeltaSharingError 错误对象，包含 error_code、message、status_code。
        operation: 操作名称（如 "POST_QUERY"、"GET_METADATA"）。
        request: FastAPI Request 对象，用于提取客户端信息，可为 None。
        category: 审计日志分类，默认为 "data_plane"。
        **kwargs: 透传至 audit_logger.log() 的额外字段（如 share、schema、table 等）。

    Raises:
        HTTPException: 始终抛出，状态码和详情来自 error 参数。
    """
    client_ip = get_client_ip(request) if request else None
    user_agent = request.headers.get("User-Agent") if request else None

    audit_logger.log(
        operation=operation,
        category=category,
        http_status_code=error.status_code,
        error_code=error.error_code.value,
        error_message=error.message,
        client_ip=client_ip,
        user_agent=user_agent,
        **kwargs,
    )

    raise HTTPException(status_code=error.status_code, detail=error.to_dict())
