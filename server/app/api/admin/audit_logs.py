"""
审计日志管理API

提供审计日志文件列表查询、日志条目分页查询和关键字筛选功能。
支持三种日志类型：admin_audit、client_audit、app log。
"""

import json
import re
from pathlib import Path

from fastapi import APIRouter, Query, Request

from app.core.audit import get_audit_logger
from app.core.errors import ErrorCode, DeltaSharingError
from app.utils.audit_utils import raise_audited_error
from loguru import logger

router = APIRouter(prefix="/audit-logs", tags=["admin-audit-logs"])

# 日志根目录（相对 server/ 目录）
LOG_BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "log"

# 日志类型到子目录的映射
LOG_TYPE_DIR_MAP = {
    "admin_audit": "admin_audit",
    "client_audit": "client_audit",
    "app": "",  # app 日志直接在 log/ 根目录下
}

# 日志类型到文件名前缀的映射
LOG_TYPE_PREFIX_MAP = {
    "admin_audit": "admin-audit",
    "client_audit": "client-audit",
    "app": "app",
}

# 允许的日志类型
VALID_LOG_TYPES = set(LOG_TYPE_DIR_MAP.keys())


def _get_log_file_path(log_type: str, date: str) -> Path:
    """
    根据日志类型和日期获取日志文件路径

    文件名格式:
      - admin_audit: log/admin_audit/admin-audit-{date}.jsonl
      - client_audit: log/client_audit/client-audit-{date}.jsonl
      - app:         log/app-{date}.jsonl

    Args:
        log_type: 日志类型
        date: 日期字符串，格式 YYYY-MM-DD

    Returns:
        日志文件的完整路径
    """
    prefix = LOG_TYPE_PREFIX_MAP[log_type]
    subdir = LOG_TYPE_DIR_MAP[log_type]

    if subdir:
        return LOG_BASE_DIR / subdir / f"{prefix}-{date}.jsonl"
    else:
        return LOG_BASE_DIR / f"{prefix}-{date}.jsonl"


def _validate_log_type(log_type: str) -> None:
    """
    校验日志类型参数，防止路径遍历攻击

    Args:
        log_type: 日志类型字符串

    Raises:
        DeltaSharingError: 如果日志类型不合法
    """
    if log_type not in VALID_LOG_TYPES:
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            f"无效的日志类型: {log_type}，有效值为: {', '.join(sorted(VALID_LOG_TYPES))}",
            status_code=400,
        )


def _validate_date(date: str) -> None:
    """
    校验日期参数格式和安全性，防止路径遍历攻击

    Args:
        date: 日期字符串

    Raises:
        DeltaSharingError: 如果日期格式不合法或包含路径遍历字符
    """
    # 拒绝路径遍历字符
    if ".." in date or "/" in date or "\\" in date:
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            "日期参数包含非法字符",
            status_code=400,
        )

    # 校验日期格式 YYYY-MM-DD
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise DeltaSharingError(
            ErrorCode.INVALID_PARAMETER_VALUE,
            f"日期格式无效: {date}，应为 YYYY-MM-DD 格式",
            status_code=400,
        )


def _get_nested_value(data: dict, column_path: str) -> str:
    """
    从嵌套字典中按路径获取值，转为字符串用于模糊匹配比较

    支持点号分隔的嵌套路径，如 "record.level.name" -> data["record"]["level"]["name"]

    Args:
        data: 日志条目字典
        column_path: 点号分隔的列路径

    Returns:
        字段值的字符串表示，如果路径不存在则返回空字符串
    """
    keys = column_path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return ""
    # 将值转为字符串进行模糊匹配比较
    if current is None:
        return ""
    if isinstance(current, (dict, list)):
        return str(current)
    return str(current)


def _strip_client_audit_entry(entry: dict) -> dict:
    """
    裁减 client_audit 日志条目，仅保留前端展示所需字段，删除冗余嵌套对象以减少响应数据量

    将嵌套字段展平到顶层后，删除 category、operation_type、http、client、
    resource、error、response 等冗余字段。

    保留字段：request_id、timestamp、operation、recipient_id、query_object、
    http_status_code、client_ip、client_user_agent、files_returned

    Args:
        entry: 原始 client_audit 日志条目（完整结构）

    Returns:
        展平并裁减后的日志条目
    """
    result: dict = {}

    if "request_id" in entry:
        result["request_id"] = entry["request_id"]
    if "timestamp" in entry:
        result["timestamp"] = entry["timestamp"]
    if "operation" in entry:
        result["operation"] = entry["operation"]

    resource = entry.get("resource", {})
    if isinstance(resource, dict):
        if resource.get("recipient_id") is not None:
            result["recipient_id"] = resource["recipient_id"]
        query_parts = [
            resource.get("share"),
            resource.get("schema"),
            resource.get("table"),
        ]
        query_parts = [p for p in query_parts if p]
        if query_parts:
            result["query_object"] = ".".join(query_parts)

    http = entry.get("http", {})
    if isinstance(http, dict) and http.get("status_code") is not None:
        result["http_status_code"] = http["status_code"]

    client = entry.get("client", {})
    if isinstance(client, dict):
        if client.get("ip") is not None:
            result["client_ip"] = client["ip"]
        if client.get("user_agent") is not None:
            result["client_user_agent"] = client["user_agent"]

    response = entry.get("response", {})
    if isinstance(response, dict) and response.get("files_returned") is not None:
        result["files_returned"] = response["files_returned"]

    return result


def _flatten_record(entry: dict) -> dict:
    """
    将 app log 的嵌套 record 结构扁平化

    app log 结构: {"text": "...", "record": {"elapsed": ..., "level": ..., ...}}
    扁平化为: {"time": "...", "level": "...", "message": "...", "module": "...", ...}

    Args:
        entry: 原始日志条目

    Returns:
        扁平化后的日志条目
    """
    record = entry.get("record", {})
    if not isinstance(record, dict):
        return entry

    result = {}

    # 提取 record.time 的格式化时间
    time_obj = record.get("time", {})
    if isinstance(time_obj, dict):
        result["time"] = time_obj.get("repr", "")

    # 提取 record.level 名称
    level_obj = record.get("level", {})
    if isinstance(level_obj, dict):
        result["level"] = level_obj.get("name", "")

    # 提取关键字段
    result["message"] = record.get("message", "")
    result["module"] = record.get("module", "")
    result["function"] = record.get("function", "")
    result["line"] = record.get("line", "")
    result["name"] = record.get("name", "")

    # 提取 request_id
    extra = record.get("extra", {})
    if isinstance(extra, dict):
        result["request_id"] = extra.get("request_id", "")

    # 保留异常信息
    exception = record.get("exception")
    if exception is not None:
        result["exception"] = (
            str(exception) if not isinstance(exception, str) else exception
        )

    return result


def _scan_log_files() -> dict[str, list[str]]:
    """
    扫描日志目录，返回所有可用的日志文件按类型分组的日期列表

    Returns:
        字典，键为日志类型，值为日期列表（降序排列）
    """
    result: dict[str, list[str]] = {
        "admin_audit": [],
        "client_audit": [],
        "app": [],
    }

    # admin_audit: log/admin_audit/admin-audit-{date}.jsonl
    admin_dir = LOG_BASE_DIR / "admin_audit"
    if admin_dir.exists() and admin_dir.is_dir():
        for f in sorted(admin_dir.glob("admin-audit-*.jsonl"), reverse=True):
            date_match = re.match(r"admin-audit-(\d{4}-\d{2}-\d{2})\.jsonl", f.name)
            if date_match:
                result["admin_audit"].append(date_match.group(1))

    # client_audit: log/client_audit/client-audit-{date}.jsonl
    client_dir = LOG_BASE_DIR / "client_audit"
    if client_dir.exists() and client_dir.is_dir():
        for f in sorted(client_dir.glob("client-audit-*.jsonl"), reverse=True):
            date_match = re.match(r"client-audit-(\d{4}-\d{2}-\d{2})\.jsonl", f.name)
            if date_match:
                result["client_audit"].append(date_match.group(1))

    # app: log/app-{date}.jsonl
    for f in sorted(LOG_BASE_DIR.glob("app-*.jsonl"), reverse=True):
        date_match = re.match(r"app-(\d{4}-\d{2}-\d{2})\.jsonl", f.name)
        if date_match:
            result["app"].append(date_match.group(1))

    return result


@router.get("")
async def list_audit_logs(request: Request = None):
    """
    获取所有可用的日志文件列表

    扫描 log/ 目录下的三种日志文件，按类型分组返回日期列表。

    Returns:
        按日志类型分组的日期列表，日期降序排列
    """
    audit_logger = get_audit_logger()
    try:
        return _scan_log_files()
    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_LIST_AUDIT_LOGS",
            request=request,
            category="admin",
        )
    except Exception:
        logger.exception("Unexpected error scanning log files")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_LIST_AUDIT_LOGS",
            request=request,
            category="admin",
        )


@router.get("/{log_type}")
async def get_audit_log_entries(
    log_type: str,
    date: str = Query(..., description="日志日期，格式 YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(50, ge=1, le=200, description="每页条数，最大200"),
    filters: str | None = Query(
        None,
        description='JSON字符串，格式为 {"列名": "搜索关键字"}，支持多列模糊匹配（大小写不敏感），'
        '例如 {"http.status_code": "40"} 可匹配 400, 401, 403 等',
    ),
    request: Request = None,
):
    """
    分页查询指定日期和类型的日志条目

    支持按多列进行模糊匹配筛选（关键字包含即可，大小写不敏感）。
    对于 app log 类型，自动将嵌套的 record 结构扁平化。

    Args:
        log_type: 日志类型（admin_audit / client_audit / app）
        date: 日志日期
        page: 页码
        page_size: 每页条数（上限200）
        filters: JSON编码的列过滤条件，如 {"http.status_code": "40"}

    Returns:
        分页的日志条目及元数据
    """
    audit_logger = get_audit_logger()

    try:
        # 参数校验
        _validate_log_type(log_type)
        _validate_date(date)

        # 确保 page_size 不超过上限
        if page_size > 200:
            page_size = 200

        # 构建文件路径并检查存在性
        file_path = _get_log_file_path(log_type, date)
        if not file_path.exists() or not file_path.is_file():
            raise DeltaSharingError(
                ErrorCode.RESOURCE_DOES_NOT_EXIST,
                f"日志文件不存在: {log_type} ({date})",
                status_code=404,
            )

        # 解析过滤条件（JSON字符串 -> 字典）
        filters_dict: dict[str, str] = {}
        if filters:
            try:
                filters_dict = json.loads(filters)
                if not isinstance(filters_dict, dict):
                    filters_dict = {}
            except (json.JSONDecodeError, ValueError):
                filters_dict = {}

        # 逐行读取并处理日志内容
        entries: list[dict] = []
        total = 0

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    if not isinstance(entry, dict):
                        continue

                    # app log 需要扁平化
                    if log_type == "app":
                        entry = _flatten_record(entry)
                    # client_audit 需要裁减冗余字段
                    elif log_type == "client_audit":
                        entry = _strip_client_audit_entry(entry)

                    # 多列模糊匹配过滤（AND逻辑，大小写不敏感）
                    if filters_dict:
                        skip = False
                        for col, keyword in filters_dict.items():
                            cell_value = _get_nested_value(entry, col)
                            if keyword.lower() not in cell_value.lower():
                                skip = True
                                break
                        if skip:
                            continue

                    total += 1
                except (json.JSONDecodeError, ValueError):
                    # 跳过无法解析的行
                    continue

        # 计算分页
        total_pages = max(1, (total + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        # 重新遍历（这次提取需要的页）
        current_idx = 0
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    if not isinstance(entry, dict):
                        continue

                    if log_type == "app":
                        entry = _flatten_record(entry)
                    elif log_type == "client_audit":
                        entry = _strip_client_audit_entry(entry)

                    # 多列模糊匹配过滤（AND逻辑，大小写不敏感）
                    if filters_dict:
                        skip = False
                        for col, keyword in filters_dict.items():
                            cell_value = _get_nested_value(entry, col)
                            if keyword.lower() not in cell_value.lower():
                                skip = True
                                break
                        if skip:
                            continue

                    if current_idx >= start_idx and current_idx < end_idx:
                        entries.append(entry)

                    current_idx += 1

                    if current_idx >= end_idx:
                        break
                except (json.JSONDecodeError, ValueError):
                    continue

        return {
            "log_type": log_type,
            "date": date,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "entries": entries,
        }

    except DeltaSharingError as e:
        raise_audited_error(
            audit_logger,
            e,
            "ADMIN_GET_AUDIT_LOG_ENTRIES",
            request=request,
            category="admin",
            log_type=log_type,
            date=date,
        )
    except IOError as e:
        logger.exception(f"IO error reading log file: {log_type} ({date})")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR,
                f"读取日志文件失败: {str(e)}",
                status_code=500,
            ),
            "ADMIN_GET_AUDIT_LOG_ENTRIES",
            request=request,
            category="admin",
            log_type=log_type,
            date=date,
        )
    except Exception:
        logger.exception(f"Unexpected error reading log entries: {log_type} ({date})")
        raise_audited_error(
            audit_logger,
            DeltaSharingError(
                ErrorCode.INTERNAL_ERROR, "Internal server error", status_code=500
            ),
            "ADMIN_GET_AUDIT_LOG_ENTRIES",
            request=request,
            category="admin",
            log_type=log_type,
            date=date,
        )
