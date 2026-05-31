"""
Page Token 工具模块单元测试

测试 app.utils.page_token_utils 中的 encode_page_token() 和 decode_page_token()
函数，覆盖正常编解码、恶意 token 拒绝、签名验证、类型校验等场景。
"""

import base64
import json
import hashlib
import hmac
import time

import pytest

from app.utils.page_token_utils import (
    encode_page_token,
    decode_page_token,
    _get_token_secret,
    PAGE_TOKEN_TTL_SECONDS,
)


SECRET_A = "test-secret-a"
SECRET_B = "test-secret-b"


@pytest.fixture(autouse=True)
def _patch_token_secret(monkeypatch):
    """每个测试用例自动将 _get_token_secret 打桩为固定密钥 SECRET_A。

    需要同时打桩两个位置：
    1. app.utils.page_token_utils._get_token_secret（模块内部 encode/decode 引用）
    2. tests.test_page_token_utils._get_token_secret（测试模块 _build_tampered_token 引用）
    """
    monkeypatch.setattr(
        "app.utils.page_token_utils._get_token_secret",
        lambda: SECRET_A,
    )
    monkeypatch.setattr(
        "tests.test_page_token_utils._get_token_secret",
        lambda: SECRET_A,
    )


class TestEncodeDecodeRoundtrip:
    """正常编解码往返测试。"""

    def test_roundtrip_positive_offset(self):
        """验证正偏移量编码后能正确解码。"""
        for offset in [0, 1, 10, 100, 9999]:
            token = encode_page_token(offset)
            decoded = decode_page_token(token)
            assert decoded == offset, f"offset={offset}, decoded={decoded}"

    def test_roundtrip_zero_offset(self):
        """验证 offset=0 能正确往返。"""
        token = encode_page_token(0)
        assert decode_page_token(token) == 0

    def test_roundtrip_large_offset(self):
        """验证大偏移量编码后能正确解码。"""
        offset = 999999
        token = encode_page_token(offset)
        assert decode_page_token(token) == offset


class TestDecodeInvalidBase64:
    """非法 Base64 输入测试。"""

    def test_decode_non_base64_string(self):
        """传入非 Base64 字符串应返回 None。"""
        assert decode_page_token("!!!not-valid-base64!!!") is None

    def test_decode_empty_string(self):
        """传入空字符串应返回 None。"""
        assert decode_page_token("") is None

    def test_decode_none_like_string(self):
        """传入 None 字符串应返回 None（Base64 解码失败）。"""
        assert decode_page_token("None") is None


class TestDecodeInvalidJson:
    """合法 Base64 但非法 JSON 测试。"""

    def test_decode_plain_text_as_base64(self):
        """传入 Base64 编码的纯文本（非 JSON）应返回 None。"""
        plain_text = base64.urlsafe_b64encode(b"this is not json").decode("ascii")
        assert decode_page_token(plain_text) is None

    def test_decode_partial_json(self):
        """传入 Base64 编码的不完整 JSON 应返回 None。"""
        partial = base64.urlsafe_b64encode(b"{invalid").decode("ascii")
        assert decode_page_token(partial) is None


class TestDecodeTamperedPayload:
    """payload 篡改测试。"""

    def test_tampered_offset(self):
        """篡改 payload 中的 offset 值后签名不匹配应返回 None。"""
        original_token = encode_page_token(42)

        raw_bytes = base64.urlsafe_b64decode(original_token)
        outer = json.loads(raw_bytes)
        tampered_inner = '{"offset":999}'
        outer["payload"] = tampered_inner
        tampered_token = base64.urlsafe_b64encode(
            json.dumps(outer).encode("utf-8")
        ).decode("ascii")

        assert decode_page_token(tampered_token) is None

    def test_tampered_sig(self):
        """篡改 sig 字段后签名不匹配应返回 None。"""
        original_token = encode_page_token(42)

        raw_bytes = base64.urlsafe_b64decode(original_token)
        outer = json.loads(raw_bytes)
        outer["sig"] = "0" * 64
        tampered_token = base64.urlsafe_b64encode(
            json.dumps(outer).encode("utf-8")
        ).decode("ascii")

        assert decode_page_token(tampered_token) is None


class TestDecodeWrongSecret:
    """不同密钥编解码测试。"""

    def test_decode_token_from_different_secret(self):
        """使用不同密钥编码的 token 无法被解码。"""
        encoded_with_a = encode_page_token(42)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            "app.utils.page_token_utils._get_token_secret",
            lambda: SECRET_B,
        )

        assert decode_page_token(encoded_with_a) is None

        monkeypatch.undo()

    def test_same_secret_produces_different_sig_than_another(self):
        """相同 offset、不同密钥产生不同的 token。"""
        token_a = encode_page_token(10)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            "app.utils.page_token_utils._get_token_secret",
            lambda: SECRET_B,
        )
        token_b = encode_page_token(10)
        monkeypatch.undo()

        assert token_a != token_b

        raw_a = json.loads(base64.urlsafe_b64decode(token_a))
        raw_b = json.loads(base64.urlsafe_b64decode(token_b))
        assert raw_a["sig"] != raw_b["sig"]


class TestDecodeNonIntegerOffset:
    """payload 中 offset 为非整数类型测试。"""

    def test_float_offset(self):
        """offset 为 float 时应返回 None。"""
        token = _build_tampered_token({"offset": 10.5})
        assert decode_page_token(token) is None

    def test_str_offset(self):
        """offset 为 str 时应返回 None。"""
        token = _build_tampered_token({"offset": "abc"})
        assert decode_page_token(token) is None

    def test_null_offset(self):
        """offset 为 null 时应返回 None。"""
        token = _build_tampered_token({"offset": None})
        assert decode_page_token(token) is None

    def test_bool_offset(self):
        """offset 为 bool 时应返回 None（Python 中 bool 是 int 子类，但 JSON 中 true/false 不是整数）。"""
        token = _build_tampered_token({"offset": True})
        assert decode_page_token(token) is None


class TestDecodeNegativeOffset:
    """offset 为负整数测试。"""

    def test_negative_offset_returns_none(self):
        """offset 为 -1 时应返回 None。"""
        token = _build_tampered_token({"offset": -1})
        assert decode_page_token(token) is None

    def test_large_negative_offset_returns_none(self):
        """offset 为 -999 时应返回 None。"""
        token = _build_tampered_token({"offset": -999})
        assert decode_page_token(token) is None


class TestDecodeMissingFields:
    """token 结构缺少必要字段测试。"""

    def test_missing_offset_key(self):
        """payload 中缺少 offset 键时应返回 None。"""
        token = _build_tampered_token({"other": 42})
        assert decode_page_token(token) is None

    def test_missing_sig_field(self):
        """token 结构中缺少 sig 字段应返回 None。"""
        payload = json.dumps({"offset": 42}, separators=(",", ":"))
        outer = json.dumps({"payload": payload}, separators=(",", ":"))
        token = base64.urlsafe_b64encode(outer.encode("utf-8")).decode("ascii")
        assert decode_page_token(token) is None

    def test_missing_payload_field(self):
        """token 结构中缺少 payload 字段应返回 None。"""
        outer = json.dumps({"sig": "a" * 64}, separators=(",", ":"))
        token = base64.urlsafe_b64encode(outer.encode("utf-8")).decode("ascii")
        assert decode_page_token(token) is None


class TestTokenStructure:
    """Token 结构合规性测试。"""

    def test_token_is_valid_base64(self):
        """验证生成的 token 是合法的 Base64 字符串。"""
        token = encode_page_token(42)
        decoded = base64.urlsafe_b64decode(token)
        assert decoded is not None

    def test_token_contains_payload_and_sig(self):
        """验证 token 解码后包含 payload 和 sig 字段。"""
        token = encode_page_token(42)
        raw = json.loads(base64.urlsafe_b64decode(token))
        assert "payload" in raw
        assert "sig" in raw

    def test_sig_is_64_char_hex(self):
        """验证 sig 是 64 字符的 16 进制字符串（SHA256 HMAC）。"""
        token = encode_page_token(42)
        raw = json.loads(base64.urlsafe_b64decode(token))
        assert len(raw["sig"]) == 64
        assert all(c in "0123456789abcdef" for c in raw["sig"])

    def test_payload_is_compact_json(self):
        """验证 payload 是紧凑 JSON（无多余空格）。"""
        token = encode_page_token(42)
        raw = json.loads(base64.urlsafe_b64decode(token))
        assert " " not in raw["payload"]


class TestDecodeEdgeCases:
    """边界情况测试。"""

    def test_decode_binary_data(self):
        """传入包含二进制数据的 token 应返回 None。"""
        binary_token = base64.urlsafe_b64encode(b"\x00\xff\xfe").decode("ascii")
        assert decode_page_token(binary_token) is None

    def test_decode_list_not_dict(self):
        """传入 Base64 编码的 JSON 数组（非对象）应返回 None。"""
        token = base64.urlsafe_b64encode(b"[1,2,3]").decode("ascii")
        assert decode_page_token(token) is None


class TestTokenExpiration:
    """Token 过期机制测试。"""

    def test_expired_token_returns_none(self, monkeypatch):
        """过期 token 应返回 None。"""
        # 在当前时间编码一个 token
        fixed_now = 1000
        monkeypatch.setattr(
            "app.utils.page_token_utils._get_current_timestamp",
            lambda: fixed_now,
        )
        token = encode_page_token(42)

        # 将时间拨到过期之后（TTL 已过）
        future_time = fixed_now + PAGE_TOKEN_TTL_SECONDS + 1
        monkeypatch.setattr(
            "app.utils.page_token_utils._get_current_timestamp",
            lambda: future_time,
        )

        assert decode_page_token(token) is None

    def test_non_expired_token_decoded(self, monkeypatch):
        """未过期 token 应正常解码。"""
        fixed_now = 1000
        monkeypatch.setattr(
            "app.utils.page_token_utils._get_current_timestamp",
            lambda: fixed_now,
        )
        token = encode_page_token(42)

        # 时间前进至过期前最后一秒
        future_time = fixed_now + PAGE_TOKEN_TTL_SECONDS - 1
        monkeypatch.setattr(
            "app.utils.page_token_utils._get_current_timestamp",
            lambda: future_time,
        )

        assert decode_page_token(token) == 42

    def test_token_expires_exactly_at_ttl_boundary(self, monkeypatch):
        """token 恰好在过期边界（exp == current_time）时应视为过期。"""
        fixed_now = 1000
        monkeypatch.setattr(
            "app.utils.page_token_utils._get_current_timestamp",
            lambda: fixed_now,
        )
        token = encode_page_token(42)

        # 时间精确到过期那一刻
        future_time = fixed_now + PAGE_TOKEN_TTL_SECONDS
        monkeypatch.setattr(
            "app.utils.page_token_utils._get_current_timestamp",
            lambda: future_time,
        )

        assert decode_page_token(token) is None


class TestBackwardCompatibility:
    """旧格式 token（无 exp 字段）向后兼容测试。"""

    def test_old_format_token_without_exp_is_accepted(self):
        """无 exp 字段的旧格式 token 应跳过过期校验，正常解码。"""
        token = _build_tampered_token({"offset": 99})
        assert decode_page_token(token) == 99

    def test_old_format_token_without_iat_is_accepted(self):
        """无 iat 字段的旧格式 token 应正常解码。"""
        token = _build_tampered_token({"offset": 555})
        assert decode_page_token(token) == 555


class TestIatField:
    """iat 字段正确嵌入测试。"""

    def test_encode_embeds_iat_in_payload(self, monkeypatch):
        """encode_page_token 应在 payload 中嵌入当前时间戳作为 iat。"""
        fixed_now = int(time.time())
        monkeypatch.setattr(
            "app.utils.page_token_utils._get_current_timestamp",
            lambda: fixed_now,
        )

        token = encode_page_token(7)
        raw = json.loads(base64.urlsafe_b64decode(token))
        inner = json.loads(raw["payload"])

        assert inner["iat"] == fixed_now
        assert inner["offset"] == 7
        assert inner["exp"] == fixed_now + PAGE_TOKEN_TTL_SECONDS

    def test_iat_is_integer(self):
        """iat 字段应为整数类型的时间戳。"""
        token = encode_page_token(1)
        raw = json.loads(base64.urlsafe_b64decode(token))
        inner = json.loads(raw["payload"])

        assert isinstance(inner["iat"], int)
        assert inner["iat"] > 0

    def test_iat_and_exp_relationship(self):
        """exp 应等于 iat + TTL。"""
        token = encode_page_token(1)
        raw = json.loads(base64.urlsafe_b64decode(token))
        inner = json.loads(raw["payload"])

        assert inner["exp"] == inner["iat"] + PAGE_TOKEN_TTL_SECONDS


def _build_tampered_token(inner_payload: dict) -> str:
    """构建一个带有合法 HMAC 签名但自定义 inner_payload 的 token。

    此辅助函数用于构造需要绕过 HMAC 校验的测试场景（如类型校验、范围校验测试），
    它使用当前打桩的密钥对提供的 inner_payload 正确签名，确保 token 能通过 HMAC 校验，
    只让后续的类型/范围校验逻辑捕获。

    Args:
        inner_payload: 内层 payload 字典（如 {"offset": 10.5}）。

    Returns:
        Base64 编码的签名 token 字符串。
    """
    secret = _get_token_secret()
    payload = json.dumps(inner_payload, separators=(",", ":"))
    sig = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token_structure = json.dumps(
        {"payload": payload, "sig": sig}, separators=(",", ":")
    )
    return base64.urlsafe_b64encode(token_structure.encode("utf-8")).decode("ascii")
