"""
FastAPI 权限依赖

在 API 端点层面执行权限检查，不通过则抛出 HTTP 403。
所有依赖内部复用 require_api_token 获取用户信息。
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request

from ..auth.dependencies import require_api_token
from ..dependencies import repository
from . import service

logger = logging.getLogger(__name__)


def _session():
    return repository.SessionLocal()


def get_accessible_strategy_ids(user: dict) -> Optional[set[str]]:
    """
    获取用户可访问的策略 ID 集合。
    供 router 内部使用（如列表端点过滤）。
    admin 返回 None 表示全部可访问。
    """
    session = _session()
    try:
        return service.get_accessible_strategy_ids(session, user)
    finally:
        session.close()


# ── 策略权限依赖 ──────────────────────────────────

async def require_strategy_access(request: Request) -> dict:
    """
    校验当前用户是否有权查看目标策略。
    从 request.path_params 提取 strategy_id。
    不通过 → HTTP 403。
    """
    user = await require_api_token(request)
    strategy_id = request.path_params.get("strategy_id", "")
    if not strategy_id:
        raise HTTPException(400, "缺少 strategy_id")

    session = _session()
    try:
        if not service.check_strategy_access(session, user, strategy_id):
            raise HTTPException(403, f"无权访问策略 {strategy_id}")
    finally:
        session.close()
    return user


async def require_strategy_trade(request: Request) -> dict:
    """
    校验当前用户是否有权交易（下单/撤单）。
    需要 strategy_users 中 can_trade=True。
    """
    user = await require_api_token(request)
    strategy_id = request.path_params.get("strategy_id", "")
    if not strategy_id:
        raise HTTPException(400, "缺少 strategy_id")

    session = _session()
    try:
        if not service.check_strategy_trade(session, user, strategy_id):
            raise HTTPException(403, f"无权交易策略 {strategy_id}")
    finally:
        session.close()
    return user


async def require_strategy_modify(request: Request) -> dict:
    """
    校验当前用户是否有权修改/删除策略。
    需要 strategy_users 中 can_trade=True（创建者身份）。
    """
    user = await require_api_token(request)
    strategy_id = request.path_params.get("strategy_id", "")
    if not strategy_id:
        raise HTTPException(400, "缺少 strategy_id")

    session = _session()
    try:
        if not service.check_strategy_modify(session, user, strategy_id):
            raise HTTPException(403, f"无权修改策略 {strategy_id}")
    finally:
        session.close()
    return user


# ── Admin 依赖 ────────────────────────────────────

async def require_admin_user(user: dict = Depends(require_api_token)) -> dict:
    """校验当前用户是否为管理员，非 admin → HTTP 403"""
    if user.get("role") != "admin":
        raise HTTPException(403, "仅管理员可执行此操作")
    return user


# ── 监控权限依赖 ──────────────────────────────────

async def require_monitor_access(request: Request) -> dict:
    """
    校验当前用户是否有权查看目标监控。
    需要先获取 monitor 的 owner_id，再调用 service 检查。
    注意：此依赖仅做认证，实际权限检查在 handler 中完成（需要 monitor 信息）。
    """
    user = await require_api_token(request)
    return user


async def require_monitor_modify(request: Request) -> dict:
    """
    校验当前用户是否有权修改目标监控。
    同 require_monitor_access，实际检查在 handler 中。
    """
    user = await require_api_token(request)
    return user


def check_monitor_permission(user: dict, owner_id: Optional[int], action: str = "访问") -> None:
    """
    同步检查监控权限，在 handler 内部调用。
    不通过 → HTTP 403。
    """
    if not service.check_monitor_access(user, owner_id):
        raise HTTPException(403, f"无权{action}此监控")
