"""
安全工具模块

该模块提供 Admin UI 认证所需的安全工具函数，包括：
- bcrypt 密码哈希与验证
- JWT Token 签发与解码

密码使用 bcrypt (cost=12) 进行哈希，永不明文存储。
JWT 使用 python-jose 库进行签发和验证，签名密钥从配置读取。
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any

import bcrypt
from jose import jwt, JWTError, ExpiredSignatureError
from loguru import logger

from app.core.config import get_config

# bcrypt 哈希轮数（cost factor），12 轮提供足够安全性且性能合理
_BCRYPT_ROUNDS = 12

# JWT 算法：HS256 对称签名
_JWT_ALGORITHM = "HS256"

# JWT 有效期：8 小时（秒）
_JWT_EXPIRATION_SECONDS = 8 * 60 * 60


def hash_password(password: str) -> str:
    """使用 bcrypt 对密码进行哈希。

    对明文密码使用 bcrypt 进行单向哈希处理。
    哈希结果可直接存入数据库 password_hash 字段。
    返回字符串以便直接存入数据库 TEXT 列。

    Args:
        password: 明文密码字符串。

    Returns:
        bcrypt 哈希字符串，格式为 $2b$12$...。
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码是否与 bcrypt 哈希匹配。

    Args:
        plain_password: 用户输入的明文密码。
        hashed_password: 数据库中存储的 bcrypt 哈希值。

    Returns:
        密码匹配返回 True，否则返回 False。
    """
    plain_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(plain_bytes, hashed_bytes)


def _get_jwt_secret() -> str:
    """获取 JWT 签名密钥。

    优先级：config.yaml admin.jwt_secret > 环境变量 JWT_SECRET > 随机生成。
    随机生成时记录 Warning 日志，提醒生产环境应配置固定密钥。

    Returns:
        JWT 签名密钥字符串。
    """
    config = get_config()
    secret = (config.admin.jwt_secret or "").strip()

    if secret:
        return secret

    # 未配置时生成随机密钥，仅当前进程生命周期有效
    import secrets

    random_secret = secrets.token_hex(32)
    logger.warning(
        "JWT_SECRET 未配置，已生成随机临时密钥。"
        "生产环境请通过环境变量 JWT_SECRET 或 config.yaml 中的 admin.jwt_secret "
        "配置固定密钥，否则每次重启服务后所有已签发的 JWT Token 将失效"
    )
    return random_secret


def create_admin_token(admin_id: str) -> str:
    """为管理员签发 JWT Token。

    生成的 JWT 包含以下声明（claims）：
    - sub: 管理员 ID（admin_id）
    - iat: 签发时间（Unix 时间戳）
    - exp: 过期时间（签发时间 + 8 小时）

    Args:
        admin_id: 管理员的唯一标识符（UUID）。

    Returns:
        签发的 JWT 字符串（Bearer Token）。
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": admin_id,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + _JWT_EXPIRATION_SECONDS,
    }

    secret = _get_jwt_secret()
    token = jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)
    return token


def decode_admin_token(token: str) -> Optional[Dict[str, Any]]:
    """解码并验证 JWT Token。

    验证 Token 的签名和有效期。如果 Token 有效，
    返回其中包含的 payload 字典；否则返回 None。

    Args:
        token: JWT 字符串。

    Returns:
        成功时返回包含 sub/iat/exp 的字典，失败返回 None。
    """
    secret = _get_jwt_secret()

    try:
        payload = jwt.decode(token, secret, algorithms=[_JWT_ALGORITHM])
        return payload
    except ExpiredSignatureError:
        logger.debug("JWT Token 已过期")
        return None
    except JWTError as e:
        logger.debug(f"JWT Token 验证失败: {e}")
        return None
