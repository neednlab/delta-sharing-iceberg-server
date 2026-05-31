"""
DeltaSharingCapabilities 及相关数据类单元测试

覆盖范围：
- parse_delta_sharing_capabilities: header 解析
- DeltaSharingCapabilities.to_response_header: 序列化
- EndStreamAction.to_json_dict / to_delta_dict
- DeltaProtocol.to_delta_dict
- DeltaMetadata.to_delta_dict
- DeltaFileAction.to_delta_dict
"""

import pytest
from app.core.delta_capabilities import (
    ResponseFormat,
    DeltaSharingCapabilities,
    parse_delta_sharing_capabilities,
    get_default_capabilities,
    EndStreamAction,
    DeltaProtocol,
    DeltaMetadata,
    DeltaFileAction,
)


class TestParseDeltaSharingCapabilities:
    def test_empty_header_returns_defaults(self):
        result = parse_delta_sharing_capabilities(None)
        assert result.response_format == ResponseFormat.PARQUET
        assert result.reader_features == set()
        assert result.include_end_stream_action is False

    def test_empty_string_returns_defaults(self):
        result = parse_delta_sharing_capabilities("")
        assert result.response_format == ResponseFormat.PARQUET
        assert result.reader_features == set()
        assert result.include_end_stream_action is False

    def test_full_header_parsing(self):
        header = "responseFormat=parquet;readerFeatures=deletionVectors,columnMapping;includeEndStreamAction=false"
        result = parse_delta_sharing_capabilities(header)
        assert result.response_format == ResponseFormat.PARQUET
        assert result.reader_features == {"deletionvectors", "columnmapping"}
        assert result.include_end_stream_action is False

    def test_case_insensitive(self):
        header = "RESPONSEFORMAT=DELTA;READERFEATURES=DV"
        result = parse_delta_sharing_capabilities(header)
        assert result.response_format == ResponseFormat.DELTA
        assert result.reader_features == {"dv"}

    def test_comma_separated_multi_format(self):
        header = "responseFormat=parquet,delta"
        result = parse_delta_sharing_capabilities(header)
        assert result.response_format == ResponseFormat.PARQUET

    def test_unknown_format_falls_back_to_parquet(self):
        header = "responseFormat=unknown"
        result = parse_delta_sharing_capabilities(header)
        assert result.response_format == ResponseFormat.PARQUET

    def test_include_end_stream_action_false_for_parquet(self):
        header = "responseFormat=parquet;includeEndStreamAction=true"
        result = parse_delta_sharing_capabilities(header)
        assert result.include_end_stream_action is False


class TestToResponseHeader:
    def test_full_serialization(self):
        caps = DeltaSharingCapabilities(
            response_format=ResponseFormat.DELTA,
            reader_features={"dv", "cm"},
            include_end_stream_action=True,
        )
        header = caps.to_response_header()
        assert "responseFormat=delta" in header
        assert "readerFeatures=cm,dv" in header
        assert "includeEndStreamAction=true" in header

    def test_empty_reader_features_omitted(self):
        caps = DeltaSharingCapabilities(
            response_format=ResponseFormat.PARQUET,
            reader_features=set(),
            include_end_stream_action=False,
        )
        header = caps.to_response_header()
        assert "readerFeatures" not in header
        assert "responseFormat=parquet" in header
        assert "includeEndStreamAction=false" in header


class TestEndStreamAction:
    def test_to_json_dict_only_non_none_fields(self):
        action = EndStreamAction(next_page_token="abc", refresh_token=None)
        result = action.to_json_dict()
        assert result == {"nextPageToken": "abc"}
        assert "refreshToken" not in result

    def test_to_json_dict_all_none_returns_empty(self):
        action = EndStreamAction()
        result = action.to_json_dict()
        assert result == {}

    def test_to_delta_dict_wraps_format(self):
        action = EndStreamAction(next_page_token="abc")
        result = action.to_delta_dict()
        assert result == {"endStreamAction": {"nextPageToken": "abc"}}

    def test_to_delta_dict_all_fields(self):
        action = EndStreamAction(
            refresh_token="rt",
            next_page_token="np",
            min_url_expiration_timestamp=123456,
            error_message="err",
        )
        result = action.to_delta_dict()
        inner = result["endStreamAction"]
        assert inner["refreshToken"] == "rt"
        assert inner["nextPageToken"] == "np"
        assert inner["minUrlExpirationTimestamp"] == 123456
        assert inner["errorMessage"] == "err"


class TestDeltaProtocol:
    def test_to_delta_dict_defaults(self):
        proto = DeltaProtocol()
        result = proto.to_delta_dict()
        assert result == {
            "protocol": {
                "deltaProtocol": {
                    "minReaderVersion": 1,
                    "minWriterVersion": 2,
                }
            }
        }

    def test_to_delta_dict_custom_values(self):
        proto = DeltaProtocol(min_reader_version=3, min_writer_version=7)
        result = proto.to_delta_dict()
        dp = result["protocol"]["deltaProtocol"]
        assert dp["minReaderVersion"] == 3
        assert dp["minWriterVersion"] == 7


class TestDeltaMetadata:
    def test_to_delta_dict_basic_fields(self):
        meta = DeltaMetadata(
            id="test-id",
            format={"provider": "parquet"},
            schema_string='{"type":"struct"}',
        )
        result = meta.to_delta_dict()
        assert result["metaData"]["deltaMetadata"]["id"] == "test-id"
        assert result["metaData"]["deltaMetadata"]["format"] == {"provider": "parquet"}
        assert result["metaData"]["deltaMetadata"]["schemaString"] == '{"type":"struct"}'

    def test_to_delta_dict_partition_columns(self):
        meta = DeltaMetadata(
            id="id",
            partition_columns=["dt", "region"],
        )
        result = meta.to_delta_dict()
        assert result["metaData"]["deltaMetadata"]["partitionColumns"] == [
            "dt",
            "region",
        ]

    def test_to_delta_dict_location_and_size(self):
        meta = DeltaMetadata(
            id="id",
            location="s3://bucket/table",
            size=1024,
            num_files=5,
        )
        result = meta.to_delta_dict()
        assert result["metaData"]["location"] == "s3://bucket/table"
        assert result["metaData"]["size"] == 1024
        assert result["metaData"]["numFiles"] == 5


class TestDeltaFileAction:
    def test_to_delta_dict_path_mapping(self):
        fa = DeltaFileAction(
            url="https://cos.example.com/file.parquet",
            id="file-1",
            size=1024,
        )
        result = fa.to_delta_dict()
        add = result["file"]["deltaSingleAction"]["add"]
        assert add["path"] == "https://cos.example.com/file.parquet"

    def test_to_delta_dict_partition_values(self):
        fa = DeltaFileAction(
            url="https://cos.example.com/file.parquet",
            id="file-1",
            partition_values={"dt": "2026-01-01"},
        )
        result = fa.to_delta_dict()
        add = result["file"]["deltaSingleAction"]["add"]
        assert add["partitionValues"] == {"dt": "2026-01-01"}

    def test_to_delta_dict_stats(self):
        fa = DeltaFileAction(
            url="s3://bucket/file.parquet",
            id="f1",
            stats='{"numRecords":100}',
        )
        result = fa.to_delta_dict()
        add = result["file"]["deltaSingleAction"]["add"]
        assert add["stats"] == '{"numRecords":100}'

    def test_to_delta_dict_expiration(self):
        fa = DeltaFileAction(
            url="s3://bucket/file.parquet",
            id="f1",
            expiration_timestamp=1700000000,
        )
        result = fa.to_delta_dict()
        assert result["file"]["expirationTimestamp"] == 1700000000


class TestGetDefaultCapabilities:
    def test_returns_default_parquet(self):
        caps = get_default_capabilities()
        assert caps.response_format == ResponseFormat.PARQUET
        assert caps.reader_features == set()
        assert caps.include_end_stream_action is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
