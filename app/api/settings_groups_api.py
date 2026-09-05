"""
用户组管理 API（仅管理员）

提供用户组 CRUD、成员管理、组权限（功能/策略/工具）设置。
这些端点挂载在与 settings_api.py 共享的 router 上（prefix=/api/settings）。
"""
import logging

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.models import User, UserGroup, UserGroupMember, \
    UserGroupPermission, UserGroupStrategyPermission, UserGroupToolPermission
from ..dependencies import repository
from ..permissions.dependencies import require_admin_user
from ..permissions.service import ALL_TOOLS

# 复用 settings_api.py 的 router 对象和 _session 工厂函数
from .settings_api import router, _session as _session

# 导入 Pydantic 请求模型
from ..models.requests import (
    CreateGroupRequest,
    UpdateGroupRequest,
    AddGroupMembersRequest,
    SetGroupPermissionsRequest,
    SetGroupStrategyPermissionRequest,
    SetGroupToolPermissionRequest,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# ── 用户组管理 ──────────────────────────────────────────
# ═══════════════════════════════════════════════════════════

@router.get("/groups")
async def list_groups(_admin: dict = Depends(require_admin_user)):
    """列出所有用户组（含成员数）"""
    session = _session()
    try:
        groups = session.query(UserGroup).all()
        result = []
        for g in groups:
            member_count = session.query(UserGroupMember).filter_by(group_id=g.id).count()
            result.append({
                "id": g.id,
                "name": g.name,
                "description": g.description or "",
                "member_count": member_count,
                "created_at": g.created_at.isoformat() if g.created_at else "",
            })
        return result
    finally:
        session.close()


@router.post("/groups")
async def create_group(
    req: "CreateGroupRequest",
    admin: dict = Depends(require_admin_user),
):
    """创建用户组"""
    session = _session()
    try:
        group = UserGroup(
            name=req.name,
            description=req.description or "",
            created_by=admin["user_id"],
        )
        session.add(group)
        session.flush()

        perm = UserGroupPermission(group_id=group.id)
        session.add(perm)
        session.commit()

        logger.info("管理员 %s 创建用户组: %s (id=%d)", admin["sub"], req.name, group.id)
        return {"id": group.id, "message": "组已创建"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"创建失败: {e}")
    finally:
        session.close()


@router.get("/groups/{group_id}")
async def get_group_detail(
    group_id: int,
    _admin: dict = Depends(require_admin_user),
):
    """获取组详情（成员、权限）"""
    from ..store.models import Strategys

    session = _session()
    try:
        group = session.query(UserGroup).filter_by(id=group_id).first()
        if not group:
            raise HTTPException(404, "用户组不存在")

        members = []
        for m in group.members:
            u = session.query(User).filter_by(id=m.user_id).first()
            if u:
                members.append({
                    "user_id": u.id,
                    "username": u.username,
                    "role": u.role,
                })

        perm = group.permissions
        permissions = {
            "can_use_agent": perm.can_use_agent if perm else True,
            "can_create_real": perm.can_create_real if perm else True,
            "max_strategies": perm.max_strategies if perm else 10,
            "can_use_cron": perm.can_use_cron if perm else True,
            "can_use_monitor": perm.can_use_monitor if perm else True,
        } if perm else None

        sp_list = []
        for sp in group.strategy_permissions:
            strat = session.query(Strategys).filter_by(
                strategy_id=sp.strategy_id, is_deleted=0,
            ).first()
            sp_list.append({
                "strategy_id": sp.strategy_id,
                "strategy_name": strat.name if strat else sp.strategy_id,
                "can_trade": sp.can_trade,
            })

        tp_list = []
        for tp in group.tool_permissions:
            tp_list.append({
                "tool_key": tp.tool_key,
                "enabled": tp.enabled,
            })

        return {
            "id": group.id,
            "name": group.name,
            "description": group.description or "",
            "members": members,
            "permissions": permissions,
            "strategy_permissions": sp_list,
            "tool_permissions": tp_list,
        }
    except HTTPException:
        raise
    finally:
        session.close()


@router.put("/groups/{group_id}")
async def update_group(
    group_id: int,
    req: "UpdateGroupRequest",
    admin: dict = Depends(require_admin_user),
):
    """更新组名称/描述"""
    session = _session()
    try:
        group = session.query(UserGroup).filter_by(id=group_id).first()
        if not group:
            raise HTTPException(404, "用户组不存在")

        if req.name is not None:
            group.name = req.name
        if req.description is not None:
            group.description = req.description

        session.commit()
        logger.info("管理员 %s 更新用户组: id=%d", admin["sub"], group_id)
        return {"success": True, "message": "组已更新"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"更新失败: {e}")
    finally:
        session.close()


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    admin: dict = Depends(require_admin_user),
):
    """删除用户组"""
    session = _session()
    try:
        group = session.query(UserGroup).filter_by(id=group_id).first()
        if not group:
            raise HTTPException(404, "用户组不存在")

        session.delete(group)
        session.commit()
        logger.info("管理员 %s 删除用户组: id=%d", admin["sub"], group_id)
        return {"success": True, "message": "组已删除"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"删除失败: {e}")
    finally:
        session.close()


@router.post("/groups/{group_id}/members")
async def add_group_members(
    group_id: int,
    req: "AddGroupMembersRequest",
    admin: dict = Depends(require_admin_user),
):
    """向组添加成员"""
    session = _session()
    try:
        group = session.query(UserGroup).filter_by(id=group_id).first()
        if not group:
            raise HTTPException(404, "用户组不存在")

        added = 0
        for uid in req.user_ids:
            existing = session.query(UserGroupMember).filter_by(
                group_id=group_id, user_id=uid,
            ).first()
            if not existing:
                u = session.query(User).filter_by(id=uid).first()
                if u:
                    session.add(UserGroupMember(group_id=group_id, user_id=uid))
                    added += 1

        session.commit()
        logger.info("管理员 %s 向组 %d 添加 %d 个成员", admin["sub"], group_id, added)
        return {"success": True, "added": added}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"添加失败: {e}")
    finally:
        session.close()


@router.delete("/groups/{group_id}/members/{user_id}")
async def remove_group_member(
    group_id: int,
    user_id: int,
    admin: dict = Depends(require_admin_user),
):
    """从组移除成员"""
    session = _session()
    try:
        row = session.query(UserGroupMember).filter_by(
            group_id=group_id, user_id=user_id,
        ).first()
        if not row:
            raise HTTPException(404, "该成员不在此组中")

        session.delete(row)
        session.commit()
        logger.info("管理员 %s 从组 %d 移除成员 %d", admin["sub"], group_id, user_id)
        return {"success": True, "message": "成员已移除"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"移除失败: {e}")
    finally:
        session.close()


@router.put("/groups/{group_id}/permissions")
async def set_group_permissions(
    group_id: int,
    req: "SetGroupPermissionsRequest",
    admin: dict = Depends(require_admin_user),
):
    """设置组的功能权限"""
    session = _session()
    try:
        perm = session.query(UserGroupPermission).filter_by(group_id=group_id).first()
        if not perm:
            perm = UserGroupPermission(group_id=group_id)
            session.add(perm)

        if req.can_use_agent is not None:
            perm.can_use_agent = req.can_use_agent
        if req.can_create_real is not None:
            perm.can_create_real = req.can_create_real
        if req.max_strategies is not None:
            perm.max_strategies = req.max_strategies
        if req.can_use_cron is not None:
            perm.can_use_cron = req.can_use_cron
        if req.can_use_monitor is not None:
            perm.can_use_monitor = req.can_use_monitor

        session.commit()
        logger.info("管理员 %s 设置组 %d 权限", admin["sub"], group_id)
        return {"success": True, "message": "权限已保存"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"设置失败: {e}")
    finally:
        session.close()


@router.post("/groups/{group_id}/strategy-permissions")
async def set_group_strategy_permission(
    group_id: int,
    req: "SetGroupStrategyPermissionRequest",
    admin: dict = Depends(require_admin_user),
):
    """设置组的策略访问权限"""
    session = _session()
    try:
        from ..store.models import Strategys

        strat = session.query(Strategys).filter_by(
            strategy_id=req.strategy_id, is_deleted=0,
        ).first()
        if not strat:
            raise HTTPException(404, f"策略 {req.strategy_id} 不存在")

        row = session.query(UserGroupStrategyPermission).filter_by(
            group_id=group_id, strategy_id=req.strategy_id,
        ).first()
        if row:
            row.can_trade = req.can_trade
        else:
            session.add(UserGroupStrategyPermission(
                group_id=group_id, strategy_id=req.strategy_id, can_trade=req.can_trade,
            ))

        session.commit()
        return {"success": True, "message": "策略权限已保存"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"设置失败: {e}")
    finally:
        session.close()


@router.delete("/groups/{group_id}/strategy-permissions/{strategy_id}")
async def delete_group_strategy_permission(
    group_id: int,
    strategy_id: str,
    admin: dict = Depends(require_admin_user),
):
    """移除组的策略访问权限"""
    session = _session()
    try:
        row = session.query(UserGroupStrategyPermission).filter_by(
            group_id=group_id, strategy_id=strategy_id,
        ).first()
        if not row:
            raise HTTPException(404, "该策略权限不存在")

        session.delete(row)
        session.commit()
        return {"success": True, "message": "策略权限已移除"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"移除失败: {e}")
    finally:
        session.close()


@router.post("/groups/{group_id}/tool-permissions")
async def set_group_tool_permission(
    group_id: int,
    req: "SetGroupToolPermissionRequest",
    admin: dict = Depends(require_admin_user),
):
    """设置组的工具权限"""
    if req.tool_key not in ALL_TOOLS:
        raise HTTPException(400, f"无效工具: {req.tool_key}")

    session = _session()
    try:
        row = session.query(UserGroupToolPermission).filter_by(
            group_id=group_id, tool_key=req.tool_key,
        ).first()
        if row:
            row.enabled = req.enabled
        else:
            session.add(UserGroupToolPermission(
                group_id=group_id, tool_key=req.tool_key, enabled=req.enabled,
            ))

        session.commit()
        return {"success": True, "message": "工具权限已保存"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"设置失败: {e}")
    finally:
        session.close()
