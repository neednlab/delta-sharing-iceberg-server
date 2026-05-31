"""
Schema Asset 和 DLC 表同步功能测试模块

该模块测试 Schema 资产添加和 DLC 表同步功能：
- Schema 资产添加到 Share
- DLC DescribeTables API 集成
- 批量 Table 插入和去重
- DLC 表同步 API（全量和增量模式）
- 错误处理（DLC 未配置、API 错误等）

测试覆盖场景：
- 1. Schema 添加到 Share（无 DLC 同步）
- 2. Schema 添加到 Share（带 DLC 同步，自动同步 Table）
- 3. 重复添加已存在的 Schema
- 4. DLC 表同步（全量替换模式）
- 5. DLC 表同步（增量追加模式）
- 6. DLC 未配置错误处理
- 7. DLC API 错误处理
- 8. 批量插入时跳过已存在的 Table
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import create_admin_app
from app.core.dlc_client import DLCAPIError
from app.repositories.share_repository import ShareRepository


ADMIN_BASE = "/delta-sharing/admin/v1"


@pytest.fixture(scope="function")
def client(test_db):
    """创建 Admin API TestClient。"""
    app = create_admin_app()
    return TestClient(app)


@pytest.fixture(scope="function")
def repo(test_db):
    """ShareRepository 实例。"""
    return ShareRepository()


@pytest.fixture(scope="function")
def share(repo):
    """创建测试 Share。"""
    return repo.create_share("test_share", "Test Share")


@pytest.fixture(scope="function")
def mock_dlc_client_with_tables():
    """Mock DLC 客户端，返回表列表。"""
    mock = MagicMock()
    mock.describe_tables.return_value = {
        "table_list": [
            {"name": "table1", "location": "cos://bucket/db1/table1"},
            {"name": "table2", "location": "cos://bucket/db1/table2"},
            {"name": "table3", "location": "cos://bucket/db1/table3"},
        ],
        "total_count": 3,
        "raw_response": "{}",
    }
    return mock


@pytest.fixture(scope="function")
def mock_dlc_client_empty():
    """Mock DLC 客户端，返回空表列表。"""
    mock = MagicMock()
    mock.describe_tables.return_value = {
        "table_list": [],
        "total_count": 0,
        "raw_response": "{}",
    }
    return mock


class TestSchemaAssetAddition:
    """测试 Schema 资产添加功能。"""

    def test_add_schema_without_dlc_sync(self, client, share):
        """添加 Schema 资产时不带 DLC 同步。"""
        response = client.post(
            f"{ADMIN_BASE}/shares/test_share/objects",
            json={"schema_name": "test_schema", "metastore_db": ""},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "schema"
        assert data["data"]["schema_name"] == "test_schema"
        assert data["tables_synced"] == 0
        assert data["tables_skipped"] == 0

    def test_add_schema_not_found_share(self, client):
        """向不存在的 Share 添加 Schema 时返回 404。"""
        response = client.post(
            f"{ADMIN_BASE}/shares/nonexistent_share/objects",
            json={"schema_name": "test_schema"},
        )
        assert response.status_code == 404
        data = response.json()
        assert data["errorCode"] == "SHARE_NOT_FOUND"

    def test_add_schema_already_exists(self, client, share):
        """添加已存在的 Schema 时返回 409。"""
        client.post(
            f"{ADMIN_BASE}/shares/test_share/objects",
            json={"schema_name": "existing_schema"},
        )

        response = client.post(
            f"{ADMIN_BASE}/shares/test_share/objects",
            json={"schema_name": "existing_schema"},
        )
        assert response.status_code == 409
        data = response.json()
        assert data["errorCode"] == "SCHEMA_ALREADY_EXISTS"


class TestSchemaAssetWithDLCSync:
    """测试带 DLC 同步的 Schema 资产添加功能。"""

    def test_add_schema_with_dlc_sync(self, client, share, mock_dlc_client_with_tables):
        """添加 Schema 资产并从 DLC 同步 Table。"""
        with patch(
            "app.api.admin.share_management.get_dlc_client",
            return_value=mock_dlc_client_with_tables,
        ):
            response = client.post(
                f"{ADMIN_BASE}/shares/test_share/objects",
                json={"schema_name": "dlc_schema", "metastore_db": "dlc_database"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "schema"
        assert data["data"]["schema_name"] == "dlc_schema"
        assert data["tables_synced"] == 3
        assert data["tables_skipped"] == 0

    def test_add_schema_with_dlc_sync_empty_tables(self, client, share, mock_dlc_client_empty):
        """添加 Schema 资产但 DLC 返回空表列表。"""
        with patch(
            "app.api.admin.share_management.get_dlc_client",
            return_value=mock_dlc_client_empty,
        ):
            response = client.post(
                f"{ADMIN_BASE}/shares/test_share/objects",
                json={"schema_name": "empty_schema", "metastore_db": "empty_database"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "schema"
        assert data["tables_synced"] == 0

    def test_add_schema_dlc_not_configured(self, client, share):
        """DLC 未配置时添加 Schema 资产返回 500。"""
        with patch("app.api.admin.share_management.get_dlc_client", return_value=None):
            response = client.post(
                f"{ADMIN_BASE}/shares/test_share/objects",
                json={"schema_name": "test_schema", "metastore_db": "dlc_db"},
            )

        assert response.status_code == 500
        data = response.json()
        assert data["errorCode"] == "DLC_NOT_CONFIGURED"

    def test_add_schema_dlc_api_error(self, client, share):
        """DLC API 调用失败时返回 500。"""
        mock_client = MagicMock()
        mock_client.describe_tables.side_effect = DLCAPIError("API Error", code="INTERNAL_ERROR")

        with patch("app.api.admin.share_management.get_dlc_client", return_value=mock_client):
            response = client.post(
                f"{ADMIN_BASE}/shares/test_share/objects",
                json={"schema_name": "test_schema", "metastore_db": "dlc_db"},
            )

        assert response.status_code == 500
        data = response.json()
        assert data["errorCode"] == "DLC_API_ERROR"

    def test_add_schema_duplicate_tables_skipped(
        self, client, share, repo, mock_dlc_client_with_tables
    ):
        """批量插入时跳过已存在的 Table。

        当 Schema 已存在时，先通过 API 添加 Schema（会失败），然后用 repo 直接创建，
        再测试批量插入时跳过已存在的 Table。
        """
        repo.create_schema("test_share", "dlc_schema2", "dlc_database")
        # 通过 create_tables_batch 预创建 table1，确保 linked_schema_id 正确关联
        repo.create_tables_batch(
            "test_share",
            "dlc_schema2",
            [
                {
                    "name": "table1",
                    "location": "cos://bucket/table1",
                    "metastore_db": "dlc_database",
                    "metastore_table": "table1",
                }
            ],
        )

        tables = [
            {
                "name": "table1",
                "location": "cos://bucket/table1",
                "metastore_db": "dlc_database",
            },
            {
                "name": "table2",
                "location": "cos://bucket/table2",
                "metastore_db": "dlc_database",
            },
            {
                "name": "table3",
                "location": "cos://bucket/table3",
                "metastore_db": "dlc_database",
            },
        ]

        result = repo.create_tables_batch("test_share", "dlc_schema2", tables)

        assert result["inserted_count"] == 2
        assert result["skipped_count"] == 1


class TestDLCSyncAPI:
    """测试 DLC 表同步 API。"""

    def test_sync_tables_append_mode(self, client, share, repo, mock_dlc_client_with_tables):
        """测试增量追加模式同步 Table。"""
        repo.create_schema("test_share", "sync_schema", "sync_database")

        with patch(
            "app.api.admin.sync.get_dlc_client",
            return_value=mock_dlc_client_with_tables,
        ):
            response = client.post(
                f"{ADMIN_BASE}/sync/tables",
                json={
                    "share_name": "test_share",
                    "schema_name": "sync_schema",
                    "mode": "append",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "append"
        assert data["total_count"] == 3
        assert data["synced_count"] == 3
        assert data["skipped_count"] == 0
        assert data["deleted_count"] == 0

    def test_sync_tables_full_mode(self, client, share, repo, mock_dlc_client_with_tables):
        """测试全量替换模式同步 Table。"""
        repo.create_schema("test_share", "full_sync_schema", "full_sync_database")
        # 通过 create_tables_batch 预创建 old_table，确保 linked_schema_id 正确关联
        repo.create_tables_batch(
            "test_share",
            "full_sync_schema",
            [
                {
                    "name": "old_table",
                    "location": "cos://bucket/old_table",
                    "metastore_db": "full_sync_database",
                    "metastore_table": "old_table",
                }
            ],
        )

        with patch(
            "app.api.admin.sync.get_dlc_client",
            return_value=mock_dlc_client_with_tables,
        ):
            response = client.post(
                f"{ADMIN_BASE}/sync/tables",
                json={
                    "share_name": "test_share",
                    "schema_name": "full_sync_schema",
                    "mode": "full",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "full"
        assert data["deleted_count"] == 1
        assert data["synced_count"] == 3

    def test_sync_tables_share_not_found(self, client):
        """同步不存在的 Share 时返回 404。"""
        response = client.post(
            f"{ADMIN_BASE}/sync/tables",
            json={
                "share_name": "nonexistent",
                "schema_name": "schema",
                "mode": "append",
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["errorCode"] == "SHARE_NOT_FOUND"

    def test_sync_tables_schema_not_found(self, client, share):
        """同步不存在的 Schema 时返回 404。"""
        response = client.post(
            f"{ADMIN_BASE}/sync/tables",
            json={
                "share_name": "test_share",
                "schema_name": "nonexistent",
                "mode": "append",
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["errorCode"] == "SCHEMA_NOT_FOUND"

    def test_sync_tables_no_dlc_database(self, client, share, repo):
        """未指定 DLC Database 且 Schema 无 metastore_db 时返回 400。"""
        repo.create_schema("test_share", "no_dlc_schema", "")

        response = client.post(
            f"{ADMIN_BASE}/sync/tables",
            json={
                "share_name": "test_share",
                "schema_name": "no_dlc_schema",
                "mode": "append",
            },
        )

        assert response.status_code == 400


class TestBatchTableOperations:
    """测试批量 Table 操作。"""

    def test_create_tables_batch(self, repo, share):
        """测试批量创建 Table。"""
        repo.create_schema("test_share", "batch_schema", "batch_db")

        tables = [
            {
                "name": "batch_table1",
                "location": "cos://bucket/batch_table1",
                "metastore_db": "batch_db",
            },
            {
                "name": "batch_table2",
                "location": "cos://bucket/batch_table2",
                "metastore_db": "batch_db",
            },
            {
                "name": "batch_table3",
                "location": "cos://bucket/batch_table3",
                "metastore_db": "batch_db",
            },
        ]

        result = repo.create_tables_batch("test_share", "batch_schema", tables)

        assert result["inserted_count"] == 3
        assert result["skipped_count"] == 0

    def test_create_tables_batch_with_duplicates(self, repo, share):
        """测试批量创建 Table 时跳过重复项。"""
        repo.create_schema("test_share", "dup_schema", "dup_db")
        # 通过 create_tables_batch 预创建 existing_table，确保 linked_schema_id 正确关联
        repo.create_tables_batch(
            "test_share",
            "dup_schema",
            [
                {
                    "name": "existing_table",
                    "location": "cos://bucket/existing_table",
                    "metastore_db": "dup_db",
                    "metastore_table": "existing_table",
                }
            ],
        )

        tables = [
            {
                "name": "existing_table",
                "location": "cos://bucket/existing_table",
                "metastore_db": "dup_db",
            },
            {
                "name": "new_table1",
                "location": "cos://bucket/new_table1",
                "metastore_db": "dup_db",
            },
            {
                "name": "new_table2",
                "location": "cos://bucket/new_table2",
                "metastore_db": "dup_db",
            },
        ]

        result = repo.create_tables_batch("test_share", "dup_schema", tables)

        assert result["inserted_count"] == 2
        assert result["skipped_count"] == 1

    def test_delete_schema_tables(self, repo, share):
        """测试删除 Schema 下的所有 Table。"""
        repo.create_schema("test_share", "delete_schema", "delete_db")
        # 通过 create_tables_batch 创建 tables，确保 linked_schema_id 正确关联
        repo.create_tables_batch(
            "test_share",
            "delete_schema",
            [
                {
                    "name": "table1",
                    "location": "cos://bucket/table1",
                    "metastore_db": "delete_db",
                    "metastore_table": "table1",
                },
                {
                    "name": "table2",
                    "location": "cos://bucket/table2",
                    "metastore_db": "delete_db",
                    "metastore_table": "table2",
                },
            ],
        )

        deleted_count = repo.delete_schema_tables("test_share", "delete_schema")

        assert deleted_count == 2

        tables = repo.get_schema_tables_from_db("test_share", "delete_schema")
        assert len(tables) == 0


class TestDLCErrorCodes:
    """测试 DLC 错误码。"""

    def test_dlc_not_configured_error_code(self):
        """验证 DLC_NOT_CONFIGURED 错误码存在。"""
        from app.core.errors import ErrorCode

        assert hasattr(ErrorCode, "DLC_NOT_CONFIGURED")
        assert ErrorCode.DLC_NOT_CONFIGURED.value == "DLC_NOT_CONFIGURED"

    def test_dlc_api_error_code(self):
        """验证 DLC_API_ERROR 错误码存在。"""
        from app.core.errors import ErrorCode

        assert hasattr(ErrorCode, "DLC_API_ERROR")
        assert ErrorCode.DLC_API_ERROR.value == "DLC_API_ERROR"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
