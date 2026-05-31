"""
audit_utils 模块单元测试

覆盖范围：
- raise_audited_error(): kwargs 透传至 audit_logger.log()
- raise_audited_error(): HTTPException 抛出逻辑
- raise_audited_error(): request=None 时的容错处理
- QueryAuditContext: to_audit_dict() 过滤 None 值

重点验证 Bug 修复：确保 recipient_name、share_name、token_hash 等 admin API
传入的额外 kwargs 能正确透传至 AuditLogger.log()，避免
"got an unexpected keyword argument" 异常。
"""

import pytest
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.core.errors import DeltaSharingError, ErrorCode
from app.utils.audit_utils import raise_audited_error, QueryAuditContext


class TestRaiseAuditedErrorKwargsPassthrough:
    """验证 raise_audited_error 的 **kwargs 透传机制。

    Bug 背景：admin API (shares.py/recipients.py/tokens.py) 传入了
    recipient_name、share_name、token_hash 等 kwargs，但 AuditLogger.log()
    方法签名中缺少这些参数，导致运行时抛出 TypeError。
    """

    def _make_audit_logger_mock(self):
        """创建 audit_logger Mock，其 log() 方法接受任意 kwargs。"""
        mock = MagicMock()
        mock.log = MagicMock()
        return mock

    def test_recipient_name_kwarg_passed_through(self):
        """验证 recipient_name=xxx 能透传至 audit_logger.log()。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(
            ErrorCode.RECIPIENT_NOT_FOUND, "Recipient not found", status_code=404
        )

        with pytest.raises(HTTPException):
            raise_audited_error(
                audit_logger,
                error,
                "ADMIN_GET_RECIPIENT",
                category="admin",
                recipient_name="test-recipient",
            )

        call_kwargs = audit_logger.log.call_args.kwargs
        assert call_kwargs["recipient_name"] == "test-recipient"

    def test_share_name_kwarg_passed_through(self):
        """验证 share_name=xxx 能透传至 audit_logger.log()。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(
            ErrorCode.SHARE_NOT_FOUND, "Share not found", status_code=404
        )

        with pytest.raises(HTTPException):
            raise_audited_error(
                audit_logger,
                error,
                "ADMIN_GRANT_SHARE",
                category="admin",
                recipient_name="rec",
                share_name="my_share",
            )

        call_kwargs = audit_logger.log.call_args.kwargs
        assert call_kwargs["recipient_name"] == "rec"
        assert call_kwargs["share_name"] == "my_share"

    def test_token_hash_kwarg_passed_through(self):
        """验证 token_hash=xxx 能透传至 audit_logger.log()。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(
            ErrorCode.INVALID_TOKEN, "Token not found", status_code=404
        )

        with pytest.raises(HTTPException):
            raise_audited_error(
                audit_logger,
                error,
                "ADMIN_REVOKE_TOKEN",
                category="admin",
                recipient_name="rec",
                token_hash="abc123def456",
            )

        call_kwargs = audit_logger.log.call_args.kwargs
        assert call_kwargs["recipient_name"] == "rec"
        assert call_kwargs["token_hash"] == "abc123def456"

    def test_mixed_admin_kwargs_passed_through(self):
        """验证 shares.py 的典型调用模式：同时传入 recipient_name + share_name。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(
            ErrorCode.AUTHORIZATION_ALREADY_EXISTS, "Already exists", status_code=409
        )

        with pytest.raises(HTTPException):
            raise_audited_error(
                audit_logger,
                error,
                "ADMIN_GRANT_SHARE",
                request=None,
                category="admin",
                recipient_name="cnslk_recipient",
                share_name="cnslk_share",
                granted_by="admin",
            )

        call_kwargs = audit_logger.log.call_args.kwargs
        assert call_kwargs["recipient_name"] == "cnslk_recipient"
        assert call_kwargs["share_name"] == "cnslk_share"


class TestRaiseAuditedErrorHttpException:
    """验证 raise_audited_error 的 HTTPException 抛出逻辑。"""

    def _make_audit_logger_mock(self):
        mock = MagicMock()
        mock.log = MagicMock()
        return mock

    def test_raises_http_exception_with_status_code(self):
        """验证抛出的 HTTPException 状态码与 error 一致。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(
            ErrorCode.INTERNAL_ERROR, "Server error", status_code=500
        )

        with pytest.raises(HTTPException) as exc_info:
            raise_audited_error(audit_logger, error, "TEST_OP")

        assert exc_info.value.status_code == 500

    def test_raises_http_exception_with_error_detail(self):
        """验证抛出的 HTTPException detail 包含 error_code 和 message。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(
            ErrorCode.SHARE_NOT_FOUND, "Share 'x' not found", status_code=404
        )

        with pytest.raises(HTTPException) as exc_info:
            raise_audited_error(audit_logger, error, "TEST_OP")

        detail = exc_info.value.detail
        assert detail["errorCode"] == "SHARE_NOT_FOUND"
        assert detail["message"] == "Share 'x' not found"

    def test_audit_logger_called_with_error_info(self):
        """验证 audit_logger.log() 收到正确的 error_code 和 error_message。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(
            ErrorCode.COS_ACCESS_ERROR, "COS failed", status_code=503
        )

        with pytest.raises(HTTPException):
            raise_audited_error(audit_logger, error, "TEST_OP")

        call_kwargs = audit_logger.log.call_args.kwargs
        assert call_kwargs["error_code"] == "COS_ACCESS_ERROR"
        assert call_kwargs["error_message"] == "COS failed"

    def test_audit_logger_called_with_operation(self):
        """验证 audit_logger.log() 收到正确的 operation 参数。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(ErrorCode.INTERNAL_ERROR, "err", status_code=500)

        with pytest.raises(HTTPException):
            raise_audited_error(audit_logger, error, "ADMIN_CREATE_RECIPIENT")

        call_kwargs = audit_logger.log.call_args.kwargs
        assert call_kwargs["operation"] == "ADMIN_CREATE_RECIPIENT"

    def test_default_category_is_data_plane(self):
        """验证不传 category 时默认为 data_plane。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(ErrorCode.INTERNAL_ERROR, "err", status_code=500)

        with pytest.raises(HTTPException):
            raise_audited_error(audit_logger, error, "TEST_OP")

        call_kwargs = audit_logger.log.call_args.kwargs
        assert call_kwargs["category"] == "data_plane"

    def test_category_is_admin_when_specified(self):
        """验证显式传入 category='admin' 时生效。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(ErrorCode.INTERNAL_ERROR, "err", status_code=500)

        with pytest.raises(HTTPException):
            raise_audited_error(audit_logger, error, "TEST_OP", category="admin")

        call_kwargs = audit_logger.log.call_args.kwargs
        assert call_kwargs["category"] == "admin"


class TestRaiseAuditedErrorRequestNone:
    """验证 request=None 时的容错处理。"""

    def _make_audit_logger_mock(self):
        mock = MagicMock()
        mock.log = MagicMock()
        return mock

    def test_request_none_does_not_crash(self):
        """验证 request=None 不会导致 AttributeError。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(ErrorCode.INTERNAL_ERROR, "err", status_code=500)

        with pytest.raises(HTTPException):
            raise_audited_error(audit_logger, error, "TEST_OP", request=None)

        call_kwargs = audit_logger.log.call_args.kwargs
        assert call_kwargs["client_ip"] is None
        assert call_kwargs["user_agent"] is None

    def test_request_none_with_extra_kwargs(self):
        """验证 request=None + 额外 kwargs 的组合场景。"""
        audit_logger = self._make_audit_logger_mock()
        error = DeltaSharingError(
            ErrorCode.RECIPIENT_NOT_FOUND, "Not found", status_code=404
        )

        with pytest.raises(HTTPException):
            raise_audited_error(
                audit_logger,
                error,
                "ADMIN_DELETE_RECIPIENT",
                request=None,
                category="admin",
                recipient_name="to-delete",
            )

        call_kwargs = audit_logger.log.call_args.kwargs
        assert call_kwargs["recipient_name"] == "to-delete"
        assert call_kwargs["client_ip"] is None
        assert call_kwargs["user_agent"] is None


class TestQueryAuditContext:
    """验证 QueryAuditContext 数据类的 to_audit_dict() 方法。"""

    def test_all_fields_included(self):
        """验证所有非 None 字段都包含在返回字典中。"""
        ctx = QueryAuditContext(
            share="s1",
            schema="sc1",
            table="t1",
            delta_table_version=5,
            iceberg_snapshot_id=100,
            files_returned=3,
            recipient_id="rec-1",
            query_version=2,
            query_timestamp="2022-01-01T00:00:00Z",
        )
        result = ctx.to_audit_dict()
        assert result["share"] == "s1"
        assert result["schema"] == "sc1"
        assert result["table"] == "t1"
        assert result["delta_table_version"] == 5
        assert result["iceberg_snapshot_id"] == 100
        assert result["files_returned"] == 3
        assert result["recipient_id"] == "rec-1"
        assert result["query_version"] == 2
        assert result["query_timestamp"] == "2022-01-01T00:00:00Z"

    def test_none_fields_excluded(self):
        """验证 None 值的可选字段不会出现在返回字典中。"""
        ctx = QueryAuditContext(
            share="s1",
            schema="sc1",
            table="t1",
            delta_table_version=0,
            iceberg_snapshot_id=0,
            files_returned=0,
            recipient_id="rec-1",
        )
        result = ctx.to_audit_dict()
        assert "query_version" not in result
        assert "query_timestamp" not in result
        assert "query_starting_version" not in result
        assert "query_ending_version" not in result
        assert "file_paths" not in result

    def test_file_paths_included_when_set(self):
        """验证 file_paths 有值时包含在返回字典中。"""
        ctx = QueryAuditContext(
            share="s1",
            schema="sc1",
            table="t1",
            delta_table_version=0,
            iceberg_snapshot_id=0,
            files_returned=2,
            recipient_id="rec-1",
            file_paths=["/path/1.parquet", "/path/2.parquet"],
        )
        result = ctx.to_audit_dict()
        assert result["file_paths"] == ["/path/1.parquet", "/path/2.parquet"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
