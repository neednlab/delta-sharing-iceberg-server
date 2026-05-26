import json
import pytest
from unittest.mock import MagicMock, patch

from app.core.config import (
    Config,
)
from app.core.errors import DeltaSharingError, ErrorCode
from app.core.authentication import normalize_name, AuthService, get_current_recipient


class TestConfig:
    def test_config_initialization(self):
        config = Config()
        assert config.server.host == "0.0.0.0"
        assert config.server.port == 8088
        assert config.server.api_prefix == "/delta-sharing"
        assert config.cos.region == ""
        assert config.database.url == "sqlite:///./data/server.db"
        assert config.token.rotation_period_hours == 24
        assert config.token.expiration_hours == 168
        assert config.presigned_url.expiration_hours == 6

    def test_config_from_dict(self):
        data = {
            "server": {"host": "127.0.0.1", "port": 9000, "api_prefix": "/api"},
            "cos": {"region": "ap-guangzhou"},
            "database": {"url": "sqlite:////tmp/test.db"},
        }

        config = Config.from_dict(data)
        assert config.server.host == "127.0.0.1"
        assert config.server.port == 9000
        assert config.server.api_prefix == "/api"
        assert config.cos.region == "ap-guangzhou"
        assert config.database.url == "sqlite:////tmp/test.db"


class TestErrorCodes:
    def test_error_codes_exist(self):
        assert ErrorCode.INVALID_TOKEN.value == "INVALID_TOKEN"
        assert ErrorCode.TOKEN_EXPIRED.value == "TOKEN_EXPIRED"
        assert ErrorCode.ACCESS_DENIED.value == "ACCESS_DENIED"
        assert ErrorCode.SHARE_NOT_FOUND.value == "SHARE_NOT_FOUND"
        assert ErrorCode.SCHEMA_NOT_FOUND.value == "SCHEMA_NOT_FOUND"
        assert ErrorCode.TABLE_NOT_FOUND.value == "TABLE_NOT_FOUND"
        assert ErrorCode.TABLE_NOT_SUPPORTED.value == "TABLE_NOT_SUPPORTED"
        assert ErrorCode.INVALID_REQUEST.value == "INVALID_REQUEST"
        assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"

    def test_delta_sharing_error_to_dict(self):
        error = DeltaSharingError(
            error_code=ErrorCode.SHARE_NOT_FOUND, message="Share not found", status_code=404
        )

        error_dict = error.to_dict()
        assert error_dict["errorCode"] == "SHARE_NOT_FOUND"
        assert error_dict["message"] == "Share not found"


class TestAuthService:
    """AuthService 单元测试

    使用 mock TokenRepository 隔离数据库依赖，验证 Service 层业务逻辑。
    """

    @pytest.fixture
    def auth_service(self):
        """创建 AuthService 实例，注入 mock TokenRepository。"""
        service = AuthService()
        service.token_repo = MagicMock()
        return service

    # ------------------------------------------------------------------
    # normalize_name 测试
    # ------------------------------------------------------------------

    def test_normalize_name(self):
        assert normalize_name("MyShare") == "myshare"
        assert normalize_name("MySchema") == "myschema"
        assert normalize_name("MyTable") == "mytable"
        assert normalize_name("UPPERCASE") == "uppercase"

    def test_auth_service_case_insensitive(self):
        assert normalize_name("CaseSensitive") == normalize_name("casesensitive")
        assert normalize_name("MixedCase") == normalize_name("mixedcase")

    # ------------------------------------------------------------------
    # validate_token 测试
    # ------------------------------------------------------------------

    def test_validate_token_empty(self, auth_service):
        """空 token 应返回 None。"""
        assert auth_service.validate_token("") is None

    def test_validate_token_not_found(self, auth_service):
        """数据库中不存在该 token 哈希时返回 None。"""
        auth_service.token_repo.find_by_hash.return_value = None
        result = auth_service.validate_token("some-token")
        assert result is None

    def test_validate_token_valid(self, auth_service):
        """有效 token（未撤销、未过期）返回完整信息。"""
        auth_service.token_repo.find_by_hash.return_value = {
            "recipient_id": "rec-001",
            "expires_at": 9999999999,
            "is_revoked": False,
        }
        result = auth_service.validate_token("valid-token")
        assert result is not None
        assert result["recipient_id"] == "rec-001"
        assert result["is_revoked"] is False
        assert result["is_expired"] is False

    def test_validate_token_revoked(self, auth_service):
        """已撤销 token 应返回 is_revoked=True，不再返回 None。"""
        auth_service.token_repo.find_by_hash.return_value = {
            "recipient_id": "rec-002",
            "expires_at": 9999999999,
            "is_revoked": True,
        }
        result = auth_service.validate_token("revoked-token")
        assert result is not None
        assert result["is_revoked"] is True
        assert result["recipient_id"] == "rec-002"

    def test_validate_token_expired(self, auth_service):
        """已过期 token 应返回 is_expired=True。"""
        auth_service.token_repo.find_by_hash.return_value = {
            "recipient_id": "rec-003",
            "expires_at": 1,
            "is_revoked": False,
        }
        result = auth_service.validate_token("expired-token")
        assert result is not None
        assert result["is_expired"] is True
        assert result["is_revoked"] is False

    # ------------------------------------------------------------------
    # get_token_info 测试
    # ------------------------------------------------------------------

    def test_get_token_info_empty(self, auth_service):
        """空 token 应返回 None。"""
        assert auth_service.get_token_info("") is None

    def test_get_token_info_not_found(self, auth_service):
        """数据库中不存在该 token 哈希时返回 None。"""
        auth_service.token_repo.find_by_hash.return_value = None
        result = auth_service.get_token_info("some-token")
        assert result is None

    def test_get_token_info_found(self, auth_service):
        """找到 token 时返回包含 is_expired 和 is_revoked 的完整信息。"""
        auth_service.token_repo.find_by_hash.return_value = {
            "recipient_id": "rec-004",
            "expires_at": 9999999999,
            "is_revoked": False,
        }
        result = auth_service.get_token_info("some-token")
        assert result is not None
        assert result["recipient_id"] == "rec-004"
        assert "is_expired" in result
        assert "is_revoked" in result
        assert result["is_revoked"] is False

    # ------------------------------------------------------------------
    # revoke_token 测试
    # ------------------------------------------------------------------

    def test_revoke_token_success(self, auth_service):
        """撤销成功时返回 True。"""
        auth_service.token_repo.revoke.return_value = True
        result = auth_service.revoke_token("some-token", "test reason")
        assert result is True
        auth_service.token_repo.revoke.assert_called_once()

    def test_revoke_token_failure(self, auth_service):
        """撤销失败时返回 False。"""
        auth_service.token_repo.revoke.return_value = False
        result = auth_service.revoke_token("non-existent-token")
        assert result is False

    # ------------------------------------------------------------------
    # validate_token 和 get_token_info 返回结构一致性测试
    # ------------------------------------------------------------------

    def test_validate_and_get_token_info_same_structure(self, auth_service):
        """两个方法对同一有效 token 应返回相同字段集。"""
        mock_record = {
            "recipient_id": "rec-005",
            "expires_at": 9999999999,
            "is_revoked": False,
        }
        auth_service.token_repo.find_by_hash.return_value = mock_record

        validate_result = auth_service.validate_token("token")
        get_info_result = auth_service.get_token_info("token")

        assert set(validate_result.keys()) == set(get_info_result.keys())
        assert validate_result["recipient_id"] == get_info_result["recipient_id"]


class TestGetCurrentRecipient:
    """get_current_recipient FastAPI 依赖函数单元测试

    使用 mock Request 对象模拟 HTTP 请求的各种认证场景。
    """

    @pytest.fixture
    def mock_request(self):
        """创建 mock FastAPI Request。"""
        req = MagicMock()
        req.headers = {}
        return req

    async def test_missing_authorization_header(self, mock_request):
        """缺失 Authorization 头应抛出 401。"""
        mock_request.headers = {}
        with pytest.raises(DeltaSharingError) as exc_info:
            await get_current_recipient(mock_request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.error_code == ErrorCode.AUTHENTICATION_HEADER_MISSING

    async def test_invalid_authorization_format(self, mock_request):
        """Authorization 头格式无效（非 Bearer）应抛出 401。"""
        mock_request.headers = {"authorization": "Basic abc123"}
        with pytest.raises(DeltaSharingError) as exc_info:
            await get_current_recipient(mock_request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.error_code == ErrorCode.AUTHENTICATION_HEADER_INVALID

    async def test_empty_token(self, mock_request):
        """Bearer 后 token 为空应抛出 401。"""
        mock_request.headers = {"authorization": "Bearer "}
        with pytest.raises(DeltaSharingError) as exc_info:
            await get_current_recipient(mock_request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.error_code == ErrorCode.TOKEN_MALFORMED

    async def test_token_not_found_in_db(self, mock_request):
        """数据库中没有该 token 记录应抛出 401。"""
        token = "unknown-token-12345"
        mock_request.headers = {"authorization": f"Bearer {token}"}

        with patch.object(AuthService, "validate_token", return_value=None):
            with pytest.raises(DeltaSharingError) as exc_info:
                await get_current_recipient(mock_request)
            assert exc_info.value.status_code == 401
            assert exc_info.value.error_code == ErrorCode.INVALID_TOKEN

    async def test_revoked_token(self, mock_request):
        """已撤销 token 应抛出 403。"""
        token = "revoked-token-12345"
        mock_request.headers = {"authorization": f"Bearer {token}"}

        with patch.object(
            AuthService,
            "validate_token",
            return_value={
                "recipient_id": "rec-revoked",
                "expires_at": 9999999999,
                "is_expired": False,
                "is_revoked": True,
            },
        ):
            with pytest.raises(DeltaSharingError) as exc_info:
                await get_current_recipient(mock_request)
            assert exc_info.value.status_code == 403
            assert exc_info.value.error_code == ErrorCode.TOKEN_REVOKED

    async def test_expired_token(self, mock_request):
        """已过期 token 应抛出 403。"""
        token = "expired-token-12345"
        mock_request.headers = {"authorization": f"Bearer {token}"}

        with patch.object(
            AuthService,
            "validate_token",
            return_value={
                "recipient_id": "rec-expired",
                "expires_at": 1,
                "is_expired": True,
                "is_revoked": False,
            },
        ):
            with pytest.raises(DeltaSharingError) as exc_info:
                await get_current_recipient(mock_request)
            assert exc_info.value.status_code == 403
            assert exc_info.value.error_code == ErrorCode.TOKEN_EXPIRED

    async def test_valid_token(self, mock_request):
        """有效 token 应返回 recipient_id。"""
        token = "valid-token-12345"
        mock_request.headers = {"authorization": f"Bearer {token}"}

        with patch.object(
            AuthService,
            "validate_token",
            return_value={
                "recipient_id": "rec-valid",
                "expires_at": 9999999999,
                "is_expired": False,
                "is_revoked": False,
            },
        ):
            result = await get_current_recipient(mock_request)
            assert result == "rec-valid"


class TestIcebergSchemaConverter:
    """IcebergSchemaConverter 单元测试

    验证 schema 序列化输出符合 Delta Sharing 协议规范的 Schema Object 格式。
    """

    def test_convert_primitive_types(self):
        """验证基本类型字段的 type 属性为类型名字符串。"""
        from pyiceberg.types import (
            BooleanType,
            IntegerType,
            LongType,
            FloatType,
            DoubleType,
            DateType,
            TimestampType,
            StringType,
            BinaryType,
            DecimalType,
            NestedField,
        )
        from app.services.iceberg_service import IcebergSchemaConverter

        test_cases = [
            (IntegerType(), "integer"),
            (BooleanType(), "boolean"),
            (LongType(), "long"),
            (FloatType(), "float"),
            (DoubleType(), "double"),
            (DateType(), "date"),
            (TimestampType(), "timestamp"),
            (StringType(), "string"),
            (BinaryType(), "binary"),
            (DecimalType(precision=10, scale=2), "decimal(10,2)"),
        ]

        for field_type, expected_type_name in test_cases:
            field = NestedField(1, "test_col", field_type, required=True)
            result = IcebergSchemaConverter.convert_primitive(field)
            assert result["type"] == expected_type_name, (
                f"{type(field_type).__name__}: expected type={expected_type_name}, got {result['type']}"
            )
            assert result["name"] == "test_col"
            assert result["nullable"] is False
            assert result["metadata"] == {}

    def test_convert_struct_nested_type_format(self):
        """验证 struct 类型字段输出嵌套 type 对象格式。"""
        from pyiceberg.types import StructType, StringType, NestedField
        from app.services.iceberg_service import IcebergSchemaConverter

        struct_type = StructType(
            fields=(
                NestedField(1, "city", StringType(), required=False),
                NestedField(2, "zip", StringType(), required=False),
            )
        )
        result = IcebergSchemaConverter.convert_struct(struct_type, "address", is_nullable=True)

        assert result["name"] == "address"
        assert result["nullable"] is True
        assert result["metadata"] == {}
        assert isinstance(result["type"], dict), "struct 字段的 type 应为嵌套对象"

        inner_type = result["type"]
        assert inner_type["type"] == "struct"
        assert len(inner_type["fields"]) == 2
        assert inner_type["fields"][0] == {
            "name": "city",
            "type": "string",
            "nullable": True,
            "metadata": {},
        }
        assert inner_type["fields"][1] == {
            "name": "zip",
            "type": "string",
            "nullable": True,
            "metadata": {},
        }

    def test_convert_list_primitive_element(self):
        """验证 list<基本类型> 输出 elementType 为类型名字符串。"""
        from pyiceberg.types import ListType, IntegerType
        from app.services.iceberg_service import IcebergSchemaConverter

        list_type = ListType(element_id=1, element_type=IntegerType(), element_required=True)
        result = IcebergSchemaConverter.convert_list(list_type, "tags", is_nullable=True)

        assert result["name"] == "tags"
        assert result["nullable"] is True
        assert isinstance(result["type"], dict), "array 字段的 type 应为嵌套对象"

        inner_type = result["type"]
        assert inner_type["type"] == "array"
        assert inner_type["elementType"] == "integer"
        assert "element" not in inner_type, "不应出现旧键名 element"
        assert inner_type["containsNull"] == (not list_type.element_field.required)

    def test_convert_list_struct_element(self):
        """验证 list<struct<...>> 输出 elementType 为嵌套 struct type 对象。"""
        from pyiceberg.types import ListType, StructType, StringType, IntegerType, NestedField
        from app.services.iceberg_service import IcebergSchemaConverter

        struct_type = StructType(
            fields=(
                NestedField(1, "name", StringType(), required=False),
                NestedField(2, "value", IntegerType(), required=False),
            )
        )
        list_type = ListType(element_id=1, element_type=struct_type, element_required=True)
        result = IcebergSchemaConverter.convert_list(list_type, "items", is_nullable=True)

        inner_type = result["type"]
        assert inner_type["type"] == "array"
        assert isinstance(inner_type["elementType"], dict), "elementType 对复杂类型应为嵌套对象"
        assert inner_type["elementType"]["type"] == "struct"
        assert len(inner_type["elementType"]["fields"]) == 2
        assert inner_type["elementType"]["fields"][0]["name"] == "name"
        assert inner_type["elementType"]["fields"][0]["type"] == "string"
        assert inner_type["elementType"]["fields"][1]["name"] == "value"
        assert inner_type["elementType"]["fields"][1]["type"] == "integer"

    def test_convert_map_primitive_key_value(self):
        """验证 map<string, int> 输出 keyType/valueType 为类型名字符串。"""
        from pyiceberg.types import MapType, StringType, IntegerType
        from app.services.iceberg_service import IcebergSchemaConverter

        map_type = MapType(
            key_id=1,
            key_type=StringType(),
            value_id=2,
            value_type=IntegerType(),
            value_required=False,
        )
        result = IcebergSchemaConverter.convert_map(map_type, "scores", is_nullable=True)

        assert result["name"] == "scores"
        assert isinstance(result["type"], dict), "map 字段的 type 应为嵌套对象"

        inner_type = result["type"]
        assert inner_type["type"] == "map"
        assert inner_type["keyType"] == "string", "基本类型 key 应为类型名字符串"
        assert inner_type["valueType"] == "integer", "基本类型 value 应为类型名字符串"
        assert inner_type["valueContainsNull"] is True
        assert "key" not in inner_type, "不应出现旧键名 key"
        assert "value" not in inner_type, "不应出现旧键名 value"

    def test_convert_map_nested_value(self):
        """验证 map<string, array<int>> 输出 valueType 为嵌套 array type 对象。"""
        from pyiceberg.types import MapType, StringType, ListType, IntegerType
        from app.services.iceberg_service import IcebergSchemaConverter

        list_type = ListType(element_id=1, element_type=IntegerType(), element_required=True)
        map_type = MapType(
            key_id=1, key_type=StringType(), value_id=2, value_type=list_type, value_required=False
        )
        result = IcebergSchemaConverter.convert_map(map_type, "items_map", is_nullable=True)

        inner_type = result["type"]
        assert inner_type["type"] == "map"
        assert inner_type["keyType"] == "string", "基本类型 key 应为类型名字符串"
        assert isinstance(inner_type["valueType"], dict), "复杂类型 value 应为嵌套 type 对象"
        assert inner_type["valueType"]["type"] == "array"
        assert inner_type["valueType"]["elementType"] == "integer"

    def test_deep_nesting_array_struct(self):
        """验证深层嵌套 array<struct<name, value>> 的正确递归序列化。"""
        from pyiceberg.types import ListType, StructType, StringType, IntegerType, NestedField
        from app.services.iceberg_service import IcebergSchemaConverter

        struct_type = StructType(
            fields=(
                NestedField(1, "name", StringType(), required=False),
                NestedField(2, "value", IntegerType(), required=False),
            )
        )
        list_type = ListType(element_id=1, element_type=struct_type, element_required=True)
        result = IcebergSchemaConverter.convert_list(list_type, "items", is_nullable=True)

        inner_type = result["type"]
        assert inner_type["type"] == "array"
        element_type = inner_type["elementType"]
        assert isinstance(element_type, dict), "elementType 应为嵌套 struct type 对象"
        assert element_type["type"] == "struct"
        assert len(element_type["fields"]) == 2

        name_field = element_type["fields"][0]
        assert name_field == {"name": "name", "type": "string", "nullable": True, "metadata": {}}

        value_field = element_type["fields"][1]
        assert value_field == {"name": "value", "type": "integer", "nullable": True, "metadata": {}}

    def test_pyspark_from_json_parsing(self):
        """验证生成的 JSON Schema 可被 PySpark DataType.fromJson() 正确解析。"""
        from pyiceberg.types import (
            StructType,
            StringType,
            IntegerType,
            LongType,
            FloatType,
            ListType,
            MapType,
            NestedField,
        )
        from app.services.iceberg_service import IcebergSchemaConverter
        from pyspark.sql.types import StructType as SparkStructType

        # 构建一个包含所有复杂类型的 Iceberg schema
        struct_type = StructType(
            fields=(
                NestedField(1, "id", IntegerType(), required=True),
                NestedField(2, "name", StringType(), required=False),
                NestedField(3, "age", LongType(), required=False),
                NestedField(4, "score", FloatType(), required=False),
                NestedField(
                    5,
                    "address",
                    StructType(
                        fields=(
                            NestedField(6, "city", StringType(), required=False),
                            NestedField(7, "zip", StringType(), required=False),
                        )
                    ),
                    required=False,
                ),
                NestedField(
                    8,
                    "tags",
                    ListType(element_id=8, element_type=StringType(), element_required=True),
                    required=False,
                ),
                NestedField(
                    9,
                    "items",
                    ListType(
                        element_id=9,
                        element_type=StructType(
                            fields=(
                                NestedField(10, "name", StringType(), required=False),
                                NestedField(11, "value", IntegerType(), required=False),
                            )
                        ),
                        element_required=True,
                    ),
                    required=False,
                ),
                NestedField(
                    12,
                    "scores",
                    MapType(
                        key_id=12,
                        key_type=StringType(),
                        value_id=13,
                        value_type=IntegerType(),
                        value_required=False,
                    ),
                    required=False,
                ),
            )
        )

        # 通过 convert_schema 生成完整 JSON
        from pyiceberg.schema import Schema as IcebergSchema

        schema_obj = IcebergSchema(
            schema_id=0,
            type="struct",
            fields=struct_type.fields,
        )
        json_str = IcebergSchemaConverter.convert_schema(schema_obj)

        # PySpark StructType.fromJson() 应成功解析不抛出异常
        parsed = SparkStructType.fromJson(json.loads(json_str))
        assert parsed is not None, "PySpark 应能成功解析 schema JSON"

        # 验证解析后的结构
        parsed_fields = {f.name: f for f in parsed.fields}
        assert "id" in parsed_fields
        assert parsed_fields["id"].dataType.typeName() == "integer"
        assert parsed_fields["id"].nullable is False

        assert "name" in parsed_fields
        assert parsed_fields["name"].dataType.typeName() == "string"

        assert "address" in parsed_fields
        assert parsed_fields["address"].dataType.typeName() == "struct"
        address_fields = {f.name: f for f in parsed_fields["address"].dataType.fields}
        assert "city" in address_fields
        assert "zip" in address_fields

        assert "tags" in parsed_fields
        assert parsed_fields["tags"].dataType.typeName() == "array"
        assert parsed_fields["tags"].dataType.elementType.typeName() == "string"

        assert "items" in parsed_fields
        assert parsed_fields["items"].dataType.typeName() == "array"
        assert parsed_fields["items"].dataType.elementType.typeName() == "struct"

        assert "scores" in parsed_fields
        assert parsed_fields["scores"].dataType.typeName() == "map"

    def test_short_byte_type_serialization(self):
        """验证 short 和 byte 类型正确序列化。"""
        from pyiceberg.types import NestedField
        from app.services.iceberg_service import (
            _ShortType,
            _ByteType,
            IcebergSchemaConverter,
        )

        # short 类型
        short_field = NestedField(1, "small_val", _ShortType(), required=False)
        result_short = IcebergSchemaConverter.convert_primitive(short_field)
        assert result_short["type"] == "short"
        assert result_short["name"] == "small_val"
        assert result_short["nullable"] is True

        # byte 类型
        byte_field = NestedField(2, "tiny_val", _ByteType(), required=True)
        result_byte = IcebergSchemaConverter.convert_primitive(byte_field)
        assert result_byte["type"] == "byte"
        assert result_byte["name"] == "tiny_val"
        assert result_byte["nullable"] is False

    def test_parse_field_type_short_byte(self):
        """验证 _parse_field_type 正确返回 short/byte 类型实例。"""
        from app.services.iceberg_service import (
            _ShortType,
            _ByteType,
            IcebergSchemaConverter,
        )

        assert isinstance(IcebergSchemaConverter._parse_field_type("short"), _ShortType)
        assert isinstance(IcebergSchemaConverter._parse_field_type("byte"), _ByteType)

    def test_type_value_short_byte(self):
        """验证 _type_value 对 short/byte 返回正确字符串。"""
        from app.services.iceberg_service import (
            _ShortType,
            _ByteType,
            IcebergSchemaConverter,
        )

        assert IcebergSchemaConverter._type_value(_ShortType()) == "short"
        assert IcebergSchemaConverter._type_value(_ByteType()) == "byte"

    def test_parse_field_type_any_list_dict_format(self):
        """验证 _parse_field_type_any 正确解析 Iceberg 元数据 JSON 中的 list dict 格式。"""
        from pyiceberg.types import ListType, StringType
        from app.services.iceberg_service import IcebergSchemaConverter

        # 模拟 Iceberg 元数据 JSON 中 list 类型的嵌套 dict
        list_type_dict = {
            "type": "list",
            "element-id": 9,
            "element-required": True,
            "element": "string",
        }
        result = IcebergSchemaConverter._parse_field_type_any(list_type_dict)
        assert isinstance(result, ListType)
        assert result.element_id == 9
        assert result.element_required is True
        assert isinstance(result.element_type, StringType)

    def test_parse_field_type_any_list_nested_dict_format(self):
        """验证 _parse_field_type_any 正确解析嵌套 list<struct> 的 dict 格式。"""
        from pyiceberg.types import ListType, StructType, StringType, IntegerType
        from app.services.iceberg_service import IcebergSchemaConverter

        # 模拟 Iceberg 元数据 JSON 中 list<struct> 的嵌套 dict
        list_type_dict = {
            "type": "list",
            "element-id": 10,
            "element-required": False,
            "element": {
                "type": "struct",
                "fields": [
                    {"id": 11, "name": "key", "type": "string", "required": False},
                    {"id": 12, "name": "value", "type": "int", "required": False},
                ],
            },
        }
        result = IcebergSchemaConverter._parse_field_type_any(list_type_dict)
        assert isinstance(result, ListType)
        assert result.element_id == 10
        assert isinstance(result.element_type, StructType)
        assert len(result.element_type.fields) == 2
        assert result.element_type.fields[0].name == "key"
        assert isinstance(result.element_type.fields[0].field_type, StringType)
        assert result.element_type.fields[1].name == "value"
        assert isinstance(result.element_type.fields[1].field_type, IntegerType)

    def test_parse_field_type_any_map_dict_format(self):
        """验证 _parse_field_type_any 正确解析 Iceberg 元数据 JSON 中的 map dict 格式。"""
        from pyiceberg.types import MapType, StringType, IntegerType
        from app.services.iceberg_service import IcebergSchemaConverter

        # 模拟 Iceberg 元数据 JSON 中 map<string, int> 的嵌套 dict
        map_type_dict = {
            "type": "map",
            "key-id": 13,
            "key": "string",
            "value-id": 14,
            "value": "int",
            "value-required": True,
        }
        result = IcebergSchemaConverter._parse_field_type_any(map_type_dict)
        assert isinstance(result, MapType)
        assert result.key_id == 13
        assert result.value_id == 14
        assert isinstance(result.key_type, StringType)
        assert isinstance(result.value_type, IntegerType)

    def test_parse_field_type_any_struct_dict_format(self):
        """验证 _parse_field_type_any 正确解析 Iceberg 元数据 JSON 中的 struct dict 格式。"""
        from pyiceberg.types import StructType, StringType, IntegerType
        from app.services.iceberg_service import IcebergSchemaConverter

        # 模拟 Iceberg 元数据 JSON 中 struct 类型的嵌套 dict
        struct_type_dict = {
            "type": "struct",
            "fields": [
                {"id": 15, "name": "city", "type": "string", "required": False},
                {"id": 16, "name": "code", "type": "int", "required": True},
            ],
        }
        result = IcebergSchemaConverter._parse_field_type_any(struct_type_dict)
        assert isinstance(result, StructType)
        assert len(result.fields) == 2
        assert result.fields[0].name == "city"
        assert isinstance(result.fields[0].field_type, StringType)
        assert result.fields[0].required is False
        assert result.fields[1].name == "code"
        assert isinstance(result.fields[1].field_type, IntegerType)
        assert result.fields[1].required is True

    def test_parse_field_type_any_string_fallback(self):
        """验证 _parse_field_type_any 对基本类型字符串保持原有行为。"""
        from pyiceberg.types import IntegerType, StringType, LongType
        from app.services.iceberg_service import (
            _ShortType,
            _ByteType,
            IcebergSchemaConverter,
        )

        assert isinstance(IcebergSchemaConverter._parse_field_type_any("int"), IntegerType)
        assert isinstance(IcebergSchemaConverter._parse_field_type_any("string"), StringType)
        assert isinstance(IcebergSchemaConverter._parse_field_type_any("long"), LongType)
        assert isinstance(IcebergSchemaConverter._parse_field_type_any("short"), _ShortType)
        assert isinstance(IcebergSchemaConverter._parse_field_type_any("byte"), _ByteType)

    def test_parse_field_type_any_decimal_dict_format(self):
        """验证 _parse_field_type_any 正确解析 Iceberg 元数据 JSON 中的 decimal dict 格式。

        这是修复远程 Databricks 客户端报 "Read schema Decimal(10,2) is not compatible
        with Parquet schema Decimal(38,0)" 的关键测试用例。
        在 Iceberg metadata.json 中，decimal 字段以 dict 格式存储：
        {"type": "decimal", "precision": 38, "scale": 0}
        但之前缺少此分支，导致 precision/scale 被丢弃，总是回退到默认的 (10,2)。
        """
        from pyiceberg.types import DecimalType
        from app.services.iceberg_service import IcebergSchemaConverter

        # 模拟 DLC 中创建表时定义的 Decimal(38, 0) 字段
        decimal_type_dict = {
            "type": "decimal",
            "precision": 38,
            "scale": 0,
        }
        result = IcebergSchemaConverter._parse_field_type_any(decimal_type_dict)
        assert isinstance(result, DecimalType)
        assert result.precision == 38, f"expected precision=38, got {result.precision}"
        assert result.scale == 0, f"expected scale=0, got {result.scale}"

    def test_parse_field_type_any_decimal_dict_various_precision_scale(self):
        """验证 dict 格式 decimal 在不同 precision/scale 组合下均正确解析。"""
        from pyiceberg.types import DecimalType
        from app.services.iceberg_service import IcebergSchemaConverter

        test_cases = [
            ({"type": "decimal", "precision": 38, "scale": 0}, (38, 0)),
            ({"type": "decimal", "precision": 10, "scale": 2}, (10, 2)),
            ({"type": "decimal", "precision": 20, "scale": 5}, (20, 5)),
            ({"type": "decimal", "precision": 38, "scale": 38}, (38, 38)),
            ({"type": "decimal", "precision": 1, "scale": 0}, (1, 0)),
        ]

        for type_dict, (expected_precision, expected_scale) in test_cases:
            result = IcebergSchemaConverter._parse_field_type_any(type_dict)
            assert isinstance(result, DecimalType)
            assert result.precision == expected_precision, (
                f"dict {type_dict}: expected precision={expected_precision}, got {result.precision}"
            )
            assert result.scale == expected_scale, (
                f"dict {type_dict}: expected scale={expected_scale}, got {result.scale}"
            )

    def test_parse_field_type_any_decimal_dict_defaults(self):
        """验证 dict 格式 decimal 缺少 precision/scale 字段时使用合理默认值。"""
        from pyiceberg.types import DecimalType
        from app.services.iceberg_service import IcebergSchemaConverter

        # 仅有 type 字段，缺少 precision 和 scale
        result = IcebergSchemaConverter._parse_field_type_any({"type": "decimal"})
        assert isinstance(result, DecimalType)
        assert result.precision == 10
        assert result.scale == 2

    def test_parse_field_type_any_decimal_string_format(self):
        """验证字符串格式 decimal(38,0) 依然正确解析（回归测试），包括带空格格式。"""
        from pyiceberg.types import DecimalType
        from app.services.iceberg_service import IcebergSchemaConverter

        # 标准无空格格式
        result = IcebergSchemaConverter._parse_field_type_any("decimal(38,0)")
        assert isinstance(result, DecimalType)
        assert result.precision == 38
        assert result.scale == 0

        result = IcebergSchemaConverter._parse_field_type_any("decimal(10,2)")
        assert isinstance(result, DecimalType)
        assert result.precision == 10
        assert result.scale == 2

        # 带空格格式（COS Iceberg 元数据实际存储格式）
        result = IcebergSchemaConverter._parse_field_type_any("decimal(38, 0)")
        assert isinstance(result, DecimalType)
        assert result.precision == 38, f"带空格: 期望 precision=38, 实际={result.precision}"
        assert result.scale == 0, f"带空格: 期望 scale=0, 实际={result.scale}"

        result = IcebergSchemaConverter._parse_field_type_any("decimal(38, 2)")
        assert isinstance(result, DecimalType)
        assert result.precision == 38
        assert result.scale == 2

        result = IcebergSchemaConverter._parse_field_type_any("decimal(18, 0)")
        assert isinstance(result, DecimalType)
        assert result.precision == 18
        assert result.scale == 0

        # 多空格也兼容
        result = IcebergSchemaConverter._parse_field_type_any("decimal( 38 , 0 )")
        assert isinstance(result, DecimalType)
        assert result.precision == 38
        assert result.scale == 0

    def test_parse_field_type_leading_trailing_whitespace(self):
        """验证 _parse_field_type 能正确处理字符串首尾空格。"""
        from pyiceberg.types import IntegerType, StringType, LongType, FloatType
        from app.services.iceberg_service import IcebergSchemaConverter

        assert isinstance(IcebergSchemaConverter._parse_field_type(" int"), IntegerType)
        assert isinstance(IcebergSchemaConverter._parse_field_type("string "), StringType)
        assert isinstance(IcebergSchemaConverter._parse_field_type(" long "), LongType)
        assert isinstance(IcebergSchemaConverter._parse_field_type("\tfloat "), FloatType)

        # decimal 也兼容首尾空格
        result = IcebergSchemaConverter._parse_field_type(" decimal(38, 0) ")
        assert result.precision == 38
        assert result.scale == 0

    def test_parse_field_type_any_decimal_roundtrip_consistency(self):
        """验证 decimal dict 格式解析后，经 convert_primitive 能正确序列化回字符串。

        这确保从 Iceberg metadata.json 读取 → type 对象 → schema JSON 的
        完整往返过程中 precision/scale 不会丢失。
        """
        from pyiceberg.types import DecimalType, NestedField
        from app.services.iceberg_service import IcebergSchemaConverter

        # 模拟完整流程：metadata.json 的 dict → type 对象 → protocol JSON
        dict_input = {"type": "decimal", "precision": 38, "scale": 0}
        parsed_type = IcebergSchemaConverter._parse_field_type_any(dict_input)
        assert isinstance(parsed_type, DecimalType)

        # 构建 NestedField 并序列化为协议格式
        field = NestedField(1, "sls_qty", parsed_type, required=False)
        result = IcebergSchemaConverter.convert_primitive(field)
        assert result["type"] == "decimal(38,0)", (
            f"往返序列化失败: 期望 'decimal(38,0)'，实际 '{result['type']}'"
        )
        assert result["name"] == "sls_qty"

    def test_parse_field_type_numeric_synonym(self):
        """验证 numeric 作为 decimal 的防御性别名能正确解析。

        Iceberg 规范仅定义 decimal(P,S)，但某些 SQL 引擎可能写入
        numeric(P,S) 格式。本测试确保两种格式等效解析。
        """
        from pyiceberg.types import DecimalType
        from app.services.iceberg_service import IcebergSchemaConverter

        # 字符串格式：numeric(P, S) 应解析为 DecimalType
        result = IcebergSchemaConverter._parse_field_type("numeric(38, 0)")
        assert isinstance(result, DecimalType)
        assert result.precision == 38
        assert result.scale == 0

        result = IcebergSchemaConverter._parse_field_type("numeric(10, 2)")
        assert isinstance(result, DecimalType)
        assert result.precision == 10
        assert result.scale == 2

        # 带空格格式也应兼容
        result = IcebergSchemaConverter._parse_field_type("numeric(38, 0)")
        assert result.precision == 38
        assert result.scale == 0

    def test_parse_field_type_any_numeric_dict_format(self):
        """验证 dict 格式 numeric 类型能正确解析为 DecimalType。"""
        from pyiceberg.types import DecimalType
        from app.services.iceberg_service import IcebergSchemaConverter

        numeric_dict = {
            "type": "numeric",
            "precision": 38,
            "scale": 0,
        }
        result = IcebergSchemaConverter._parse_field_type_any(numeric_dict)
        assert isinstance(result, DecimalType)
        assert result.precision == 38
        assert result.scale == 0

    def test_parse_field_type_any_numeric_string_format(self):
        """验证 _parse_field_type_any 通过字符串路径也能处理 numeric。"""
        from pyiceberg.types import DecimalType
        from app.services.iceberg_service import IcebergSchemaConverter

        # _parse_field_type_any 接收字符串时应转发给 _parse_field_type
        result = IcebergSchemaConverter._parse_field_type_any("numeric(38, 2)")
        assert isinstance(result, DecimalType)
        assert result.precision == 38
        assert result.scale == 2

    def test_numeric_to_decimal_roundtrip_output_is_standard(self):
        """验证 numeric 输入始终输出标准 decimal(P,S) 格式。

        无论输入是 decimal 还是 numeric，输出端 _type_value 都必须
        序列化为标准 decimal(P,S) 格式，保证协议兼容性。
        """
        from pyiceberg.types import NestedField
        from app.services.iceberg_service import IcebergSchemaConverter

        # numeric(38,0) 输入 → 解析 → 序列化 → 输出 "decimal(38,0)"
        parsed = IcebergSchemaConverter._parse_field_type("numeric(38, 0)")
        field = NestedField(1, "qty", parsed, required=False)
        result = IcebergSchemaConverter.convert_primitive(field)
        assert result["type"] == "decimal(38,0)", (
            f"numeric 输入应输出标准 decimal 格式，实际: {result['type']}"
        )

    def test_convert_schema_full_format(self):
        """验证 convert_schema 完整输出格式符合协议规范示例。"""
        from pyiceberg.types import (
            StructType,
            IntegerType,
            NestedField,
        )
        from app.services.iceberg_service import IcebergSchemaConverter
        from pyiceberg.schema import Schema as IcebergSchema

        struct_type = StructType(
            fields=(
                NestedField(1, "a", IntegerType(), required=True),
                NestedField(
                    2,
                    "b",
                    StructType(fields=(NestedField(3, "d", IntegerType(), required=True),)),
                    required=False,
                ),
            )
        )
        schema_obj = IcebergSchema(schema_id=0, type="struct", fields=struct_type.fields)
        json_str = IcebergSchemaConverter.convert_schema(schema_obj)
        schema = json.loads(json_str)

        assert schema["type"] == "struct"
        assert len(schema["fields"]) == 2

        # 字段 a: 基本类型 integer, 不可为空, 带 metadata comment
        field_a = schema["fields"][0]
        assert field_a["name"] == "a"
        assert field_a["type"] == "integer"
        assert field_a["nullable"] is False

        # 字段 b: struct 类型, 可空, type 为嵌套对象
        field_b = schema["fields"][1]
        assert field_b["name"] == "b"
        assert isinstance(field_b["type"], dict)
        assert field_b["type"]["type"] == "struct"
        assert len(field_b["type"]["fields"]) == 1
        assert field_b["type"]["fields"][0]["name"] == "d"
        assert field_b["type"]["fields"][0]["type"] == "integer"
        assert field_b["type"]["fields"][0]["nullable"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
