"""
REST API AuthZ (Authorization) 测试模块

该模块测试 Delta Sharing Server 的完整 AuthN/AuthZ 安全检查流程：
- 身份认证 (Authentication): Bearer Token 验证
- 访问授权 (Authorization): Recipient-Share 授权关系验证

测试覆盖场景：
- 401: 认证失败 (缺失/无效 token)
- 403: 授权失败 (token 有效但未授权访问 share)
- 200: 认证+授权都成功

测试端点：
- GET /shares - 列出可访问的 share
- GET /shares/{share}/schemas - 列出 share 下的 schema
- GET /shares/{share}/schemas/{schema}/tables - 列出 schema 下的 table
- GET /shares/{share}/schemas/{schema}/tables/{table}/metadata - 获取表元数据
- POST /shares/{share}/schemas/{schema}/tables/{table}/query - 查询表数据
"""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from main import create_data_plane_app
from app.core.database import bearer_tokens
from app.repositories.token_repository import TokenRepository
from app.services.recipient_service import RecipientService
from app.repositories.recipient_share_repository import RecipientShareRepository


@pytest.fixture(scope="function")
def client(test_db):
    """创建 Data Plane TestClient（不带认证覆盖），用于测试 AuthN/AuthZ 流程。"""
    app = create_data_plane_app()
    return TestClient(app)


@pytest.fixture(scope="function")
def auth_service(test_db):
    """RecipientShare Repository 实例（用于授权验证）。"""
    return RecipientShareRepository()


@pytest.fixture(scope="function")
def recipient_service(test_db):
    """Recipient 服务实例。"""
    return RecipientService()


@pytest.fixture(scope="function")
def token_service(test_db):
    """Token 服务实例。"""
    from app.services.token_service import TokenService

    return TokenService()


@pytest.fixture(scope="function")
def recipient_a(recipient_service):
    """创建测试 recipient_a (被授权访问 myshare)。"""
    return recipient_service.create_recipient("recipient_a", "Test recipient A")


@pytest.fixture(scope="function")
def recipient_b(recipient_service):
    """创建测试 recipient_b (被授权访问 myshare 和 needn_share)。"""
    return recipient_service.create_recipient("recipient_b", "Test recipient B")


@pytest.fixture(scope="function")
def valid_token_a(token_service, recipient_a):
    """创建 recipient_a 的有效 token。"""
    return token_service.generate_token(
        recipient_a["recipient_id"], require_authorized_shares=False
    )["token"]


@pytest.fixture(scope="function")
def valid_token_b(token_service, recipient_b):
    """创建 recipient_b 的有效 token。"""
    return token_service.generate_token(
        recipient_b["recipient_id"], require_authorized_shares=False
    )["token"]


@pytest.fixture(scope="function")
def expired_token(token_service, recipient_a):
    """创建已过期的 token (通过直接数据库操作创建)。"""
    import hashlib

    from app.core.database import get_database

    token = token_service.generate_token(
        recipient_a["recipient_id"], require_authorized_shares=False
    )["token"]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = get_database().get_engine()
    past_ts = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    with conn.begin() as c:
        c.execute(
            bearer_tokens.update()
            .values(expires_at=past_ts)
            .where(bearer_tokens.c.token_hash == token_hash)
        )
    return token


@pytest.fixture(scope="function")
def revoked_token(token_service, recipient_a):
    """创建已撤销的 token。"""
    token = token_service.generate_token(
        recipient_a["recipient_id"], require_authorized_shares=False
    )["token"]
    import hashlib

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    token_repo = TokenRepository()
    token_repo.revoke(token_hash, "Test revocation")
    return token


@pytest.fixture(scope="function")
def mock_share_service():
    """Mock share_service。"""
    mock = MagicMock()
    mock.share_exists.return_value = True
    mock.schema_exists.return_value = True
    mock.table_exists.return_value = True
    mock.list_schemas.return_value = {"items": []}
    mock.list_tables.return_value = {"items": []}
    mock.get_table_metadata.return_value = {"name": "ice_t1", "schema": {"name": "myschema"}}
    mock.list_shares.return_value = {"items": []}
    mock.query_table.return_value = {"data": []}
    return mock


def _make_auth_mock(return_value=None, side_effect=None, only_allow_share=None):
    """创建符合新 check_access_with_share_validation 签名的 mock。

    check_access_with_share_validation(share_name, recipient_id)
    返回: None (share 不存在) 或 {"share_id": "...", "authorized": True/False}

    Args:
        return_value: 固定返回值。
        side_effect: 自定义副作用函数。
        only_allow_share: 简化参数，仅允许指定 share（其余返回 authorized=False）。
    """
    mock = MagicMock()
    if return_value is not None:
        mock.check_access_with_share_validation.return_value = return_value
    elif side_effect is not None:
        mock.check_access_with_share_validation.side_effect = side_effect
    elif only_allow_share is not None:
        mock.check_access_with_share_validation.side_effect = lambda sn, rid: {
            "share_id": "fake-id",
            "authorized": sn.lower() == only_allow_share,
        }
    return mock


class TestAuthenticationRequired:
    """测试需要认证的端点在未提供认证信息时的行为 (401 场景)。"""

    def test_list_shares_without_auth_header(self, client):
        """GET /shares - 无 Authorization header 时返回 401。"""
        response = client.get("/delta-sharing/shares")
        assert response.status_code == 401
        data = response.json()
        assert data["errorCode"] == "AUTHENTICATION_HEADER_MISSING"

    def test_list_shares_with_invalid_auth_format(self, client):
        """GET /shares - Authorization header 格式无效时返回 401。"""
        response = client.get("/delta-sharing/shares", headers={"Authorization": "InvalidFormat"})
        assert response.status_code == 401
        data = response.json()
        assert data["errorCode"] == "AUTHENTICATION_HEADER_INVALID"

    def test_list_shares_with_empty_bearer_token(self, client):
        """GET /shares - Bearer token 为空时返回 401。"""
        response = client.get("/delta-sharing/shares", headers={"Authorization": "Bearer "})
        assert response.status_code == 401
        data = response.json()
        assert data["errorCode"] == "TOKEN_MALFORMED"

    def test_list_shares_with_invalid_token(self, client):
        """GET /shares - Token 无效时返回 401。"""
        response = client.get(
            "/delta-sharing/shares",
            headers={"Authorization": "Bearer invalid_token_12345"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["errorCode"] == "INVALID_TOKEN"

    def test_list_schemas_without_auth(self, client):
        """GET /shares/{share}/schemas - 无认证时返回 401。"""
        response = client.get("/delta-sharing/shares/myshare/schemas")
        assert response.status_code == 401

    def test_list_tables_without_auth(self, client):
        """GET /shares/{share}/schemas/{schema}/tables - 无认证时返回 401。"""
        response = client.get("/delta-sharing/shares/myshare/schemas/myschema/tables")
        assert response.status_code == 401

    def test_table_metadata_without_auth(self, client):
        """GET /shares/{share}/schemas/{schema}/tables/{table}/metadata - 无认证时返回 401。"""
        response = client.get(
            "/delta-sharing/shares/myshare/schemas/myschema/tables/ice_t1/metadata"
        )
        assert response.status_code == 401

    def test_query_table_without_auth(self, client):
        """POST /shares/{share}/schemas/{schema}/tables/{table}/query - 无认证时返回 401。"""
        response = client.post("/delta-sharing/shares/myshare/schemas/myschema/tables/ice_t1/query")
        assert response.status_code == 401


class TestTokenExpirationAndRevocation:
    """测试 token 过期和撤销场景 (403 场景)。"""

    def test_expired_token_on_list_shares(self, client, expired_token):
        """过期的 token 返回 403。"""
        response = client.get(
            "/delta-sharing/shares",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["errorCode"] == "TOKEN_EXPIRED"

    def test_revoked_token_on_list_shares(self, client, revoked_token):
        """已撤销的 token 返回 403。"""
        response = client.get(
            "/delta-sharing/shares",
            headers={"Authorization": f"Bearer {revoked_token}"},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["errorCode"] == "TOKEN_REVOKED"

    def test_expired_token_on_list_schemas(self, client, expired_token, mock_share_service):
        """过期 token 访问 list_schemas 返回 403。"""
        with patch("app.routes.shares.share_service", mock_share_service):
            response = client.get(
                "/delta-sharing/shares/myshare/schemas",
                headers={"Authorization": f"Bearer {expired_token}"},
            )
        assert response.status_code == 403
        data = response.json()
        assert data["errorCode"] == "TOKEN_EXPIRED"

    def test_revoked_token_on_list_tables(self, client, revoked_token, mock_share_service):
        """已撤销 token 访问 list_tables 返回 403。"""
        with patch("app.routes.shares.share_service", mock_share_service):
            response = client.get(
                "/delta-sharing/shares/myshare/schemas/myschema/tables",
                headers={"Authorization": f"Bearer {revoked_token}"},
            )
        assert response.status_code == 403
        data = response.json()
        assert data["errorCode"] == "TOKEN_REVOKED"


class TestShareAuthorization:
    """测试 Share 授权验证 (403 场景 - token 有效但未授权访问 share)。"""

    def test_unauthorized_share_access_on_list_schemas(
        self,
        client,
        recipient_a,
        valid_token_a,
        mock_share_service,
    ):
        """有效 token 但未授权访问 needn_share 时返回 403。"""
        mock_auth = _make_auth_mock(only_allow_share="myshare")

        with (
            patch("app.routes.shares.share_service", mock_share_service),
            patch("app.routes.shares.auth_repo", mock_auth),
        ):
            response = client.get(
                "/delta-sharing/shares/needn_share/schemas",
                headers={"Authorization": f"Bearer {valid_token_a}"},
            )
        assert response.status_code == 403
        data = response.json()
        assert data["errorCode"] == "SHARE_ACCESS_DENIED"

    def test_unauthorized_share_access_on_list_tables(
        self,
        client,
        recipient_a,
        valid_token_a,
        mock_share_service,
    ):
        """有效 token 但未授权访问 share 时，访问 list_tables 返回 403。"""
        mock_auth = _make_auth_mock(only_allow_share="myshare")

        with (
            patch("app.routes.shares.share_service", mock_share_service),
            patch("app.routes.shares.auth_repo", mock_auth),
        ):
            response = client.get(
                "/delta-sharing/shares/needn_share/schemas/needn_schema/tables",
                headers={"Authorization": f"Bearer {valid_token_a}"},
            )
        assert response.status_code == 403
        data = response.json()
        assert data["errorCode"] == "SHARE_ACCESS_DENIED"

    def test_unauthorized_share_access_on_metadata(
        self,
        client,
        recipient_a,
        valid_token_a,
        mock_share_service,
    ):
        """有效 token 但未授权访问 share 时，访问 metadata 返回 403。"""
        mock_auth = _make_auth_mock(only_allow_share="myshare")

        with (
            patch("app.routes.metadata.share_service", mock_share_service),
            patch("app.routes.metadata.auth_repo", mock_auth),
        ):
            response = client.get(
                "/delta-sharing/shares/needn_share/schemas/needn_schema/tables/ice_t1/metadata",
                headers={"Authorization": f"Bearer {valid_token_a}"},
            )
        assert response.status_code == 403
        data = response.json()
        assert data["errorCode"] == "SHARE_ACCESS_DENIED"

    def test_unauthorized_share_access_on_query(
        self,
        client,
        recipient_a,
        valid_token_a,
        mock_share_service,
    ):
        """有效 token 但未授权访问 share 时，访问 query 返回 403。"""
        mock_auth = _make_auth_mock(only_allow_share="myshare")

        with (
            patch("app.routes.query.share_service", mock_share_service),
            patch("app.routes.query.auth_repo", mock_auth),
        ):
            response = client.post(
                "/delta-sharing/shares/needn_share/schemas/needn_schema/tables/ice_t1/query",
                headers={"Authorization": f"Bearer {valid_token_a}"},
            )
        assert response.status_code == 403
        data = response.json()
        assert data["errorCode"] == "SHARE_ACCESS_DENIED"

    def test_authorized_recipient_can_access_authorized_share(
        self,
        client,
        recipient_b,
        valid_token_b,
        mock_share_service,
    ):
        """recipient_b 有权访问 myshare，用它的 token 访问 myshare 时应成功。"""
        mock_auth = _make_auth_mock(return_value={"share_id": "fake-id", "authorized": True})

        with (
            patch("app.routes.shares.share_service", mock_share_service),
            patch("app.routes.shares.auth_repo", mock_auth),
        ):
            response = client.get(
                "/delta-sharing/shares/myshare/schemas",
                headers={"Authorization": f"Bearer {valid_token_b}"},
            )
        assert response.status_code == 200


class TestAuthorizedAccess:
    """测试认证+授权都成功的场景 (200 成功场景)。

    注意：这些测试需要完整的 shares 配置（来自 config.yaml）来验证端点逻辑。
    在测试环境中，我们通过 mock share_service 来避免依赖 COS 配置。
    """

    def test_valid_token_and_authorized_share_list_schemas_with_mock(
        self,
        client,
        valid_token_a,
        mock_share_service,
    ):
        """有效的 token + 已授权的 share + mock，可以访问 list_schemas。"""
        mock_auth = _make_auth_mock(return_value={"share_id": "fake-id", "authorized": True})

        with (
            patch("app.routes.shares.share_service", mock_share_service),
            patch("app.routes.shares.auth_repo", mock_auth),
        ):
            response = client.get(
                "/delta-sharing/shares/myshare/schemas",
                headers={"Authorization": f"Bearer {valid_token_a}"},
            )
        assert response.status_code == 200

    def test_valid_token_and_authorized_share_list_tables_with_mock(
        self,
        client,
        valid_token_a,
        mock_share_service,
    ):
        """有效的 token + 已授权的 share + mock，可以访问 list_tables。"""
        mock_auth = _make_auth_mock(return_value={"share_id": "fake-id", "authorized": True})

        with (
            patch("app.routes.shares.share_service", mock_share_service),
            patch("app.routes.shares.auth_repo", mock_auth),
        ):
            response = client.get(
                "/delta-sharing/shares/myshare/schemas/myschema/tables",
                headers={"Authorization": f"Bearer {valid_token_a}"},
            )
        assert response.status_code == 200

    def test_valid_token_and_authorized_share_get_metadata_with_mock(
        self,
        client,
        valid_token_a,
        mock_share_service,
    ):
        """有效的 token + 已授权的 share + mock，可以访问 metadata。"""
        mock_auth = _make_auth_mock(return_value={"share_id": "fake-id", "authorized": True})
        mock_table = MagicMock()
        mock_table.get_table_config.return_value = {
            "name": "ice_t1",
            "location": "cosn://bucket/ice_t1",
            "bucket": "bucket",
            "region": "ap-shanghai",
        }
        mock_iceberg = MagicMock()
        mock_iceberg.get_current_snapshot.return_value = {
            "snapshot-id": "snap-001",
            "timestamp": 1000,
        }
        mock_iceberg.get_table_metadata.return_value = {
            "id": "table-uuid",
            "name": "ice_t1",
            "schema": {"name": "myschema"},
        }
        mock_version = MagicMock()
        mock_version.get_or_allocate_version.return_value = 1

        with (
            patch("app.routes.metadata.share_service", mock_share_service),
            patch("app.routes.metadata.auth_repo", mock_auth),
            patch("app.routes.metadata.table_service", mock_table),
            patch("app.routes.metadata.iceberg_service", mock_iceberg),
            patch("app.routes.metadata.version_service", mock_version),
        ):
            response = client.get(
                "/delta-sharing/shares/myshare/schemas/myschema/tables/ice_t1/metadata",
                headers={"Authorization": f"Bearer {valid_token_a}"},
            )
        assert response.status_code == 200

    def test_valid_token_and_authorized_share_query_table_with_mock(
        self,
        client,
        valid_token_a,
        mock_share_service,
    ):
        """有效的 token + 已授权的 share + mock，可以访问 query 端点。"""
        mock_auth = _make_auth_mock(return_value={"share_id": "fake-id", "authorized": True})
        mock_table = MagicMock()
        mock_table.get_table_config.return_value = {
            "name": "ice_t1",
            "type": "iceberg",
        }
        mock_iceberg = MagicMock()
        mock_iceberg.get_current_snapshot.return_value = {
            "snapshot-id": "snap-001",
            "timestamp": 1000,
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

        with (
            patch("app.routes.query.share_service", mock_share_service),
            patch("app.routes.query.auth_repo", mock_auth),
            patch("app.routes.query.table_service", mock_table),
            patch("app.routes.query.iceberg_service", mock_iceberg),
            patch("app.routes.query.version_service", mock_version),
            patch("app.routes.query.predicate_service", mock_predicate),
        ):
            response = client.post(
                "/delta-sharing/shares/myshare/schemas/myschema/tables/ice_t1/query",
                headers={"Authorization": f"Bearer {valid_token_a}"},
            )
        assert response.status_code == 200

    def test_recipient_with_multiple_shares_can_access_both_with_mock(
        self,
        client,
        valid_token_b,
        mock_share_service,
    ):
        """recipient_b 有权访问 myshare 和 needn_share，可以访问两者。"""
        mock_auth = _make_auth_mock(return_value={"share_id": "fake-id", "authorized": True})

        with (
            patch("app.routes.shares.share_service", mock_share_service),
            patch("app.routes.shares.auth_repo", mock_auth),
        ):
            response_myshare = client.get(
                "/delta-sharing/shares/myshare/schemas",
                headers={"Authorization": f"Bearer {valid_token_b}"},
            )
            assert response_myshare.status_code == 200

            response_needn = client.get(
                "/delta-sharing/shares/needn_share/schemas",
                headers={"Authorization": f"Bearer {valid_token_b}"},
            )
            assert response_needn.status_code == 200


class TestShareListing:
    """测试 share 列表过滤功能 (只返回有权限访问的 share)。

    注意：这些测试需要有效的 token 和正确的授权服务 mock。
    由于 share_service.list_shares() 内部使用 authorization_service 进行过滤，
    我们在这里只验证响应结构和状态码。
    """

    def test_list_shares_returns_valid_response_with_mock(
        self,
        client,
        valid_token_a,
        mock_share_service,
    ):
        """列出 share 时，验证返回有效的响应结构。"""
        mock_auth = _make_auth_mock(only_allow_share="myshare")

        with (
            patch("app.routes.shares.share_service", mock_share_service),
            patch("app.routes.shares.auth_repo", mock_auth),
        ):
            response = client.get(
                "/delta-sharing/shares",
                headers={"Authorization": f"Bearer {valid_token_a}"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_list_shares_for_recipient_with_multiple_shares_returns_valid_response(
        self,
        client,
        valid_token_b,
        mock_share_service,
    ):
        """recipient_b 有权访问多个 share，验证返回有效的响应结构。"""
        mock_auth = _make_auth_mock(return_value={"share_id": "fake-id", "authorized": True})

        with (
            patch("app.routes.shares.share_service", mock_share_service),
            patch("app.routes.shares.auth_repo", mock_auth),
        ):
            response = client.get(
                "/delta-sharing/shares",
                headers={"Authorization": f"Bearer {valid_token_b}"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
