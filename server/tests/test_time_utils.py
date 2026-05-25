"""
时间工具模块单元测试

测试 app.utils.time_utils 中的 now_ts()、ts_to_datetime()、
parse_iso8601_timestamp() 三个公开函数。
"""

import pytest
from datetime import datetime, timezone

from app.utils.time_utils import now_ts, ts_to_datetime, parse_iso8601_timestamp


class TestNowTs:
    """now_ts() 函数的单元测试。"""

    def test_now_ts_returns_int(self):
        """验证 now_ts() 返回值为整数类型。"""
        result = now_ts()
        assert isinstance(result, int)

    def test_now_ts_consistency(self):
        """验证 now_ts() 连续调用返回的时间戳在合理误差范围内（2秒以内）。"""
        ts1 = now_ts()
        ts2 = now_ts()
        assert ts1 > 0
        assert abs(ts2 - ts1) <= 2


class TestTsToDatetime:
    """ts_to_datetime() 函数的单元测试。"""

    def test_ts_to_datetime_utc_timezone(self):
        """验证 ts_to_datetime() 返回的 datetime 对象带 UTC 时区。"""
        ts = 1700000000
        dt = ts_to_datetime(ts)
        assert dt.tzinfo is not None
        assert dt.tzinfo.utcoffset(dt).total_seconds() == 0

    def test_ts_to_datetime_roundtrip(self):
        """验证 ts_to_datetime() 与 dt.timestamp() 的往返一致性。

        给定一个已知时间戳，转换为 datetime 后再转回时间戳时结果应一致。
        """
        ts = 1700000000
        dt = ts_to_datetime(ts)
        roundtrip_ts = int(dt.timestamp())
        assert roundtrip_ts == ts


class TestParseIso8601Timestamp:
    """parse_iso8601_timestamp() 函数的单元测试。"""

    def test_parse_iso8601_z_suffix(self):
        """验证解析带 Z 后缀的 ISO8601 时间戳字符串。"""
        result = parse_iso8601_timestamp("2022-01-01T00:00:00Z")
        expected_dt = datetime(2022, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        expected_ms = int(expected_dt.timestamp() * 1000)
        assert result == expected_ms

    def test_parse_iso8601_with_timezone_offset(self):
        """验证解析带时区偏移的 ISO8601 时间戳字符串。"""
        result = parse_iso8601_timestamp("2022-01-01T00:00:00+08:00")
        expected_dt = datetime(2022, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        expected_ms = int((expected_dt.timestamp() - 8 * 3600) * 1000)
        assert result == expected_ms

    def test_parse_iso8601_invalid_input_raises_value_error(self):
        """验证解析非法时间戳字符串时抛出 ValueError 异常。"""
        with pytest.raises(ValueError):
            parse_iso8601_timestamp("not-a-valid-timestamp")

        with pytest.raises(ValueError):
            parse_iso8601_timestamp("")

        with pytest.raises(ValueError):
            parse_iso8601_timestamp("2022-13-01T00:00:00Z")
