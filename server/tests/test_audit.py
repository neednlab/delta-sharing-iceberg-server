"""
AuditLogger 单元测试

覆盖范围：
- _get_log_file: category 路由
- log(): 日志条目构建与写入
- is_recorded / mark_recorded: 防双重记录
- request_id_ctx: ContextVar 隔离
- get_audit_logger: 单例模式
"""

import json
import pytest
from unittest.mock import patch, MagicMock, mock_open

from app.core.audit import (
    AuditLogger,
    request_id_ctx,
    get_audit_logger,
    _recorded_ids,
    _MAX_RECORDED_IDS,
)


@pytest.fixture(autouse=True)
def reset_state():
    """每个测试前重置全局状态。"""
    request_id_ctx.set(None)
    _recorded_ids.clear()
    from app.core.audit import _audit_logger
    import app.core.audit as audit_mod

    audit_mod._audit_logger = None
    yield
    request_id_ctx.set(None)
    _recorded_ids.clear()
    audit_mod._audit_logger = None


@pytest.fixture
def mock_config():
    """Mock 配置对象。"""
    cfg = MagicMock()
    cfg.logging.log_dir = "./log"
    cfg.logging.audit_log_level = "INFO"
    return cfg


@pytest.fixture
def audit_logger(mock_config):
    """创建 AuditLogger 实例并注入配置。"""
    with patch("app.core.audit.get_config", return_value=mock_config):
        logger = AuditLogger()
        return logger


class TestGetLogFile:
    def test_admin_category_routes_to_admin_audit(self, audit_logger):
        path = audit_logger._get_log_file("admin")
        assert "admin_audit" in str(path)
        assert "admin-audit-" in str(path.name)

    def test_data_plane_category_routes_to_client_audit(self, audit_logger):
        path = audit_logger._get_log_file("data_plane")
        assert "client_audit" in str(path)
        assert "client-audit-" in str(path.name)

    def test_unknown_category_falls_back_to_client_audit(self, audit_logger):
        path = audit_logger._get_log_file("unknown_category")
        assert "client_audit" in str(path)
        assert "client-audit-" in str(path.name)

    def test_date_in_filename(self, audit_logger):
        from datetime import datetime

        path = audit_logger._get_log_file("admin")
        expected_date = datetime.now().strftime("%Y-%m-%d")
        assert expected_date in str(path.name)


class TestAuditLoggerLog:
    def _get_written_json(self, m):
        """从 mock_open 对象中提取写入的 JSON 内容。"""
        written = m().write.call_args[0][0]
        return json.loads(written)

    def test_minimal_entry(self, audit_logger):
        m = mock_open()
        with patch("builtins.open", m):
            audit_logger.log(operation="TEST_OP")

        entry = self._get_written_json(m)
        assert entry["operation"] == "TEST_OP"
        assert "request_id" in entry
        assert "timestamp" in entry
        assert "category" in entry
        assert entry["error"] == {"code": None, "message": None}

    def test_full_entry_with_substructures(self, audit_logger):
        m = mock_open()
        with patch("builtins.open", m):
            audit_logger.log(
                operation="POST_QUERY",
                category="data_plane",
                recipient_id="rec-1",
                share="s",
                schema="sc",
                table="t",
                http_method="POST",
                http_path="/delta-sharing/query",
                http_status_code=200,
                http_duration_ms=150,
                client_ip="1.2.3.4",
                user_agent="TestClient",
                files_returned=10,
            )

        entry = self._get_written_json(m)
        assert entry["http"]["method"] == "POST"
        assert entry["http"]["path"] == "/delta-sharing/query"
        assert entry["http"]["status_code"] == 200
        assert entry["http"]["duration_ms"] == 150
        assert entry["client"]["ip"] == "1.2.3.4"
        assert entry["client"]["user_agent"] == "TestClient"
        assert entry["resource"]["recipient_id"] == "rec-1"
        assert entry["resource"]["share"] == "s"
        assert entry["resource"]["schema"] == "sc"
        assert entry["resource"]["table"] == "t"
        assert entry["response"]["files_returned"] == 10

    def test_file_paths_not_recorded_at_info_level(self, audit_logger):
        audit_logger.audit_log_level = "INFO"
        m = mock_open()
        with patch("builtins.open", m):
            audit_logger.log(
                operation="TEST",
                file_paths=["path1", "path2"],
            )

        entry = self._get_written_json(m)
        assert "response" not in entry or "file_paths" not in entry.get("response", {})

    def test_file_paths_recorded_at_debug_level(self, audit_logger):
        audit_logger.audit_log_level = "DEBUG"
        m = mock_open()
        with patch("builtins.open", m):
            audit_logger.log(
                operation="TEST",
                file_paths=["path1", "path2"],
            )

        entry = self._get_written_json(m)
        assert entry["response"]["file_paths"] == ["path1", "path2"]

    def test_error_substructure_always_exists(self, audit_logger):
        m = mock_open()
        with patch("builtins.open", m):
            audit_logger.log(operation="TEST_OP")

        entry = self._get_written_json(m)
        assert "error" in entry
        assert entry["error"]["code"] is None
        assert entry["error"]["message"] is None


class TestIsRecordedAndMarkRecorded:
    def test_not_recorded_initially(self, audit_logger):
        request_id_ctx.set("rid-1")
        assert audit_logger.is_recorded() is False

    def test_marked_after_log(self, audit_logger):
        request_id_ctx.set("rid-2")
        m = mock_open()
        with patch("builtins.open", m):
            audit_logger.log(operation="TEST")
        assert audit_logger.is_recorded() is True

    def test_mark_recorded_then_is_recorded(self, audit_logger):
        request_id_ctx.set("rid-3")
        audit_logger.mark_recorded()
        assert audit_logger.is_recorded() is True

    def test_set_overflow_cleanup(self, audit_logger):
        for i in range(_MAX_RECORDED_IDS + 1):
            request_id_ctx.set(f"rid-{i}")
            audit_logger.mark_recorded()
        assert len(_recorded_ids) <= _MAX_RECORDED_IDS


class TestRequestIdCtx:
    def test_set_and_get_consistent(self):
        request_id_ctx.set("my-id")
        assert request_id_ctx.get() == "my-id"
        assert request_id_ctx.get() == "my-id"

    def test_not_set_generates_uuid(self, mock_config):
        request_id_ctx.set(None)
        with patch("app.core.audit.get_config", return_value=mock_config):
            logger = AuditLogger()
            rid = logger.get_request_id()
            assert rid is not None
            assert len(rid) == 36
            assert request_id_ctx.get() == rid


class TestGetAuditLoggerSingleton:
    def test_multiple_calls_return_same_instance(self, mock_config):
        with patch("app.core.audit.get_config", return_value=mock_config):
            from app.core.audit import _audit_logger
            import app.core.audit as audit_mod

            audit_mod._audit_logger = None
            logger1 = get_audit_logger()
            logger2 = get_audit_logger()
            assert logger1 is logger2

    def test_singleton_after_reset(self, mock_config):
        with patch("app.core.audit.get_config", return_value=mock_config):
            import app.core.audit as audit_mod

            audit_mod._audit_logger = None
            logger1 = get_audit_logger()
            audit_mod._audit_logger = None
            logger2 = get_audit_logger()
            assert logger1 is not logger2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
