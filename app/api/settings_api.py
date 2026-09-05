"""
Settings API — 用户管理 + 策略权限管理（仅管理员）

前端 SettingsView.vue 已对接这些端点。
"""

import logging

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.models import User, StrategyUser
from ..auth.security import hash_password
from ..dependencies import repository
from ..permissions.dependencies import require_admin_user
from ..permissions.service import (
    grant_strategy_access,
    revoke_strategy_access,
    ALL_TOOLS,
    set_tool_permission,
    get_all_tool_permissions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ── 工具定义（中文标签） ────────────────────────────

TOOL_LABELS: dict[str, str] = {
    "shell": "Shell",
    "file_read": "文件读",
    "file_write": "文件写",
    "file_search": "文件搜索",
    "web_search": "Web搜索",
    "web_fetch": "Web抓取",
    "cronjob": "定时任务",
    "agent": "子Agent",
    "strategy_view": "策略持仓",
}


def _session() -> Session:
    return repository.SessionLocal()


# ── Request 模型 ──────────────────────────────────

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    can_use_agent: bool = True
    can_create_real: bool = True
    max_strategies: int = 10
    can_use_cron: bool = True
    can_use_monitor: bool = True


class UpdateUserPermissionsRequest(BaseModel):
    can_use_agent: Optional[bool] = None
    can_create_real: Optional[bool] = None
    max_strategies: Optional[int] = None
    can_use_cron: Optional[bool] = None
    can_use_monitor: Optional[bool] = None


class GrantPermissionRequest(BaseModel):
    username: str
    strategyId: str
    canTrade: bool = True


class RevokePermissionRequest(BaseModel):
    username: str
    strategyId: str


class SetToolPermissionRequest(BaseModel):
    username: str
    toolKey: str
    enabled: bool


# ── 用户管理 ──────────────────────────────────────

@router.get("/users")
async def list_users(_admin: dict = Depends(require_admin_user)):
    """列出所有用户"""
    session = _session()
    try:
        rows = session.query(User).all()
        return [
            {
                "id": r.id,
                "username": r.username,
                "role": r.role,
                "can_use_agent": r.can_use_agent if r.can_use_agent is not None else True,
                "can_create_real": r.can_create_real if r.can_create_real is not None else True,
                "max_strategies": r.max_strategies if r.max_strategies is not None else 10,
                "can_use_cron": r.can_use_cron if r.can_use_cron is not None else True,
                "can_use_monitor": r.can_use_monitor if r.can_use_monitor is not None else True,
            }
            for r in rows
        ]
    finally:
        session.close()


@router.post("/users")
async def create_user(req: CreateUserRequest, _admin: dict = Depends(require_admin_user)):
    """管理员创建新用户"""
    session = _session()
    try:
        existing = session.query(User).filter_by(username=req.username).first()
        if existing:
            raise HTTPException(400, "用户名已存在")

        if req.role not in ("admin", "trader", "viewer"):
            raise HTTPException(400, f"无效角色: {req.role}")

        user = User(
            username=req.username,
            password_hash=hash_password(req.password),
            role=req.role,
            can_use_agent=req.can_use_agent,
            can_create_real=req.can_create_real,
            max_strategies=req.max_strategies,
            can_use_cron=req.can_use_cron,
            can_use_monitor=req.can_use_monitor,
        )
        session.add(user)
        session.commit()
        logger.info("管理员 %s 创建用户: %s (role=%s)", _admin["sub"], req.username, req.role)
        return {"success": True, "message": f"用户 {req.username} 创建成功"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("创建用户失败")
        raise HTTPException(400, f"创建失败: {e}")
    finally:
        session.close()


@router.put("/users/{username}/permissions")
async def update_user_permissions(
    username: str,
    req: UpdateUserPermissionsRequest,
    _admin: dict = Depends(require_admin_user),
):
    """管理员设置用户的功能权限（Agent / 实盘 / 策略上限 / 定时任务 / 监控）"""
    session = _session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            raise HTTPException(404, f"用户 {username} 不存在")

        changes = []
        if req.can_use_agent is not None:
            user.can_use_agent = req.can_use_agent
            changes.append(f"can_use_agent={req.can_use_agent}")
        if req.can_create_real is not None:
            user.can_create_real = req.can_create_real
            changes.append(f"can_create_real={req.can_create_real}")
        if req.max_strategies is not None:
            user.max_strategies = req.max_strategies
            changes.append(f"max_strategies={req.max_strategies}")
        if req.can_use_cron is not None:
            user.can_use_cron = req.can_use_cron
            changes.append(f"can_use_cron={req.can_use_cron}")
        if req.can_use_monitor is not None:
            user.can_use_monitor = req.can_use_monitor
            changes.append(f"can_use_monitor={req.can_use_monitor}")

        if not changes:
            raise HTTPException(400, "未提供需要更新的权限字段")

        session.commit()
        logger.info(
            "管理员 %s 更新用户权限: %s (%s)",
            _admin["sub"], username, ", ".join(changes),
        )
        return {"success": True, "message": f"用户 {username} 权限已更新"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("更新用户权限失败")
        raise HTTPException(400, f"更新失败: {e}")
    finally:
        session.close()


# ── 策略权限管理 ──────────────────────────────────

@router.get("/permissions")
async def list_permissions(_admin: dict = Depends(require_admin_user)):
    """列出所有策略权限分配"""
    from ..store.models import Strategys

    session = _session()
    try:
        rows = session.query(StrategyUser, User.username, Strategys.name).join(
            User, StrategyUser.user_id == User.id,
        ).join(
            Strategys, StrategyUser.strategy_id == Strategys.strategy_id,
        ).all()
        return [
            {
                "username": username,
                "strategy_id": su.strategy_id,
                "strategy_name": name,
                "can_trade": su.can_trade,
            }
            for su, username, name in rows
        ]
    finally:
        session.close()


@router.post("/permissions")
async def grant_permission(req: GrantPermissionRequest, _admin: dict = Depends(require_admin_user)):
    """授权用户对策略的访问权限"""
    session = _session()
    try:
        # 查找用户
        user = session.query(User).filter_by(username=req.username).first()
        if not user:
            raise HTTPException(404, f"用户 {req.username} 不存在")

        # 检查策略是否存在
        from ..store.models import Strategys
        strategy = session.query(Strategys).filter_by(
            strategy_id=req.strategyId, is_deleted=0,
        ).first()
        if not strategy:
            raise HTTPException(404, f"策略 {req.strategyId} 不存在")

        grant_strategy_access(session, user.id, req.strategyId, req.canTrade)
        session.commit()

        logger.info(
            "管理员 %s 授权: user=%s strategy=%s can_trade=%s",
            _admin["sub"], req.username, req.strategyId, req.canTrade,
        )
        return {"success": True, "message": "授权成功"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("授权失败")
        raise HTTPException(400, f"授权失败: {e}")
    finally:
        session.close()


@router.delete("/permissions")
async def revoke_permission(req: RevokePermissionRequest, _admin: dict = Depends(require_admin_user)):
    """撤销用户对策略的访问权限"""
    session = _session()
    try:
        user = session.query(User).filter_by(username=req.username).first()
        if not user:
            raise HTTPException(404, f"用户 {req.username} 不存在")

        revoke_strategy_access(session, user.id, req.strategyId)
        session.commit()

        logger.info(
            "管理员 %s 撤销权限: user=%s strategy=%s",
            _admin["sub"], req.username, req.strategyId,
        )
        return {"success": True, "message": "权限已撤销"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("撤销权限失败")
        raise HTTPException(400, f"撤销失败: {e}")
    finally:
        session.close()


# ── 工具权限管理 ──────────────────────────────────

@router.get("/tools")
async def list_tools(_admin: dict = Depends(require_admin_user)):
    """返回系统可用工具列表（含中文标签），供前端动态渲染"""
    return [
        {"key": key, "label": TOOL_LABELS.get(key, key)}
        for key in ALL_TOOLS
    ]

@router.get("/tool-permissions")
async def list_tool_permissions(_admin: dict = Depends(require_admin_user)):
    """列出所有用户的工具权限"""
    session = _session()
    try:
        return get_all_tool_permissions(session)
    finally:
        session.close()


@router.post("/tool-permissions")
async def set_tool_perm(req: SetToolPermissionRequest, _admin: dict = Depends(require_admin_user)):
    """设置用户的工具权限"""
    if req.toolKey not in ALL_TOOLS:
        raise HTTPException(400, f"无效工具: {req.toolKey}，可选: {ALL_TOOLS}")

    session = _session()
    try:
        user = session.query(User).filter_by(username=req.username).first()
        if not user:
            raise HTTPException(404, f"用户 {req.username} 不存在")

        set_tool_permission(session, user.id, req.toolKey, req.enabled)
        session.commit()

        status = "启用" if req.enabled else "禁用"
        logger.info(
            "管理员 %s %s工具: user=%s tool=%s",
            _admin["sub"], status, req.username, req.toolKey,
        )
        return {"success": True, "message": f"已{status} {req.username} 的 {req.toolKey}"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("设置工具权限失败")
        raise HTTPException(400, f"设置失败: {e}")
    finally:
        session.close()


# ── 反馈管理 ──────────────────────────────────

class ReplyFeedbackRequest(BaseModel):
    status: Optional[str] = None  # pending / in_progress / resolved / closed
    admin_reply: Optional[str] = None


@router.get("/feedback")
async def list_feedback(
    status: str | None = None,
    _admin: dict = Depends(require_admin_user),
):
    """列出全部用户反馈（可按 status 筛选）"""
    from ..store.models import Feedback

    session = _session()
    try:
        q = session.query(Feedback).order_by(Feedback.created_at.desc())
        if status:
            q = q.filter_by(status=status)
        rows = q.all()

        # 批量查询用户名
        user_ids = set()
        for r in rows:
            user_ids.add(r.user_id)
            if r.replied_by:
                user_ids.add(r.replied_by)
        user_map = {}
        if user_ids:
            for u in session.query(User).filter(User.id.in_(user_ids)).all():
                user_map[u.id] = u.username

        result = []
        for r in rows:
            result.append({
                "id": r.id,
                "user_id": r.user_id,
                "username": user_map.get(r.user_id, "unknown"),
                "type": r.type,
                "title": r.title,
                "content": r.content,
                "status": r.status,
                "admin_reply": r.admin_reply,
                "replied_by": r.replied_by,
                "replied_by_name": user_map.get(r.replied_by) if r.replied_by else None,
                "replied_at": r.replied_at.isoformat() if r.replied_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return result
    finally:
        session.close()


@router.get("/feedback/count")
async def feedback_count(_admin: dict = Depends(require_admin_user)):
    """各状态反馈数量"""
    from ..store.models import Feedback
    from sqlalchemy import func

    session = _session()
    try:
        rows = session.query(Feedback.status, func.count(Feedback.id)).group_by(Feedback.status).all()
        counts = {status: count for status, count in rows}
        return {
            "total": sum(counts.values()),
            "pending": counts.get("pending", 0),
            "in_progress": counts.get("in_progress", 0),
            "resolved": counts.get("resolved", 0),
            "closed": counts.get("closed", 0),
        }
    finally:
        session.close()


@router.put("/feedback/{feedback_id}")
async def reply_feedback(
    feedback_id: int,
    req: ReplyFeedbackRequest,
    admin: dict = Depends(require_admin_user),
):
    """管理员回复/更新反馈状态"""
    from ..store.models import Feedback

    if req.status and req.status not in ("pending", "in_progress", "resolved", "closed"):
        raise HTTPException(400, "无效的状态值")

    session = _session()
    try:
        fb = session.query(Feedback).filter_by(id=feedback_id).first()
        if not fb:
            raise HTTPException(404, "反馈不存在")

        if req.status is not None:
            fb.status = req.status
        if req.admin_reply is not None:
            fb.admin_reply = req.admin_reply.strip()
            fb.replied_by = admin["user_id"]
            from datetime import datetime
            fb.replied_at = datetime.now()

        session.commit()
        logger.info("管理员 %s 回复反馈 #%d", admin["sub"], feedback_id)
        return {"success": True, "message": "反馈已更新"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("回复反馈失败")
        raise HTTPException(400, f"更新失败: {e}")
    finally:
        session.close()


