"""
FastAPI dependencies for authentication.
"""
import logging
from typing import Optional

from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse

from .security import decode_token, is_api_token, hash_api_token, resolve_api_token
from ..dependencies import repository

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> Optional[dict]:
    """Extract user from session cookie (for web pages). Returns None if not logged in."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if payload is None:
        logger.warning("认证失败: token 无效或已过期 (path=%s)", request.url.path)
        return None
    return payload


async def require_login(request: Request):
    """Dependency: redirect to /login if not authenticated."""
    user = await get_current_user(request)
    if user is None:
        return RedirectResponse("/login?next=" + request.url.path, status_code=302)
    request.state.user = user
    return user


async def require_admin(request: Request):
    """Dependency: require admin role."""
    user = await require_login(request)
    if isinstance(user, RedirectResponse):
        return user
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user


async def can_access_strategy(request: Request, strategy_id: str) -> bool:
    """Check if current user can view a strategy."""
    user = await get_current_user(request)
    if user is None:
        return False
    if user.get("role") == "admin":
        return True
    session = repository.SessionLocal()
    try:
        from .models import StrategyUser
        row = session.query(StrategyUser).filter_by(
            user_id=user["user_id"], strategy_id=strategy_id
        ).first()
        return row is not None
    finally:
        session.close()


async def can_trade_strategy(request: Request, strategy_id: str) -> bool:
    """Check if current user can trade on a strategy."""
    user = await get_current_user(request)
    if user is None:
        return False
    if user.get("role") == "admin":
        return True
    session = repository.SessionLocal()
    try:
        from .models import StrategyUser
        row = session.query(StrategyUser).filter_by(
            user_id=user["user_id"], strategy_id=strategy_id, can_trade=True
        ).first()
        return row is not None
    finally:
        session.close()


async def require_api_token(request: Request):
    """Dependency for API routes: Bearer token auth.

    全局 auth_middleware 已通过验证并设置 request.state.user，
    此处直接返回即可；若 middleware 被绕过（如测试场景），则回退到自行验证。
    """
    # 快速路径：middleware 已完成验证
    user = getattr(request.state, "user", None)
    if user is not None:
        return user

    # 回退：middleware 未生效时自行验证
    # 尝试 X-API-Token header 或 Authorization header
    api_token_raw = request.headers.get("X-API-Token")
    auth_header = request.headers.get("Authorization", "")

    if api_token_raw:
        # API Token 路径
        if not is_api_token(api_token_raw):
            logger.warning("API 认证失败: 非 API Token 格式 (path=%s)", request.url.path)
            raise HTTPException(401, "Invalid API token format")
        token_hash = hash_api_token(api_token_raw)
        token_info = resolve_api_token(token_hash)
        if token_info is None:
            logger.warning("API 认证失败: API Token 无效 (path=%s)", request.url.path)
            raise HTTPException(401, "Invalid API token")
        request.state.user = token_info
        return token_info

    if auth_header.startswith("Bearer "):
        raw = auth_header[7:]
        if is_api_token(raw):
            # Bearer 传递的也是 API Token
            token_hash = hash_api_token(raw)
            token_info = resolve_api_token(token_hash)
            if token_info is None:
                logger.warning("API 认证失败: API Token 无效 (path=%s)", request.url.path)
                raise HTTPException(401, "Invalid API token")
            request.state.user = token_info
            return token_info
        else:
            # JWT 路径
            payload = decode_token(raw)
            if payload is None:
                logger.warning("API 认证失败: token 无效或已过期 (path=%s)", request.url.path)
                raise HTTPException(401, "Invalid token")
            request.state.user = payload
            return payload

    logger.warning("API 认证失败: 缺少 Bearer token (path=%s)", request.url.path)
    raise HTTPException(401, "Missing token")


# ── 精细化权限 ──────────────────────────────────

def get_user_permissions(user: dict) -> dict:
    """查询用户的全部功能权限字段（合并组权限 + 个人覆盖）。admin 直接返回全 True / -1。"""
    if user.get("role") == "admin":
        return {
            "can_use_agent": True,
            "can_create_real": True,
            "max_strategies": -1,
            "can_use_cron": True,
            "can_use_monitor": True,
        }
    from ..permissions.service import get_effective_feature_permissions
    session = repository.SessionLocal()
    try:
        return get_effective_feature_permissions(session, user)
    finally:
        session.close()


async def require_agent_access(user: dict = Depends(require_api_token)) -> dict:
    """依赖：要求用户可以使用 Agent。"""
    perms = get_user_permissions(user)
    if not perms["can_use_agent"]:
        raise HTTPException(403, "无 Agent 使用权限")
    return user


async def require_cron_access(user: dict = Depends(require_api_token)) -> dict:
    """依赖：要求用户可以使用定时任务。"""
    perms = get_user_permissions(user)
    if not perms["can_use_cron"]:
        raise HTTPException(403, "无定时任务权限")
    return user


async def require_monitor_access(user: dict = Depends(require_api_token)) -> dict:
    """依赖：要求用户可以创建/运行监控任务。"""
    perms = get_user_permissions(user)
    if not perms["can_use_monitor"]:
        raise HTTPException(403, "无监控任务权限")
    return user
