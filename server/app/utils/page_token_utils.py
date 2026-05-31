"""
Page Token 编解码工具模块

提供基于 HMAC-SHA256 签名的安全 page token 编解码功能。
Token 结构: base64({"payload": compact_json, "sig": hex_digest})

该模块作为共享工具供 share_service.py 和 recipient_service.py 统一引用，
消除重复代码并确保安全策略一致。
"""

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Optional

from loguru import logger

PAGE_TOKEN_TTL_SECONDS = 86400


def _get_current_timestamp() -> int:
    """获取当前 Unix 时间戳（秒）。

    统一时间戳获取方式，便于测试时 mock 和替换。

    Returns:
        当前 UTC 时间的 Unix 时间戳（整数秒）。
    """
    return int(time.time())


def _get_token_secret() -> str:
    """获取 page token HMAC 签名密钥。

    从全局配置中读取 page_token_secret，若为空则抛出 RuntimeError。
    该函数假设启动时 _validate_page_token_secret() 已确保非生产模式下密钥非空。

    Returns:
        HMAC 签名密钥字符串。

    Raises:
        RuntimeError: 密钥为空时抛出（理论上不应发生）。
    """
    from app.core.config import get_config

    config = get_config()
    secret = (config.token.page_token_secret or "").strip()

    if not secret:
        raise RuntimeError(
            "PAGE_TOKEN_SECRET is not configured. "
            "This should have been caught by startup validation."
        )

    return secret


def encode_page_token(offset: int) -> str:
    """将偏移量编码为安全的 page token。

    编码流程:
        1. 获取当前时间戳
        2. 将 offset、iat（签发时间戳）、exp（过期时间戳）序列化为紧凑 JSON payload
        3. 使用 HMAC-SHA256 对 payload 签名
        4. 组装 {"payload": ..., "sig": ...} 结构体
        5. Base64 编码整个结构体

    Args:
        offset: 分页偏移量（非负整数）。

    Returns:
        Base64 编码的签名 token 字符串。
    """
    secret = _get_token_secret()

    now = _get_current_timestamp()
    payload = json.dumps(
        {"offset": offset, "iat": now, "exp": now + PAGE_TOKEN_TTL_SECONDS},
        separators=(",", ":"),
    )

    sig = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    token_structure = json.dumps(
        {"payload": payload, "sig": sig}, separators=(",", ":")
    )

    return base64.urlsafe_b64encode(token_structure.encode("utf-8")).decode("ascii")


def decode_page_token(token: str) -> Optional[int]:
    """解码 page token 并返回偏移量。

    解码流程:
        1. Base64 解码（捕获 binascii.Error / ValueError）
        2. UTF-8 解码（捕获 UnicodeDecodeError）
        3. JSON 解析外层结构体（捕获 json.JSONDecodeError）
        4. 验证结构体包含 payload 和 sig 字段
        5. HMAC-SHA256 签名验证（使用 hmac.compare_digest 防时序攻击）
        6. JSON 解析内层 payload
        7. offset 类型与范围校验（isinstance(offset, int) 且 offset >= 0）

    Args:
        token: Base64 编码的签名 token 字符串。

    Returns:
        偏移量整数，解码失败或签名不匹配时返回 None。
    """
    secret = _get_token_secret()

    # 步骤 1: Base64 解码
    try:
        raw_bytes = base64.urlsafe_b64decode(token.encode("ascii"))
    except (binascii.Error, ValueError):
        logger.warning("Invalid base64 page token")
        return None

    # 步骤 2: UTF-8 解码
    try:
        raw_str = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("Page token decode error (non-UTF8)")
        return None

    # 步骤 3: JSON 解析外层结构
    try:
        outer = json.loads(raw_str)
    except json.JSONDecodeError:
        logger.warning("Page token JSON parse error")
        return None

    # 步骤 4: 验证结构体字段
    if not isinstance(outer, dict):
        logger.warning("Page token structure is not a JSON object")
        return None

    payload = outer.get("payload")
    sig = outer.get("sig")

    if payload is None:
        logger.warning("Page token missing 'payload' field")
        return None

    if sig is None:
        logger.warning("Page token missing 'sig' field")
        return None

    # 步骤 5: HMAC 签名验证
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, sig):
        logger.warning("Page token signature mismatch")
        return None

    # 步骤 6: 解析内层 payload
    try:
        inner = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Page token payload JSON parse error")
        return None

    # 步骤 7: offset 类型与范围校验
    offset = inner.get("offset")

    if offset is None:
        logger.warning("Page token payload missing 'offset' key")
        return None

    if not isinstance(offset, int) or isinstance(offset, bool):
        logger.warning(
            f"Page token offset type error: expected int, got {type(offset).__name__}"
        )
        return None

    if offset < 0:
        logger.warning(f"Page token negative offset: {offset}")
        return None

    # 步骤 8: 过期检查（向后兼容：旧格式 token 无 exp 字段时跳过校验）
    exp = inner.get("exp")
    if exp is not None:
        if not isinstance(exp, (int, float)):
            logger.warning(
                f"Page token exp type error: expected int/float, got {type(exp).__name__}"
            )
            return None
        current_time = _get_current_timestamp()
        if exp <= current_time:
            logger.warning(f"Page token expired: exp={exp}, current={current_time}")
            return None

    return offset
