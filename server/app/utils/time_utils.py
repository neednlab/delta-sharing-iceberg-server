"""
时间工具模块

该模块提供统一的时间戳工具函数，确保整个项目后端的时间处理行为一致且可测试。
所有时间戳均使用 UTC 时区，返回 UNIX 整数型时间戳（秒），与数据库存储格式保持一致。

提供的公开函数：
- now_ts(): 获取当前 UTC 秒级 UNIX 时间戳
- ts_to_datetime(): 将 UNIX 时间戳转换为 UTC aware datetime 对象
- parse_iso8601_timestamp(): 将 ISO8601 格式字符串解析为毫秒时间戳
"""

from datetime import datetime, timezone


def now_ts() -> int:
    """获取当前 UTC 时间的 UNIX 整数时间戳（秒）。

    统一使用 UTC 时区获取当前时间，确保所有时间戳字段的一致性，
    与 SQLite 数据库中 DEFAULT (strftime('%s', 'now')) 的语义保持一致。

    Returns:
        当前时间的 UNIX 秒级时间戳（整数）。
    """
    return int(datetime.now(timezone.utc).timestamp())


def ts_to_datetime(ts: int) -> datetime:
    """将 UNIX 整数时间戳转换为带 UTC 时区的 datetime 对象。

    该函数用于将数据库中存储的整数时间戳转换为可读的 datetime 对象，
    例如生成 token profile 中的 expirationTime 字段（ISO 8601 格式字符串）。

    Args:
        ts: UNIX 秒级时间戳（整数）。

    Returns:
        带 UTC 时区的 datetime 对象。
    """
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def parse_iso8601_timestamp(timestamp_str: str) -> int:
    """将 ISO8601 格式时间戳字符串解析为毫秒时间戳。

    根据 Delta Sharing 协议规范，时间戳应为 ISO8601 格式字符串
    （如 2022-01-01T00:00:00Z），需要转换为毫秒时间戳用于内部处理。
    该函数的返回值类型（毫秒）与 Delta Sharing 协议中 timestamp 查询参数的语义保持一致。

    Args:
        timestamp_str: ISO8601 格式的时间戳字符串。

    Returns:
        毫秒为单位的 Unix 时间戳（整数）。

    Raises:
        ValueError: 如果时间戳格式无效。
    """
    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)
