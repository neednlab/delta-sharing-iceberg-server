"""
审计日志模块

该模块提供 Delta Sharing Server 的审计日志功能，是两流制日志架构中的
审计日志流（流 A）。审计日志记录所有 HTTP 请求的完整信息，包括：
- HTTP 层信息（method、path、status_code、duration 等）
- 客户端信息（IP、User-Agent）
- 资源信息（recipient_id、share、schema、table）
- 请求详情（query_params、predicate_hints 等）
- 响应摘要（files_returned、snapshot_id 等）
- 错误信息（code、message）
- 请求分类（category：data_plane / admin / health / internal）

日志以 JSONL 格式写入文件，按 category 分离存储路径：
- data_plane / health / internal → log/client_audit/client-audit-YYYY-MM-DD.jsonl
- admin                        → log/admin_audit/admin-audit-YYYY-MM-DD.jsonl

通过 request_id ContextVar 实现全链路追踪。

设计要点：
- 审计日志始终开启，不受 log_level 配置影响
- 通过 _recorded_ids 集合机制防止中间件和 handler 对同一请求产生双重记录
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextvars import ContextVar

from app.core.config import get_config


# 全链路追踪 request_id ContextVar（在 HTTP 中间件中注入）
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
# 防双重记录：已记录的 request_id 集合（handler 显式记录后加入）
# 使用集合而非 ContextVar，因为在某些 asyncio 场景下 ContextVar 传播不可靠
_recorded_ids: set = set()
_MAX_RECORDED_IDS = 100000


# category 到子目录 + 文件名前缀的映射
_CATEGORY_ROUTING: Dict[str, Dict[str, str]] = {
    "admin": {"subdir": "admin_audit", "prefix": "admin-audit"},
    "data_plane": {"subdir": "client_audit", "prefix": "client-audit"},
    "health": {"subdir": "client_audit", "prefix": "client-audit"},
    "internal": {"subdir": "client_audit", "prefix": "client-audit"},
}


class AuditLogger:
    """审计日志类

    负责将审计事件写入审计日志文件。按 category 分离写入不同目录和文件。
    日志文件按日期存储，格式为 JSONL，每行一条完整的结构化日志记录。

    Attributes:
        config: 全局配置实例。
        base_log_dir: 日志根目录路径（来自 logging.log_dir）。
        audit_log_level: 审计日志级别，控制 file_paths 等敏感字段是否记录。
    """

    def __init__(self):
        """初始化审计日志器。"""
        self.config = get_config()
        self.base_log_dir = Path(getattr(self.config.logging, "log_dir", "./log"))
        self.audit_log_level = getattr(self.config.logging, "audit_log_level", "INFO")
        # 预创建所有子目录
        for routing in _CATEGORY_ROUTING.values():
            subdir = self.base_log_dir / routing["subdir"]
            subdir.mkdir(parents=True, exist_ok=True)

    def _get_log_file(self, category: str) -> Path:
        """根据 category 获取对应的审计日志文件路径。

        Args:
            category: 请求分类（data_plane / admin / health / internal）。

        Returns:
            日志文件路径，如 log/client_audit/client-audit-2026-04-26.jsonl。
            未识别的 category 回退到 client_audit。
        """
        routing = _CATEGORY_ROUTING.get(category, _CATEGORY_ROUTING["data_plane"])
        date_str = datetime.now().strftime("%Y-%m-%d")
        subdir = self.base_log_dir / routing["subdir"]
        return subdir / f"{routing['prefix']}-{date_str}.jsonl"

    def get_request_id(self) -> str:
        """获取当前请求 ID。

        从 ContextVar 中读取，如果不存在则生成新的 UUID。

        Returns:
            UUID 格式的请求 ID 字符串。
        """
        rid = request_id_ctx.get()
        if rid is None:
            rid = str(uuid.uuid4())
            request_id_ctx.set(rid)
        return rid

    def is_recorded(self) -> bool:
        """检查当前请求是否已被 handler 显式记录审计日志。

        Returns:
            如果已记录返回 True，否则返回 False。
        """
        rid = self.get_request_id()
        return rid in _recorded_ids

    def mark_recorded(self) -> None:
        """标记当前请求已被 handler 显式记录审计日志。

        将当前 request_id 加入已记录集合，HTTP 中间件在请求离开时将
        不会自动补录基础审计日志，避免双重记录。

        集合大小达到上限时自动清理，防止内存泄漏。
        """
        rid = self.get_request_id()
        _recorded_ids.add(rid)
        if len(_recorded_ids) > _MAX_RECORDED_IDS:
            _recorded_ids.clear()

    def log(
        self,
        operation: str,
        category: str = "internal",
        operation_type: Optional[str] = None,
        recipient_id: Optional[str] = None,
        recipient_name: Optional[str] = None,
        share: Optional[str] = None,
        share_name: Optional[str] = None,
        schema: Optional[str] = None,
        table: Optional[str] = None,
        http_method: Optional[str] = None,
        http_path: Optional[str] = None,
        http_status_code: Optional[int] = None,
        http_duration_ms: Optional[int] = None,
        http_response_size_bytes: Optional[int] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        predicate_hints: Optional[List[str]] = None,
        json_predicate_hints: Optional[Dict[str, Any]] = None,
        limit_hint: Optional[int] = None,
        query_version: Optional[int] = None,
        query_timestamp: Optional[str] = None,
        query_starting_version: Optional[int] = None,
        query_ending_version: Optional[int] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        files_returned: Optional[int] = None,
        iceberg_snapshot_id: Optional[int] = None,
        delta_table_version: Optional[int] = None,
        response_format: Optional[str] = None,
        file_paths: Optional[List[str]] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        timestamp: Optional[int] = None,
        token_hash: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一条完整的审计日志。

        根据 category 将日志写入对应的子目录和文件。

        Args:
            operation: 操作标识（如 POST_QUERY、ADMIN_CREATE_RECIPIENT 等）。
            category: 请求分类（data_plane / admin / health / internal），
                      决定日志写入哪个文件：
                          admin       → admin_audit/admin-audit-YYYY-MM-DD.jsonl
                          data_plane/health/internal → client_audit/client-audit-YYYY-MM-DD.jsonl
            operation_type: 操作分类（query / metadata / admin_recipient 等）。
            recipient_id: 接收者 ID。
            recipient_name: 接收者名称（admin 操作时使用）。
            share / share_name / schema / table: 资源路径。
            http_method / http_path / http_status_code / http_duration_ms / http_response_size_bytes: HTTP 层信息。
            client_ip / user_agent: 客户端信息。
            predicate_hints / json_predicate_hints / limit_hint 等: 请求详情。
            files_returned / iceberg_snapshot_id / delta_table_version / response_format: 响应摘要。
            file_paths: 文件列表，仅 audit_log_level=DEBUG 时记录。
            error_code / error_message: 错误信息。
            timestamp: 毫秒时间戳，为 None 时使用当前时间。
            token_hash: Token SHA-256 哈希值（token 管理操作时使用）。
            extra: 额外自定义字段。
        """
        if timestamp is None:
            timestamp = int(datetime.now().timestamp() * 1000)

        # 构建完整日志条目
        log_entry: Dict[str, Any] = {
            "request_id": self.get_request_id(),
            "timestamp": timestamp,
            "category": category,
            "operation_type": operation_type,
            "operation": operation,
        }

        # HTTP 层子结构
        http_fields: Dict[str, Any] = {}
        if http_method is not None:
            http_fields["method"] = http_method
        if http_path is not None:
            http_fields["path"] = http_path
        if http_status_code is not None:
            http_fields["status_code"] = http_status_code
        if http_duration_ms is not None:
            http_fields["duration_ms"] = http_duration_ms
        if http_response_size_bytes is not None:
            http_fields["response_size_bytes"] = http_response_size_bytes
        if http_fields:
            log_entry["http"] = http_fields

        # 客户端子结构
        client_fields: Dict[str, Any] = {}
        if client_ip is not None:
            client_fields["ip"] = client_ip
        if user_agent is not None:
            client_fields["user_agent"] = user_agent
        if client_fields:
            log_entry["client"] = client_fields

        # 资源子结构
        resource_fields: Dict[str, Any] = {}
        if recipient_id is not None:
            resource_fields["recipient_id"] = recipient_id
        if recipient_name is not None:
            resource_fields["recipient_name"] = recipient_name
        if share is not None:
            resource_fields["share"] = share
        if share_name is not None:
            resource_fields["share_name"] = share_name
        if schema is not None:
            resource_fields["schema"] = schema
        if table is not None:
            resource_fields["table"] = table
        if token_hash is not None:
            resource_fields["token_hash"] = token_hash

        # 请求详情子结构
        request_details: Dict[str, Any] = {}
        if predicate_hints is not None:
            request_details["predicate_hints"] = predicate_hints
        if json_predicate_hints is not None:
            request_details["json_predicate_hints"] = json_predicate_hints
        if limit_hint is not None:
            request_details["limit_hint"] = limit_hint
        if query_version is not None:
            request_details["version"] = query_version
        if query_timestamp is not None:
            request_details["timestamp"] = query_timestamp
        if query_starting_version is not None:
            request_details["starting_version"] = query_starting_version
        if query_ending_version is not None:
            request_details["ending_version"] = query_ending_version
        if capabilities is not None:
            request_details["capabilities"] = capabilities

        # 响应子结构
        response_fields: Dict[str, Any] = {}
        if files_returned is not None:
            response_fields["files_returned"] = files_returned
        if iceberg_snapshot_id is not None:
            response_fields["iceberg_snapshot_id"] = iceberg_snapshot_id
        if delta_table_version is not None:
            response_fields["delta_table_version"] = delta_table_version
        if response_format is not None:
            response_fields["format"] = response_format
        if file_paths and self.audit_log_level == "DEBUG":
            response_fields["file_paths"] = file_paths

        # 错误子结构（始终包含，无错误时值为 null）
        error_fields: Dict[str, Any] = {
            "code": error_code,
            "message": error_message,
        }

        # 按条件追加子结构
        if resource_fields:
            log_entry["resource"] = resource_fields
        if request_details:
            log_entry["request_details"] = request_details
        if response_fields:
            log_entry["response"] = response_fields
        log_entry["error"] = error_fields

        # 合并额外字段
        if extra:
            log_entry.update(extra)

        # 根据 category 选择目标文件写入
        log_file = self._get_log_file(category)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        # 标记已记录（防双重记录）
        self.mark_recorded()


_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """获取全局审计日志实例。

    Returns:
        全局 AuditLogger 实例。
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def log_request(operation: str, **kwargs) -> None:
    """记录审计请求日志（便捷函数）。

    Args:
        operation: 操作类型。
        **kwargs: 传递给 log() 方法的其他参数。
    """
    logger = get_audit_logger()
    logger.log(operation=operation, **kwargs)
