"""
密码哈希与 JWT 工具函数

使用 bcrypt 进行密码哈希，HS256 进行 JWT 签名。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from core.config import settings


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希

    Args:
        password: 明文密码

    Returns:
        str: bcrypt 哈希字符串
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配

    Args:
        plain_password: 明文密码
        hashed_password: bcrypt 哈希字符串

    Returns:
        bool: 是否匹配
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(user_id: str, username: str) -> str:
    """创建 JWT 访问令牌

    Args:
        user_id: 用户 UUID
        username: 用户名

    Returns:
        str: 编码后的 JWT 字符串
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )
    payload = {
        "sub": user_id,
        "username": username,
        "exp": expire,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> Optional[dict]:
    """解码并验证 JWT 令牌

    Args:
        token: JWT 字符串

    Returns:
        Optional[dict]: 解码后的 payload（含 user_id, username），验证失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None