"""监控 API 端点

REST: /api/monitors — CRUD、控制、日志、股票搜索、策略列表
WebSocket: /ws/monitor — 实时告警推送
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..auth.dependencies import require_api_token, require_monitor_access, get_user_permissions
from ..permissions.dependencies import check_monitor_permission
from .auth import verify_agent_token

logger = logging.getLogger(__name__)

monitor_router = APIRouter(prefix="/api", tags=["monitor"])


# ── Request 模型 ─────────────────────────────

class MonitorUpdateRequest(BaseModel):
    monitor_name: str | None = None
    description: str | None = None
    stock_codes: list[str] | None = None
    strategy_ids: list[str] | None = None
    interval: str | None = None
    trigger_mode: str | None = None
    enabled: bool | None = None
    cooldown_seconds: int | None = None
    params: dict | None = None


class MonitorUploadRequest(BaseModel):
    """Agent 上传监控 — 脚本保留在工作区，元信息写 DB"""
    monitor_name: str
    description: str = ""
    stock_codes: list[str] = []
    strategy_ids: list[str] = []
    interval: str = "30s"
    trigger_mode: str = "periodic"
    cooldown_seconds: int = 300
    script_metadata: dict = {}   # AI 生成的脚本元数据
    params: dict = {}            # 默认参数值
    script_path: str = "check.py"   # agent 工作区内的相对路径


# ── REST 端点 ────────────────────────────────

@monitor_router.post("/monitors/upload")
async def upload_monitor(
    req: MonitorUploadRequest,
    token: dict = Depends(verify_agent_token),
):
    """Agent 上传监控：脚本保留在工作区，只存 DB 元信息。"""
    # 权限检查
    perms = get_user_permissions({"user_id": token["user_id"], "role": ""})
    if not perms["can_use_monitor"]:
        raise HTTPException(403, "无监控任务权限")
    import random
    import string

    from ..agent.config import get_workspace_dir
    from ..dependencies import get_monitor_engine, repository
    from ..store.models import MonitorRecord

    session_id = token["session_id"]

    # 1. 验证脚本在工作区中存在
    workspace = get_workspace_dir(session_id)
    script_file = workspace / req.script_path
    if not script_file.exists():
        raise HTTPException(400, f"脚本文件不存在: {req.script_path}")

    # 2. 生成 monitor_id
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    monitor_id = f"m_{suffix}"

    # 3. 写入 DB（脚本保留在工作区，不拷贝）
    db_session = repository.SessionLocal()
    try:
        db_session.add(MonitorRecord(
            monitor_id=monitor_id,
            owner_id=token["user_id"],
            session_id=session_id,
            monitor_name=req.monitor_name,
            description=req.description,
            stock_codes=req.stock_codes,
            strategy_ids=req.strategy_ids,
            interval=req.interval,
            trigger_mode=req.trigger_mode,
            enabled=True,
            cooldown_seconds=req.cooldown_seconds,
            script_metadata=req.script_metadata,
            params=req.params,
            script_path=req.script_path,
        ))
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise HTTPException(500, "写入数据库失败")
    finally:
        db_session.close()

    # 4. 通知 engine 重新扫描
    engine = get_monitor_engine()
    engine._load_monitors()

    logger.info(
        "监控已创建: %s (owner=%s, session=%s, name=%s)",
        monitor_id, token["user_id"], session_id, req.monitor_name,
    )
    return {"monitor_id": monitor_id, "status": "created"}


@monitor_router.get("/monitors")
async def list_monitors(_user: dict = Depends(require_api_token)):
    from ..dependencies import get_monitor_engine
    return get_monitor_engine().list_monitors(user=_user)


@monitor_router.get("/monitors/logs")
async def get_monitor_logs(
    monitor_id: str | None = None,
    date: str | None = None,
    limit: int = 100,
    _user: dict = Depends(require_api_token),
):
    from datetime import date as date_type
    from sqlalchemy import func
    from ..dependencies import repository
    from ..store.models import MonitorAlertLog, MonitorRecord

    session = repository.SessionLocal()
    try:
        # 权限过滤：非 admin 只能看到自己创建的监控的日志
        if _user.get("role") != "admin":
            allowed_ids = [
                r.monitor_id for r in
                session.query(MonitorRecord.monitor_id)
                .filter(MonitorRecord.owner_id == _user["user_id"])
                .all()
            ]
            if not allowed_ids:
                return []
        else:
            allowed_ids = None  # admin 看全部

        q = session.query(MonitorAlertLog)

        if monitor_id:
            # 指定 monitor_id 时，额外校验是否属于当前用户
            if allowed_ids is not None and monitor_id not in allowed_ids:
                raise HTTPException(403, "无权查看此监控的日志")
            q = q.filter(MonitorAlertLog.monitor_id == monitor_id)
        elif allowed_ids is not None:
            q = q.filter(MonitorAlertLog.monitor_id.in_(allowed_ids))

        if date:
            try:
                target = date_type.fromisoformat(date)
            except ValueError:
                return []
            q = q.filter(func.date(MonitorAlertLog.triggered_at) == target)
        else:
            q = q.filter(func.date(MonitorAlertLog.triggered_at) == date_type.today())

        entries = (
            q.order_by(MonitorAlertLog.triggered_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "monitor_id": e.monitor_id,
                "monitor_name": e.monitor_name,
                "stock_code": e.stock_code,
                "triggered": not (isinstance(e.data, dict) and e.data.get("error")),
                "message": e.message,
                "data": e.data,
                "timestamp": e.triggered_at.isoformat(),
            }
            for e in entries
        ]
    finally:
        session.close()


@monitor_router.get("/monitors/stock-search")
async def stock_search(q: str = "", limit: int = 20, _user: dict = Depends(require_api_token)):
    """股票搜索（支持中文名/代码/拼音，从 C:/klines/stock_basic.csv）"""
    from .engine import search_stocks
    return search_stocks(q, limit=limit)


@monitor_router.get("/monitors/strategies")
async def get_strategies_for_monitor(_user: dict = Depends(require_api_token)):
    """获取当前用户有权限的策略列表（供前端选择策略持仓监控）"""
    from ..dependencies import strategy_manager, repository
    from ..permissions.service import get_accessible_strategy_ids

    session = repository.SessionLocal()
    try:
        accessible_ids = get_accessible_strategy_ids(session, _user)
    finally:
        session.close()

    result = []
    for sid, strategy in strategy_manager.items():
        # admin 看全部（accessible_ids=None），普通用户过滤
        if accessible_ids is not None and sid not in accessible_ids:
            continue
        result.append({
            "strategy_id": sid,
            "name": getattr(strategy, "name", sid),
            "position_count": len(strategy.positions),
            "position_codes": list(strategy.positions.keys()),
        })
    return result


@monitor_router.get("/monitors/{monitor_id}")
async def get_monitor(monitor_id: str, _user: dict = Depends(require_api_token)):
    from ..dependencies import get_monitor_engine
    engine = get_monitor_engine()
    info = engine._monitors.get(monitor_id)
    if not info:
        raise HTTPException(404, f"监控 {monitor_id} 不存在")
    check_monitor_permission(_user, info.owner_id, "访问")
    return engine.get_monitor(monitor_id)


@monitor_router.put("/monitors/{monitor_id}")
async def update_monitor(
    monitor_id: str,
    req: MonitorUpdateRequest,
    _user: dict = Depends(require_api_token),
):
    from ..dependencies import get_monitor_engine
    engine = get_monitor_engine()
    info = engine._monitors.get(monitor_id)
    if not info:
        raise HTTPException(404, f"监控 {monitor_id} 不存在")
    check_monitor_permission(_user, info.owner_id, "修改")

    updates = req.model_dump(exclude_none=True)
    result = engine.update_monitor(monitor_id, updates)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@monitor_router.delete("/monitors/{monitor_id}")
async def delete_monitor(monitor_id: str, _user: dict = Depends(require_api_token)):
    from ..dependencies import get_monitor_engine
    engine = get_monitor_engine()
    info = engine._monitors.get(monitor_id)
    if not info:
        raise HTTPException(404, f"监控 {monitor_id} 不存在")
    check_monitor_permission(_user, info.owner_id, "删除")

    result = engine.delete_monitor(monitor_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@monitor_router.post("/monitors/{monitor_id}/toggle")
async def toggle_monitor(monitor_id: str, _user: dict = Depends(require_api_token)):
    from ..dependencies import get_monitor_engine
    engine = get_monitor_engine()
    info = engine._monitors.get(monitor_id)
    if not info:
        raise HTTPException(404, f"监控 {monitor_id} 不存在")
    check_monitor_permission(_user, info.owner_id, "控制")

    result = engine.toggle(monitor_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@monitor_router.post("/monitors/{monitor_id}/run")
async def run_monitor(monitor_id: str, _user: dict = Depends(require_monitor_access)):
    from ..dependencies import get_monitor_engine
    engine = get_monitor_engine()
    info = engine._monitors.get(monitor_id)
    if not info:
        raise HTTPException(404, f"监控 {monitor_id} 不存在")
    check_monitor_permission(_user, info.owner_id, "执行")

    result = await engine.run_now(monitor_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


# ── WebSocket ────────────────────────────────

monitor_ws_router = APIRouter()

# 每用户最大 monitor WS 连接数
_MAX_MONITOR_WS_PER_USER = 3
_monitor_ws_count: dict[int, int] = {}


@monitor_ws_router.websocket("/ws/monitor")
async def monitor_alert_websocket(ws: WebSocket):
    from ..auth.security import decode_token

    # 鉴权：优先 httponly cookie，回退到 query param（?token= 会被记录到访问日志，仅作为兼容方案）
    from ..auth.security import decode_token

    token = ws.cookies.get("access_token", "") or ws.query_params.get("token", "")
    payload = decode_token(token) if token else None
    if payload is None:
        await ws.close(code=4001, reason="Authentication required")
        return

    user_id: int = payload.get("user_id", 0)
    username: str = payload.get("sub", "")
    role: str = payload.get("role", "")

    # 连接数限制
    current_count = _monitor_ws_count.get(user_id, 0)
    if current_count >= _MAX_MONITOR_WS_PER_USER:
        logger.warning(
            "Monitor WS 连接超限: user=%d count=%d limit=%d",
            user_id, current_count, _MAX_MONITOR_WS_PER_USER,
        )
        await ws.close(code=4003, reason="Too many connections")
        return

    _monitor_ws_count[user_id] = current_count + 1
    await ws.accept()

    from ..dependencies import get_monitor_engine
    from ..services.connection_registry import connection_registry
    engine = get_monitor_engine()
    engine.add_alert_subscriber(ws)
    connection_registry.register(user_id, username, role)

    logger.info("Monitor WS connected: user=%s (connections: %d)", username, current_count + 1)

    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Monitor WS error")
    finally:
        engine.remove_alert_subscriber(ws)
        _monitor_ws_count[user_id] = max(0, _monitor_ws_count.get(user_id, 1) - 1)
        if _monitor_ws_count[user_id] == 0:
            del _monitor_ws_count[user_id]
        from ..services.connection_registry import connection_registry
        connection_registry.unregister(user_id)
