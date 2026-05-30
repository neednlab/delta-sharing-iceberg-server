import pytest
from unittest.mock import patch


class TestHealthEndpoint:
    def test_health_check(self, client_dp):
        response = client_dp.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestSharesEndpoint:
    @patch("app.routes.shares.share_service")
    def test_list_shares(self, mock_share, client_dp):
        mock_share.list_shares.return_value = {
            "items": [{"name": "share1"}, {"name": "share2"}],
            "next_page_token": None,
        }

        response = client_dp.get("/delta-sharing/shares")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["name"] == "share1"

    @patch("app.routes.shares.share_service")
    def test_list_shares_with_pagination(self, mock_share, client_dp):
        mock_share.list_shares.return_value = {
            "items": [{"name": "share3"}],
            "next_page_token": "2",
        }

        response = client_dp.get("/delta-sharing/shares?maxResults=2")
        assert response.status_code == 200
        data = response.json()
        assert data["next_page_token"] == "2"


class TestChangesEndpoint:
    def test_changes_endpoint_returns_internal_error(self, client_dp):
        response = client_dp.get("/delta-sharing/changes")
        assert response.status_code == 500
        data = response.json()
        assert data["errorCode"] == "INTERNAL_ERROR"


class TestSchemaEndpoint:
    @patch("app.routes.shares.share_service")
    def test_list_schemas_share_not_found(self, mock_service, client_dp):
        mock_service.share_exists.return_value = False

        response = client_dp.get("/delta-sharing/shares/unknown/schemas")
        assert response.status_code == 404
        data = response.json()
        assert data["errorCode"] == "SHARE_NOT_FOUND"

    @patch("app.routes.shares.share_service")
    @patch("app.routes.shares.auth_repo")
    def test_list_schemas_success(self, mock_auth, mock_service, client_dp):
        mock_service.share_exists.return_value = True
        mock_auth.check_access_with_share_validation.return_value = {"share_id": "fake-id", "authorized": True}
        mock_service.list_schemas.return_value = {
            "items": [{"name": "schema1", "share": "share1"}],
            "next_page_token": None,
        }

        response = client_dp.get("/delta-sharing/shares/share1/schemas")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "schema1"
        assert data["items"][0]["share"] == "share1"


class TestTableEndpoint:
    @patch("app.routes.shares.share_service")
    def test_list_tables_share_not_found(self, mock_service, client_dp):
        mock_service.share_exists.return_value = False

        response = client_dp.get("/delta-sharing/shares/unknown/schemas/schema1/tables")
        assert response.status_code == 404

    @patch("app.routes.shares.share_service")
    @patch("app.routes.shares.auth_repo")
    def test_list_tables_schema_not_found(self, mock_auth, mock_service, client_dp):
        mock_service.share_exists.return_value = True
        mock_auth.check_access_with_share_validation.return_value = {"share_id": "fake-id", "authorized": True}
        mock_service.schema_exists.return_value = False

        response = client_dp.get("/delta-sharing/shares/share1/schemas/unknown/tables")
        assert response.status_code == 404
        data = response.json()
        assert data["errorCode"] == "SCHEMA_NOT_FOUND"


class TestErrorResponse:
    def test_delta_sharing_error_format(self, client_dp):
        response = client_dp.get("/delta-sharing/changes")
        data = response.json()

        assert "errorCode" in data
        assert "message" in data
        assert data["errorCode"] == "INTERNAL_ERROR"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
