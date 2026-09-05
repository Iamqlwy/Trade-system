"""
JWT token creation/verification and password hashing.

⚠️ SECRET_KEY 必须通过环境变量 JWT_SECRET 设置，不提供默认值。
  生产环境使用硬编码密钥会导致 token 可被伪造。
⚠️ JWT exp 使用 timezone-aware UTC datetime，避免 Python 3.12+ 对
  datetime.utcnow() 的弃用警告和潜在的时间戳比对错误。
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

_secret = os.getenv("JWT_SECRET")
if not _secret:
    raise RuntimeError("JWT_SECRET environment variable must be set")

# 验证 JWT 密钥强度
if len(_secret) < 32:
    raise ValueError(
        f"JWT_SECRET 长度不足 ({len(_secret)} 字符)，最少需要 32 个字符。"
        "请设置一个强随机密钥，例如: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# 检测常见弱密钥模式 — 强制拒绝，防止生产环境使用弱密钥
_WEAK_PATTERNS = [
    "dev-secret", "change-in-production", "secret-key", "test-secret",
    "your-secret", "replace-me", "default-secret", "example-secret",
]
for _pattern in _WEAK_PATTERNS:
    if _pattern in _secret.lower():
        raise ValueError(
            f"JWT_SECRET 包含疑似弱密钥模式 '{_pattern}'，已被拒绝。"
            "请使用强随机密钥，例如: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

SECRET_KEY: str = _secret
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "sub": username,
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        logger.debug("Token 解码失败: %s", str(e))
        return None


# ── API Token（外部接入凭证）───────────────────────────────

API_TOKEN_PREFIX = "qt_"


def generate_api_token() -> str:
    """
    生成 API Token 明文。

    格式: qt_{32 hex chars}
    示例: qt_a3f1b2c4d5e6f789012345678abcdef0
    """
    return API_TOKEN_PREFIX + secrets.token_hex(16)


def hash_api_token(token: str) -> str:
    """对 API Token 明文做 SHA-256 哈希（数据库只存哈希值）。"""
    return hashlib.sha256(token.encode()).hexdigest()


def is_api_token(raw: str) -> bool:
    """判断原始 token 是否为 API Token（以 qt_ 开头）。"""
    return raw.startswith(API_TOKEN_PREFIX)


# ── Agent Session Token ──────────────────────────────────────

AGENT_SESSION_TOKEN_PREFIX = "ag_"


def is_agent_session_token(raw: str) -> bool:
    """判断原始 token 是否为 Agent Session Token（以 ag_ 开头）。"""
    return raw.startswith(AGENT_SESSION_TOKEN_PREFIX)


def resolve_api_token(token_hash: str) -> dict | None:
    """
    根据 token 哈希查询数据库，返回有效的 API Token 记录。

    返回 dict 包含: user_id, username, role, scope_type, scope_strategies,
                    permissions, rate_limit, token_db_id
    无效/过期/已禁用 → None
    """
    from ..dependencies import repository
    from .models import ApiToken, User

    session = repository.SessionLocal()
    try:
        row = session.query(ApiToken).filter_by(
            token_hash=token_hash, is_active=True,
        ).first()
        if row is None:
            return None

        # 检查过期
        if row.expires_at is not None:
            # expires_at 可能是 aware 或 naive datetime，统一处理
            exp = row.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                return None

        # 查询归属用户
        user = session.query(User).filter_by(id=row.user_id).first()
        if user is None:
            return None

        # 更新 last_used_at（异步友好，不做 commit，best-effort）
        row.last_used_at = datetime.now(timezone.utc)
        try:
            session.commit()
        except Exception:
            session.rollback()

        return {
            "sub": user.username,
            "user_id": user.id,
            "role": user.role,
            "api_token_id": row.id,
            "token_scope_type": row.scope_type,
            "token_scope_strategies": row.scope_strategies or [],
            "token_permissions": row.permissions or [],
            "token_rate_limit": row.rate_limit,
            "token_require_confirm": row.require_confirm,
        }
    finally:
        session.close()
