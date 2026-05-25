import json

import pytest
from unittest.mock import MagicMock, patch
from app.core.config import DLCConfig
from app.core.dlc_client import DLCClientWrapper, DLCConfigError, DLCAPIError, DLCError


class TestDLCClientWrapper:
    def test_dlc_config_initialization(self):
        config = DLCConfig()
        assert config.secret_id == ""
        assert config.secret_key == ""
        assert config.region == ""
        assert config.endpoint == ""

    def test_dlc_config_with_values(self):
        config = DLCConfig()
        config.secret_id = "test_id"
        config.secret_key = "test_key"
        config.region = "ap-guangzhou"
        config.endpoint = "dlc.tencentcloudapi.com"

        assert config.secret_id == "test_id"
        assert config.secret_key == "test_key"
        assert config.region == "ap-guangzhou"
        assert config.endpoint == "dlc.tencentcloudapi.com"

    def test_describe_tables_without_credentials_raises_config_error(self):
        config = DLCConfig()
        client = DLCClientWrapper(config)

        with pytest.raises(DLCConfigError) as exc_info:
            client.describe_tables("test_database")
        assert "DLC credentials not configured" in str(exc_info.value)

    def test_describe_table_without_credentials_raises_config_error(self):
        config = DLCConfig()
        client = DLCClientWrapper(config)

        with pytest.raises(DLCConfigError) as exc_info:
            client.describe_table("test_database", "test_table")
        assert "DLC credentials not configured" in str(exc_info.value)

    @patch("app.core.dlc_client.DLCClient")
    def test_describe_tables_success(self, mock_dlc_client_class):
        config = DLCConfig()
        config.secret_id = "test_id"
        config.secret_key = "test_key"
        config.region = "ap-guangzhou"

        mock_response = MagicMock()
        mock_response.to_json_string.return_value = '{"TableList": [{"TableBaseInfo": {"TableName": "table1"}, "Location": "cos://bucket/path1", "Properties": [], "Partitions": []}], "TotalCount": 1}'

        mock_client_instance = MagicMock()
        mock_client_instance.DescribeTables.return_value = mock_response
        mock_dlc_client_class.return_value = mock_client_instance

        client = DLCClientWrapper(config)
        result = client.describe_tables("test_database")

        assert "table_list" in result
        assert "total_count" in result
        assert result["total_count"] == 1
        assert len(result["table_list"]) == 1
        assert result["table_list"][0]["name"] == "table1"
        assert result["table_list"][0]["location"] == "cos://bucket/path1"

    @patch("app.core.dlc_client.DLCClient")
    def test_describe_tables_api_error_raises_api_error(self, mock_dlc_client_class):
        config = DLCConfig()
        config.secret_id = "test_id"
        config.secret_key = "test_key"
        config.region = "ap-guangzhou"

        mock_client_instance = MagicMock()
        mock_client_instance.DescribeTables.side_effect = Exception("API Error")
        mock_dlc_client_class.return_value = mock_client_instance

        client = DLCClientWrapper(config)

        with pytest.raises(DLCAPIError) as exc_info:
            client.describe_tables("test_database")
        assert "Failed to describe tables" in str(exc_info.value)

    @patch("app.core.dlc_client.DLCClient")
    def test_extract_table_info_from_response(self, mock_dlc_client_class):
        config = DLCConfig()
        config.secret_id = "test_id"
        config.secret_key = "test_key"
        config.region = "ap-guangzhou"

        mock_response = MagicMock()
        mock_response.to_json_string.return_value = '{"TableList": [{"TableBaseInfo": {"TableName": "table1"}}, {"TableBaseInfo": {"TableName": "table2"}}]}'

        mock_client_instance = MagicMock()
        mock_client_instance.DescribeTables.return_value = mock_response
        mock_dlc_client_class.return_value = mock_client_instance

        client = DLCClientWrapper(config)
        result = client.describe_tables("test_database")

        raw_response = {"parsed": json.loads(result["raw_response"])}
        table_info = DLCClientWrapper.extract_table_info(raw_response)
        assert table_info is not None
        assert len(table_info) == 2

    def test_extract_table_info_empty_response(self):
        result = {"parsed": {}}
        table_info = DLCClientWrapper.extract_table_info(result)
        assert table_info is None


class TestDLCErrorClasses:
    def test_dlc_error_base_class(self):
        error = DLCError("Test error")
        assert str(error) == "Test error"

    def test_dlc_config_error(self):
        error = DLCConfigError("Config not set")
        assert str(error) == "Config not set"
        assert isinstance(error, DLCError)
        assert isinstance(error, Exception)

    def test_dlc_api_error_with_code(self):
        error = DLCAPIError("API failed", code="INVALID_PARAMETER")
        assert str(error) == "API failed"
        assert error.code == "INVALID_PARAMETER"
        assert isinstance(error, DLCError)
        assert isinstance(error, Exception)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
