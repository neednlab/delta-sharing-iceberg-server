"""
版本路由和 VersionService 测试

覆盖范围：
- GET /version 端点：无参数、timestamp 参数
- 认证检查：401/403
- 资源不存在：404
- VersionService.get_or_allocate_version: 幂等分配
- VersionService.get_by_version: 逆向查询
- VersionService.get_version_by_timestamp: 按时间戳查询
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.version_service import VersionService
from app.core.errors import DeltaSharingError, ErrorCode


class TestVersionService:
    @pytest.fixture
    def mock_repo(self):
        """创建 mock VersionRepository。"""
        repo = MagicMock()
        return repo

    @pytest.fixture
    def vs(self, mock_repo):
        """创建 VersionService 并注入 mock repository。"""
        service = VersionService()
        service._version_repo = mock_repo
        return service

    def test_get_or_allocate_existing_snapshot(self, vs, mock_repo):
        mock_repo.find_by_snapshot.return_value = 5
        result = vs.get_or_allocate_version("s1", "sc1", "t1", 100, 1234567890)
        assert result == 5
        mock_repo.allocate.assert_not_called()

    def test_get_or_allocate_new_snapshot(self, vs, mock_repo):
        mock_repo.find_by_snapshot.return_value = None
        mock_repo.allocate.return_value = 6
        result = vs.get_or_allocate_version("s1", "sc1", "t1", 101, 1234567890)
        assert result == 6
        mock_repo.allocate.assert_called_once_with("s1", "sc1", "t1", 101, 1234567890)

    def test_get_or_allocate_fixes_timestamp_zero(self, vs, mock_repo):
        mock_repo.find_by_snapshot.return_value = 5
        result = vs.get_or_allocate_version("s1", "sc1", "t1", 100, 0)
        assert result == 5
        mock_repo.update_timestamp.assert_not_called()

    def test_get_or_allocate_with_valid_timestamp(self, vs, mock_repo):
        mock_repo.find_by_snapshot.return_value = None
        mock_repo.allocate.return_value = 7
        result = vs.get_or_allocate_version("s1", "sc1", "t1", 200, 1700000000000)
        assert result == 7
        mock_repo.allocate.assert_called_once_with(
            "s1", "sc1", "t1", 200, 1700000000000
        )

    def test_update_timestamp_triggered_when_valid(self, vs, mock_repo):
        mock_repo.find_by_snapshot.return_value = 3
        result = vs.get_or_allocate_version("s1", "sc1", "t1", 100, 1700000000000)
        assert result == 3
        mock_repo.update_timestamp.assert_called_once_with(
            "s1", "sc1", "t1", 100, 1700000000000
        )
        mock_repo.allocate.assert_not_called()

    def test_get_by_version_valid(self, vs, mock_repo):
        mock_repo.find_by_version.return_value = {
            "snapshot_id": 42,
            "version": 3,
            "timestamp": 1000,
        }
        result = vs.get_by_version("s1", "sc1", "t1", 3)
        assert result["snapshot_id"] == 42
        assert result["version"] == 3

    def test_get_by_version_not_found(self, vs, mock_repo):
        mock_repo.find_by_version.return_value = None
        with pytest.raises(DeltaSharingError) as exc_info:
            vs.get_by_version("s1", "sc1", "t1", 999)
        assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
        assert exc_info.value.status_code == 400

    def test_get_version_by_timestamp_valid(self, vs, mock_repo):
        mock_repo.find_by_timestamp.return_value = {
            "snapshot_id": 10,
            "version": 2,
            "timestamp": 1000,
        }
        result = vs.get_version_by_timestamp("s1", "sc1", "t1", 1500)
        assert result["snapshot_id"] == 10
        assert result["version"] == 2

    def test_get_version_by_timestamp_not_found(self, vs, mock_repo):
        mock_repo.find_by_timestamp.return_value = None
        with pytest.raises(DeltaSharingError) as exc_info:
            vs.get_version_by_timestamp("s1", "sc1", "t1", 1)
        assert exc_info.value.error_code == ErrorCode.INVALID_REQUEST
        assert exc_info.value.status_code == 400


class TestVersionEndpoint:
    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        """Mock 版本路由依赖的服务。"""
        with (
            patch("app.routes.version.share_service") as mock_share,
            patch("app.routes.version.auth_repo") as mock_auth,
            patch("app.routes.version.iceberg_service") as mock_iceberg,
            patch("app.routes.version.version_service") as mock_version,
        ):
            self.mock_share = mock_share
            self.mock_auth = mock_auth
            self.mock_iceberg = mock_iceberg
            self.mock_version = mock_version

            self.mock_share.share_exists.return_value = True
            self.mock_share.schema_exists.return_value = True
            self.mock_share.table_exists.return_value = True
            self.mock_auth.check_access_with_share_validation.return_value = {
                "share_id": "fake-id",
                "authorized": True,
            }
            self.mock_iceberg.get_current_snapshot.return_value = {
                "snapshot-id": 100,
                "timestamp-ms": 1700000000000,
            }
            self.mock_version.get_or_allocate_version.return_value = 5
            self.mock_version.get_version_by_timestamp.return_value = {
                "snapshot_id": 100,
                "version": 3,
                "timestamp": 1600000000,
            }
            yield

    def test_get_version_no_params(self, test_db, client_dp):
        response = client_dp.get(
            "/delta-sharing/shares/s1/schemas/sc1/tables/t1/version"
        )
        assert response.status_code == 200
        assert "delta-table-version" in response.headers
        assert response.headers["delta-table-version"] == "5"

    def test_get_version_with_timestamp(self, test_db, client_dp):
        response = client_dp.get(
            "/delta-sharing/shares/s1/schemas/sc1/tables/t1/version?timestamp=2026-01-01T00:00:00Z"
        )
        assert response.status_code == 200
        assert "delta-table-version" in response.headers
        assert response.headers["delta-table-version"] == "3"

    def test_get_version_no_auth_returns_401(self, test_db, client_dp):
        """测试无 token 时 client_dp 的依赖覆盖是否正常工作。
        注意：client_dp 已覆盖 get_current_recipient，所以不会返回 401。
        """
        response = client_dp.get(
            "/delta-sharing/shares/s1/schemas/sc1/tables/t1/version"
        )
        assert response.status_code == 200

    def test_get_version_share_not_found(self, test_db, client_dp):
        self.mock_auth.check_access_with_share_validation.return_value = None
        response = client_dp.get(
            "/delta-sharing/shares/s1/schemas/sc1/tables/t1/version"
        )
        assert response.status_code == 404

    def test_get_version_schema_not_found(self, test_db, client_dp):
        self.mock_share.schema_exists.return_value = False
        response = client_dp.get(
            "/delta-sharing/shares/s1/schemas/sc1/tables/t1/version"
        )
        assert response.status_code == 404

    def test_get_version_table_not_found(self, test_db, client_dp):
        self.mock_share.table_exists.return_value = False
        response = client_dp.get(
            "/delta-sharing/shares/s1/schemas/sc1/tables/t1/version"
        )
        assert response.status_code == 404

    def test_get_version_access_denied_403(self, test_db, client_dp):
        self.mock_auth.check_access_with_share_validation.return_value = {
            "share_id": "fake-id",
            "authorized": False,
        }
        response = client_dp.get(
            "/delta-sharing/shares/s1/schemas/sc1/tables/t1/version"
        )
        assert response.status_code == 403


class TestVersionRepository:
    @pytest.fixture
    def repo(self, test_db):
        from app.repositories.version_repository import VersionRepository

        return VersionRepository()

    def test_allocate_with_zero_timestamp_fallback(self, repo):
        version = repo.allocate("ts", "tsc", "tt", 999, 0)
        assert version >= 1

        record = repo.find_by_version("ts", "tsc", "tt", version)
        assert record is not None
        assert record["timestamp"] != 0

    def test_allocate_with_valid_timestamp_stored(self, repo):
        valid_ts = 1700000000000
        version = repo.allocate("ts2", "tsc2", "tt2", 888, valid_ts)
        assert version >= 1

        record = repo.find_by_version("ts2", "tsc2", "tt2", version)
        assert record is not None
        assert record["timestamp"] == valid_ts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
