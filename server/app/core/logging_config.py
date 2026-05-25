"""
loguru 日志全局配置模块

该模块负责 Delta Sharing Server 的 loguru 全局日志配置，实现两流制日志架构中的
应用日志流（流 B）。配置包括：
- 控制台 handler：彩色文本格式，INFO 级别
- 文件 handler：JSONL 结构化格式（loguru serialize=True），按日轮转，保留 30 天
- 通过 ContextVar 注入 request_id 实现全链路追踪

配置在 main.py 的 main() 函数中 load_config() 之后、init_database() 之前调用。
"""

import sys
from loguru import logger

from app.core.audit import request_id_ctx


def _request_id_filter(record: dict) -> bool:
    """为 loguru 日志记录注入当前 request_id。

    从 ContextVar 中读取当前请求上下文的 request_id，
    注入到 record["extra"]["request_id"] 中供日志格式化使用。

    loguru filter 函数必须返回 bool 值：
    - True：保留此日志记录，传递给 handler
    - False：丢弃此日志记录

    Args:
        record: loguru 内部日志记录字典。

    Returns:
        True：始终保留日志记录（注入 request_id 后不做过滤）。
    """
    rid = request_id_ctx.get(None)
    record["extra"]["request_id"] = rid if rid else "-"
    return True


def configure_logging(
    log_dir: str = "./log",
    log_level: str = "INFO",
    log_retention: str = "30 days",
) -> None:
    """配置 loguru 全局日志系统。

    移除默认 stderr handler，配置两个新 handler：
    1. 控制台 handler：彩色文本格式，便于开发调试
    2. 文件 handler：JSONL 格式（serialize=True），按日轮转，适合生产环境排障

    必须在请求上下文外也能正常工作（request_id 回退为 "-"）。

    Args:
        log_dir: 日志文件输出目录路径。
        log_level: 日志级别，控制文件 handler 的写入级别。
                   控制台始终为 INFO 级别。
        log_retention: 日志文件保留时长，如 "30 days"。
    """
    # 移除 loguru 默认的 stderr handler
    logger.remove()

    # 控制台 handler：彩色文本格式，INFO 级别
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[request_id]}</cyan> | "
            "<level>{message}</level>"
        ),
        filter=_request_id_filter,
        level="INFO",
        colorize=True,
        enqueue=True,
    )

    # 文件 handler：JSONL 结构化格式，按日轮转
    # 使用 serialize=True 实现 JSONL 输出（每条日志一行 JSON）
    logger.add(
        f"{log_dir}/app-{{time:YYYY-MM-DD}}.jsonl",
        filter=_request_id_filter,
        level=log_level.upper(),
        rotation="00:00",
        retention=log_retention,
        encoding="utf-8",
        enqueue=True,
        serialize=True,
    )

    logger.info(
        "Logging configured successfully: dir={} level={} retention={}",
        log_dir,
        log_level,
        log_retention,
    )
