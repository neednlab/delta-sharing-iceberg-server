"""
数据库查询效率测试模块（白盒 SQL 计数测试）

该模块通过 SQLAlchemy before_cursor_execute 事件监听器，
结合 FastAPI TestClient 和 Mock COS/DLC 客户端，
精确统计每个 Data Plane 路由请求触发的 SQL 语句数量。

测试不依赖网络连接（COS/DLC 通过 Mock 替代），
仅统计数据库层 SQL 执行次数。

测试模式：
- baseline: 记录优化前的 SQL 查询次数（预期 5~6 条）
  在 Phase 4 优化完成后，测试断言将更新为优化后预期（≤4 条）
"""

import uuid
from typing import List
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from main import create_data_plane_app
from app.core.database import (
    init_database,
    shares,
    shared_schemas,
    shared_tables,
    recipients,
    recipient_shares,
    bearer_tokens,
    get_database,
)
from app.core.config import load_config
from app.utils.time_utils import now_ts


class SqlQueryCollector:
    """SQL 查询收集器（通过 SQLAlchemy event 监听）。

    在测试期间挂载到 SQLAlchemy Engine，收集所有 SQL 语句列表。
    支持 attach/detach 控制监听开关，避免跨测试污染。
    """

    def __init__(self):
        self.queries: List[str] = []
        self._attached = False

    def _on_before_cursor_execute(self, conn, cursor, statement, parameters, context, executemany):
        self.queries.append(str(statement).strip())

    def attach(self):
        """挂载事件监听器到当前引擎。"""
        if not self._attached:
            engine = get_database().get_engine()
            event.listen(engine, "before_cursor_execute", self._on_before_cursor_execute)
            self._attached = True

    def detach(self):
        """卸载事件监听器。"""
        if self._attached:
            engine = get_database().get_engine()
            event.remove(engine, "before_cursor_execute", self._on_before_cursor_execute)
            self._attached = False

    def reset(self):
        """重置查询记录列表。"""
        self.queries = []


@pytest.fixture(scope="function")
def sql_collector():
    """全局 SQL 查询收集器 fixture。

    在整个测试函数生命周期内挂载监听器。
    """
    collector = SqlQueryCollector()
    collector.attach()
    yield collector
    collector.detach()


@pytest.fixture(scope="function")
def seeded_db(monkeypatch):
    """初始化测试数据库并预置种子数据。

    插入以下种子数据：
    - share: test_share
    - schema: test_schema (链接到 test_share)
    - table: test_table (链接到 test_share + test_schema)
    - recipient: test-recipient-id
    - bearer_token: 用于认证验证
    - authorization: recipient 对 share 的授权

    通过 monkeypatch 将 config.shares.use_database 设置为 True，
    确保 check_share_access 走数据库路径。
    """
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db_path = f.name

    load_config("./config.yaml")
    db = init_database(f"sqlite:///{test_db_path}")
    engine = db.get_engine()

    share_id = str(uuid.uuid4())
    schema_id = str(uuid.uuid4())
    table_id = str(uuid.uuid4())
    ts = now_ts()
    token_hash = "sha256_test_token_hash_for_recipient"
    token_prefix = "test_token_prefix"

    with engine.begin() as conn:
        conn.execute(
            shares.insert().values(
                share_id=share_id,
                share_name="test_share",
                created_at=ts,
                updated_at=ts,
            )
        )
        conn.execute(
            shared_schemas.insert().values(
                schema_id=schema_id,
                share_id=share_id,
                schema_name="test_schema",
                created_at=ts,
                updated_at=ts,
            )
        )
        conn.execute(
            shared_tables.insert().values(
                table_id=table_id,
                share_id=share_id,
                linked_schema_id=schema_id,
                table_name="test_table",
                location="cosn://bucket/test_table",
                created_at=ts,
                updated_at=ts,
            )
        )
        conn.execute(
            recipients.insert().values(
                recipient_id="test-recipient-id",
                recipient_name="test_recipient",
                created_at=ts,
                updated_at=ts,
                is_active=1,
            )
        )
        conn.execute(
            recipient_shares.insert().values(
                id=str(uuid.uuid4()),
                recipient_id="test-recipient-id",
                share_id=share_id,
                granted_at=ts,
            )
        )
        conn.execute(
            bearer_tokens.insert().values(
                token_hash=token_hash,
                token_prefix=token_prefix,
                recipient_id="test-recipient-id",
                created_at=ts,
                is_revoked=0,
            )
        )

    monkeypatch.setattr(
        "app.services.authorization_service.AuthorizationService._is_database_authorization_enabled",
        lambda self: True,
    )

    yield db

    db.close()
    if os.path.exists(test_db_path):
        os.unlink(test_db_path)


@pytest.fixture(scope="function")
def client_dp_seeded(seeded_db, sql_collector):
    """创建 Data Plane TestClient（种子数据 + SQL 监听）。

    覆盖 get_current_recipient 返回 "test-recipient-id"。
    SQL 查询通过 sql_collector fixture 自动收集。
    """
    app = create_data_plane_app()

    async def _mock_get_current_recipient():
        return "test-recipient-id"

    from app.core.authentication import get_current_recipient

    app.dependency_overrides[get_current_recipient] = _mock_get_current_recipient

    return TestClient(app)


# ====================================================================
# Baseline 测试用例（优化前）
# ====================================================================


class TestListSharesBaseline:
    """测试 GET /shares 路由的 SQL 查询次数基线。"""

    def test_list_shares_route_sql_count_baseline(self, client_dp_seeded, sql_collector):
        """GET /delta-sharing/shares → 记录优化前 SQL 条数。"""
        sql_collector.reset()

        response = client_dp_seeded.get("/delta-sharing/shares")
        assert response.status_code == 200

        sql_count = len(sql_collector.queries)
        print(f"\n[SQL COUNT] list_shares: {sql_count} queries")
        for i, q in enumerate(sql_collector.queries):
            print(f"  [{i + 1}] {q[:120]}...")

        assert sql_count <= 4, f"Expected ≤4 SQL queries for list_shares, got {sql_count}"


class TestListSchemasBaseline:
    """测试 GET /shares/{s}/schemas 路由的 SQL 查询次数基线。"""

    def test_list_schemas_route_sql_count_baseline(self, client_dp_seeded, sql_collector):
        """GET /delta-sharing/shares/{s}/schemas → 记录优化前 SQL 条数。"""
        sql_collector.reset()

        response = client_dp_seeded.get("/delta-sharing/shares/test_share/schemas")
        assert response.status_code == 200

        sql_count = len(sql_collector.queries)
        print(f"\n[SQL COUNT] list_schemas: {sql_count} queries")
        for i, q in enumerate(sql_collector.queries):
            print(f"  [{i + 1}] {q[:120]}...")

        assert sql_count <= 4, f"Expected ≤4 SQL queries for list_schemas, got {sql_count}"


class TestListTablesBaseline:
    """测试 GET /shares/{s}/schemas/{s}/tables 路由的 SQL 查询次数基线。"""

    def test_list_tables_route_sql_count_baseline(self, client_dp_seeded, sql_collector):
        """GET /delta-sharing/shares/{s}/schemas/{s}/tables → 记录优化前 SQL 条数。"""
        sql_collector.reset()

        response = client_dp_seeded.get(
            "/delta-sharing/shares/test_share/schemas/test_schema/tables"
        )
        assert response.status_code == 200

        sql_count = len(sql_collector.queries)
        print(f"\n[SQL COUNT] list_tables: {sql_count} queries")
        for i, q in enumerate(sql_collector.queries):
            print(f"  [{i + 1}] {q[:120]}...")

        assert sql_count <= 6, f"Expected ≤6 SQL queries for list_tables, got {sql_count}"


class TestMetadataBaseline:
    """测试 GET /shares/{s}/schemas/{s}/tables/{t}/metadata 路由的 SQL 查询次数基线。"""

    def test_metadata_route_sql_count_baseline(self, client_dp_seeded, sql_collector):
        """GET .../metadata → 记录 SQL 条数（Mock iceberg/version service）。

        优化后预期：总 SQL ≤ 3（含 token 认证），前置验证（不含 token）≤ 2。
        get_table_config() 单次调用替代 schema_exists() + table_exists() 两次查询。
        """
        mock_iceberg = MagicMock()
        mock_iceberg.get_current_snapshot.return_value = {
            "snapshot-id": "snap-001",
            "timestamp-ms": 1000,
        }
        mock_iceberg.get_table_metadata.return_value = {
            "id": "table-uuid",
            "schema_string": "{}",
            "partition_columns": [],
        }
        mock_version = MagicMock()
        mock_version.get_or_allocate_version.return_value = 1

        sql_collector.reset()

        with (
            patch("app.routes.metadata.iceberg_service", mock_iceberg),
            patch("app.routes.metadata.version_service", mock_version),
        ):
            response = client_dp_seeded.get(
                "/delta-sharing/shares/test_share/schemas/test_schema/tables/test_table/metadata"
            )

        sql_count = len(sql_collector.queries)
        pre_validation_queries = [
            q for q in sql_collector.queries if "bearer_tokens" not in q.lower()
        ]
        pre_validation_count = len(pre_validation_queries)

        print(
            f"\n[SQL COUNT] metadata: {sql_count} queries (pre-validation: {pre_validation_count})"
        )
        for i, q in enumerate(sql_collector.queries):
            print(f"  [{i + 1}] {q[:120]}...")

        assert response.status_code == 200, (
            f"metadata returned {response.status_code}: {response.text}"
        )

        assert sql_count <= 3, f"Expected ≤3 SQL queries for metadata, got {sql_count}"
        assert pre_validation_count <= 3, (
            f"Expected ≤3 pre-validation queries for metadata, got {pre_validation_count}"
        )


class TestQueryBaseline:
    """测试 POST /shares/{s}/schemas/{s}/tables/{t}/query 路由的 SQL 查询次数基线。"""

    def test_query_route_sql_count_baseline(self, client_dp_seeded, sql_collector):
        """POST .../query → 记录 SQL 条数（Mock iceberg/version/predicate service）。

        优化后预期：总 SQL ≤ 3（含 token 认证），前置验证（不含 token）≤ 2。
        get_table_config() 单次调用替代 schema_exists() + table_exists() 两次查询。
        """
        mock_iceberg = MagicMock()
        mock_iceberg.get_current_snapshot.return_value = {
            "snapshot-id": "snap-001",
            "timestamp-ms": 1000,
        }
        mock_iceberg.get_data_files.return_value = ([], False)
        mock_iceberg.get_partition_columns.return_value = []
        mock_iceberg.build_file_objects.return_value = []
        mock_iceberg.get_table_metadata.return_value = {
            "id": "table-uuid",
            "schema_string": "{}",
            "partition_columns": [],
        }
        mock_version = MagicMock()
        mock_version.get_or_allocate_version.return_value = 1
        mock_predicate = MagicMock()
        mock_predicate.parse_predicate_hints.return_value = []
        mock_predicate.filter_files.return_value = []

        sql_collector.reset()

        with (
            patch("app.routes.query.iceberg_service", mock_iceberg),
            patch("app.routes.query.version_service", mock_version),
            patch("app.routes.query.predicate_service", mock_predicate),
        ):
            response = client_dp_seeded.post(
                "/delta-sharing/shares/test_share/schemas/test_schema/tables/test_table/query",
                json={},
            )

        sql_count = len(sql_collector.queries)
        pre_validation_queries = [
            q for q in sql_collector.queries if "bearer_tokens" not in q.lower()
        ]
        pre_validation_count = len(pre_validation_queries)

        print(f"\n[SQL COUNT] query: {sql_count} queries (pre-validation: {pre_validation_count})")
        for i, q in enumerate(sql_collector.queries):
            print(f"  [{i + 1}] {q[:120]}...")

        assert response.status_code == 200, (
            f"query returned {response.status_code}: {response.text}"
        )

        assert sql_count <= 3, f"Expected ≤3 SQL queries for query, got {sql_count}"
        assert pre_validation_count <= 3, (
            f"Expected ≤3 pre-validation queries for query, got {pre_validation_count}"
        )


class TestQueryRouteErrors:
    """测试 query 路由在 schema/table 不存在时的错误处理。

    get_table_config() 返回 None 后，仅在 schema 不存在时触发额外 schema_exists() 查询。
    """

    def test_query_route_schema_not_found(self, client_dp_seeded, sql_collector):
        """POST .../query → schema 不存在时返回 SCHEMA_NOT_FOUND。

        预期：触发 get_table_config() (2条) + schema_exists() (2条) + auth (1条) = 5条 SQL。
        """
        mock_iceberg = MagicMock()
        mock_iceberg.get_current_snapshot.return_value = {"snapshot-id": "snap-001"}
        mock_version = MagicMock()
        mock_predicate = MagicMock()

        sql_collector.reset()

        with (
            patch("app.routes.query.iceberg_service", mock_iceberg),
            patch("app.routes.query.version_service", mock_version),
            patch("app.routes.query.predicate_service", mock_predicate),
        ):
            response = client_dp_seeded.post(
                "/delta-sharing/shares/test_share/schemas/nonexistent_schema/tables/test_table/query",
                json={},
            )

        sql_count = len(sql_collector.queries)
        print(f"\n[SQL COUNT] query schema_not_found: {sql_count} queries")
        for i, q in enumerate(sql_collector.queries):
            print(f"  [{i + 1}] {q[:120]}...")

        assert response.status_code == 404, (
            f"Expected 404 for missing schema, got {response.status_code}: {response.text}"
        )
        assert sql_count <= 5, f"Expected ≤5 SQL queries for schema_not_found, got {sql_count}"

    def test_query_route_table_not_found(self, client_dp_seeded, sql_collector):
        """POST .../query → table 不存在时返回 TABLE_NOT_FOUND。

        预期：get_table_config() (2条) + schema_exists() (2条) + auth (1条) = 5条 SQL。
        """
        mock_iceberg = MagicMock()
        mock_iceberg.get_current_snapshot.return_value = {"snapshot-id": "snap-001"}
        mock_version = MagicMock()
        mock_predicate = MagicMock()

        sql_collector.reset()

        with (
            patch("app.routes.query.iceberg_service", mock_iceberg),
            patch("app.routes.query.version_service", mock_version),
            patch("app.routes.query.predicate_service", mock_predicate),
        ):
            response = client_dp_seeded.post(
                "/delta-sharing/shares/test_share/schemas/test_schema/tables/nonexistent_table/query",
                json={},
            )

        sql_count = len(sql_collector.queries)
        print(f"\n[SQL COUNT] query table_not_found: {sql_count} queries")
        for i, q in enumerate(sql_collector.queries):
            print(f"  [{i + 1}] {q[:120]}...")

        assert response.status_code == 404, (
            f"Expected 404 for missing table, got {response.status_code}: {response.text}"
        )
        assert sql_count <= 5, f"Expected ≤5 SQL queries for table_not_found, got {sql_count}"
