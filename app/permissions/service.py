"""
权限核心逻辑

纯业务函数，不依赖 FastAPI，便于测试和复用。
所有函数接收 SQLAlchemy Session + user dict（JWT payload 或 API Token payload）。

API Token 约束:
  当 user dict 中包含 api_token_id 时，说明是通过 API Token 认证的。
  API Token 只能访问用户自己创建的策略（owner_id 匹配），且仅支持：
  - read:  查看持仓、订单、成交
  - trade: 下单、撤单
  管理员的 API Token 同样只能操作自己的策略。
"""

import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth.models import StrategyUser, UserGroupMember, UserGroupPermission, \
    UserGroupStrategyPermission, UserGroupToolPermission

logger = logging.getLogger(__name__)


# ── API Token 约束检查 ──────────────────────────────

def _is_api_token(user: dict) -> bool:
    """判断 user dict 是否来自 API Token 认证。"""
    return user.get("api_token_id") is not None


def _token_scope_check(session: Session, user: dict, strategy_id: str) -> bool:
    """
    API Token 策略范围检查（始终限制在用户自己的策略内）。

    - scope_type='all':    只要是用户自己的策略即可
    - scope_type='listed': strategy_id 必须在 scope_strategies 白名单中，且是用户自己的

    非 API Token 用户 → 不做额外限制。
    """
    if not _is_api_token(user):
        return True

    from ..store.models import Strategys

    # 首先必须是用户自己的策略
    row = session.query(Strategys.strategy_id).filter(
        Strategys.strategy_id == strategy_id,
        Strategys.owner_id == user["user_id"],
    ).first()
    if row is None:
        return False

    # listed 模式：还必须在白名单中
    scope_type = user.get("token_scope_type", "all")
    if scope_type == "listed":
        allowed = user.get("token_scope_strategies", [])
        return strategy_id in allowed

    return True


def _token_scope_filter_ids(session: Session, user: dict, strategy_ids: set[str]) -> set[str]:
    """
    API Token 过滤：仅保留用户自己的策略，再按 scope 进一步过滤。

    非 API Token 用户 → 原样返回。
    """
    if not _is_api_token(user):
        return strategy_ids

    if not strategy_ids:
        return strategy_ids

    from ..store.models import Strategys

    # 首先只保留用户自己的策略
    rows = session.query(Strategys.strategy_id).filter(
        Strategys.strategy_id.in_(strategy_ids),
        Strategys.owner_id == user["user_id"],
    ).all()
    own_ids = {r[0] for r in rows}

    # listed 模式：进一步限制在白名单内
    scope_type = user.get("token_scope_type", "all")
    if scope_type == "listed":
        allowed = set(user.get("token_scope_strategies", []))
        return own_ids & allowed

    return own_ids


def _token_permission_check(user: dict, required_perm: str) -> bool:
    """
    检查 API Token 的 permissions 是否包含指定操作。

    required_perm: "read" | "trade"
    返回 True = 通过（或非 API Token），False = 拒绝。
    """
    if not _is_api_token(user):
        return True

    token_perms = user.get("token_permissions", [])
    return required_perm in token_perms


# ── 用户组查询 ──────────────────────────────────

def get_user_group_ids(session: Session, user_id: int) -> list[int]:
    """获取用户所属的所有组 ID"""
    rows = session.query(UserGroupMember.group_id).filter_by(user_id=user_id).all()
    return [r[0] for r in rows]


def get_effective_feature_permissions(session: Session, user: dict) -> dict:
    """
    计算用户的有效功能权限（合并组权限 + 个人覆盖）。
    admin 返回全开。
    合并策略：bool 取 OR（任一组开启即开启），max_strategies 取 MAX。
    个人显式设置覆盖组合并值。
    """
    if user.get("role") == "admin":
        return {
            "can_use_agent": True,
            "can_create_real": True,
            "max_strategies": -1,
            "can_use_cron": True,
            "can_use_monitor": True,
        }

    from ..auth.models import User
    user_id = user["user_id"]
    db_user = session.query(User).filter_by(id=user_id).first()
    if not db_user:
        return {
            "can_use_agent": True,
            "can_create_real": True,
            "max_strategies": 10,
            "can_use_cron": True,
            "can_use_monitor": True,
        }

    # 默认值
    effective = {
        "can_use_agent": True,
        "can_create_real": True,
        "max_strategies": 10,
        "can_use_cron": True,
        "can_use_monitor": True,
    }

    # 合并组权限（最宽松策略）
    group_ids = get_user_group_ids(session, user_id)
    if group_ids:
        group_perms = session.query(UserGroupPermission).filter(
            UserGroupPermission.group_id.in_(group_ids)
        ).all()
        for gp in group_perms:
            if gp.can_use_agent is not None:
                effective["can_use_agent"] = effective["can_use_agent"] or gp.can_use_agent
            if gp.can_create_real is not None:
                effective["can_create_real"] = effective["can_create_real"] or gp.can_create_real
            if gp.can_use_cron is not None:
                effective["can_use_cron"] = effective["can_use_cron"] or gp.can_use_cron
            if gp.can_use_monitor is not None:
                effective["can_use_monitor"] = effective["can_use_monitor"] or gp.can_use_monitor
            if gp.max_strategies is not None:
                effective["max_strategies"] = max(effective["max_strategies"], gp.max_strategies)

    # 个人覆盖（显式设置优先）
    if db_user.can_use_agent is not None:
        effective["can_use_agent"] = db_user.can_use_agent
    if db_user.can_create_real is not None:
        effective["can_create_real"] = db_user.can_create_real
    if db_user.max_strategies is not None:
        effective["max_strategies"] = db_user.max_strategies
    if db_user.can_use_cron is not None:
        effective["can_use_cron"] = db_user.can_use_cron
    if db_user.can_use_monitor is not None:
        effective["can_use_monitor"] = db_user.can_use_monitor

    return effective


# ── 策略权限查询 ──────────────────────────────────

def get_accessible_strategy_ids(session: Session, user: dict) -> Optional[set[str]]:
    """
    返回用户可访问的 strategy_id 集合。

    - admin（非 API Token）返回 None（表示全部可访问）
    - API Token 用户（含 admin）：仅返回自己创建的策略
    - 普通用户：owner_id 匹配 + strategy_users + 组策略权限
    """
    # API Token 用户：只能看自己的策略，再按 scope 过滤
    if _is_api_token(user):
        from ..store.models import Strategys
        rows = session.query(Strategys.strategy_id).filter(
            Strategys.owner_id == user["user_id"],
            Strategys.is_deleted == 0,
        ).all()
        own_ids = {r[0] for r in rows}
        return _token_scope_filter_ids(session, user, own_ids)

    if user.get("role") == "admin":
        return None

    user_id = user["user_id"]

    from ..store.models import Strategys

    # 查询：owner_id 匹配 OR strategy_users 中有记录
    rows = session.query(Strategys.strategy_id).filter(
        or_(
            Strategys.owner_id == user_id,
            Strategys.strategy_id.in_(
                session.query(StrategyUser.strategy_id).filter_by(user_id=user_id)
            ),
        ),
        Strategys.is_deleted == 0,
    ).all()

    result = {r[0] for r in rows}

    # 加入组策略权限
    group_ids = get_user_group_ids(session, user_id)
    if group_ids:
        group_rows = session.query(UserGroupStrategyPermission.strategy_id).filter(
            UserGroupStrategyPermission.group_id.in_(group_ids)
        ).all()
        result.update(r[0] for r in group_rows)

    return result


def check_strategy_access(session: Session, user: dict, strategy_id: str) -> bool:
    """检查用户是否可以查看策略（含 API Token scope 约束）。"""
    if user.get("role") == "admin":
        # admin 仍需通过 API Token scope 检查
        if not _token_scope_check(session, user, strategy_id):
            return False
        return True

    # API Token scope 前置检查
    if not _token_scope_check(session, user, strategy_id):
        return False

    # API Token permissions: 至少需要 read
    if not _token_permission_check(user, "read"):
        return False

    user_id = user["user_id"]
    from ..store.models import Strategys

    # owner_id 匹配 OR strategy_users 有记录
    row = session.query(Strategys.strategy_id).filter(
        Strategys.strategy_id == strategy_id,
        or_(
            Strategys.owner_id == user_id,
            Strategys.strategy_id.in_(
                session.query(StrategyUser.strategy_id).filter_by(user_id=user_id)
            ),
        ),
    ).first()
    if row is not None:
        return True

    # 组策略权限
    group_ids = get_user_group_ids(session, user_id)
    if group_ids:
        gp = session.query(UserGroupStrategyPermission).filter(
            UserGroupStrategyPermission.group_id.in_(group_ids),
            UserGroupStrategyPermission.strategy_id == strategy_id,
        ).first()
        if gp is not None:
            return True

    return False


def check_strategy_trade(session: Session, user: dict, strategy_id: str) -> bool:
    """检查用户是否可以交易（下单/撤单），含 API Token 约束。"""
    # API Token permissions: 需要 trade
    if not _token_permission_check(user, "trade"):
        return False

    # API Token scope 前置检查
    if not _token_scope_check(session, user, strategy_id):
        return False

    if user.get("role") == "admin":
        return True

    user_id = user["user_id"]
    # 个人策略权限
    row = session.query(StrategyUser).filter_by(
        user_id=user_id, strategy_id=strategy_id, can_trade=True,
    ).first()
    if row is not None:
        return True

    # 组策略权限
    group_ids = get_user_group_ids(session, user_id)
    if group_ids:
        gp = session.query(UserGroupStrategyPermission).filter(
            UserGroupStrategyPermission.group_id.in_(group_ids),
            UserGroupStrategyPermission.strategy_id == strategy_id,
            UserGroupStrategyPermission.can_trade == True,
        ).first()
        if gp is not None:
            return True

    return False


def check_strategy_modify(session: Session, user: dict, strategy_id: str) -> bool:
    """检查用户是否可以修改/删除策略。API Token 不允许修改策略。"""
    if _is_api_token(user):
        return False
    return check_strategy_trade(session, user, strategy_id)


# ── 策略权限写操作 ────────────────────────────────

def grant_strategy_access(
    session: Session, user_id: int, strategy_id: str, can_trade: bool,
) -> None:
    """授权用户对策略的访问权限（INSERT or UPDATE）"""
    row = session.query(StrategyUser).filter_by(
        user_id=user_id, strategy_id=strategy_id,
    ).first()
    if row:
        row.can_trade = can_trade
    else:
        session.add(StrategyUser(
            user_id=user_id, strategy_id=strategy_id, can_trade=can_trade,
        ))
    session.flush()


def revoke_strategy_access(session: Session, user_id: int, strategy_id: str) -> None:
    """撤销用户对策略的访问权限"""
    session.query(StrategyUser).filter_by(
        user_id=user_id, strategy_id=strategy_id,
    ).delete()
    session.flush()


def associate_creator(session: Session, user_id: int, strategy_id: str) -> None:
    """创建策略后自动关联创建者（can_trade=True）"""
    grant_strategy_access(session, user_id, strategy_id, can_trade=True)


# ── 权限列表查询（Settings 用）────────────────────

def list_all_permissions(session: Session) -> list[dict]:
    """列出所有策略权限记录"""
    from ..auth.models import User
    from ..store.models import Strategys

    rows = session.query(StrategyUser, User.username, Strategys.name).join(
        User, StrategyUser.user_id == User.id,
    ).join(
        Strategys, StrategyUser.strategy_id == Strategys.strategy_id,
    ).all()

    return [
        {
            "user_id": su.user_id,
            "username": username,
            "strategy_id": su.strategy_id,
            "strategy_name": name,
            "can_trade": su.can_trade,
        }
        for su, username, name in rows
    ]


def list_user_permissions(session: Session, user_id: int) -> list[dict]:
    """列出指定用户的策略权限"""
    from ..store.models import Strategys

    rows = session.query(StrategyUser, Strategys.name).join(
        Strategys, StrategyUser.strategy_id == Strategys.strategy_id,
    ).filter(StrategyUser.user_id == user_id).all()

    return [
        {
            "strategy_id": su.strategy_id,
            "strategy_name": name,
            "can_trade": su.can_trade,
        }
        for su, name in rows
    ]


# ── 监控权限 ──────────────────────────────────────

def check_monitor_access(user: dict, monitor_owner_id: Optional[int]) -> bool:
    """
    检查用户是否可以查看监控。

    - admin 始终可以
    - owner_id 为 None（老监控）仅 admin 可访问
    - 其他按 owner_id 匹配
    """
    if user.get("role") == "admin":
        return True
    if monitor_owner_id is None:
        return False
    return user["user_id"] == monitor_owner_id


def check_monitor_modify(user: dict, monitor_owner_id: Optional[int]) -> bool:
    """检查用户是否可以修改/删除/控制监控"""
    return check_monitor_access(user, monitor_owner_id)


def filter_monitors(user: dict, monitors: list[dict]) -> list[dict]:
    """
    按用户权限过滤监控列表。

    - admin 返回全部
    - 普通用户只返回 owner_id 匹配的监控
    - owner_id 为 None 的老监控对普通用户不可见
    """
    if user.get("role") == "admin":
        return monitors
    user_id = user["user_id"]
    return [m for m in monitors if m.get("owner_id") == user_id]


# ── 工具权限 ──────────────────────────────────────

ALL_TOOLS: list[str] = [
    "shell", "file_read", "file_write", "file_search",
    "web_search", "web_fetch", "cronjob", "agent", "strategy_view",
]

TOOL_TO_CLASSES: dict[str, list[str]] = {
    "shell":        ["Shell"],
    "file_read":    ["ReadFile"],
    "file_write":   ["WriteFile", "StrReplaceFile"],
    "file_search":  ["Glob", "Grep"],
    "web_search":   ["WebSearchTool"],
    "web_fetch":    ["WebFetch"],
    "cronjob":      ["Cronjob"],
    "agent":        ["Agent"],
    "strategy_view": ["StrategyView"],
}


def get_enabled_tools(session: Session, user: dict) -> set[str]:
    """
    返回用户可用的工具 key 集合。

    - admin 返回全部
    - 普通用户：ALL_TOOLS 减去被禁用的（组禁用 + 个人禁用）
    """
    if user.get("role") == "admin":
        return set(ALL_TOOLS)

    from ..auth.models import UserToolPermission

    enabled = set(ALL_TOOLS)

    # 组工具权限（组禁用的去掉）
    group_ids = get_user_group_ids(session, user["user_id"])
    if group_ids:
        group_restrictions = session.query(UserGroupToolPermission).filter(
            UserGroupToolPermission.group_id.in_(group_ids),
            UserGroupToolPermission.enabled == False,
        ).all()
        for gr in group_restrictions:
            enabled.discard(gr.tool_key)

    # 个人工具权限（覆盖组设置）
    rows = session.query(UserToolPermission).filter_by(
        user_id=user["user_id"],
    ).all()
    for r in rows:
        if r.enabled:
            enabled.add(r.tool_key)
        else:
            enabled.discard(r.tool_key)

    return enabled


def get_enabled_tool_classes(session: Session, user: dict) -> set[str]:
    """返回用户可用的工具类名集合（用于注册表过滤）。"""
    enabled_keys = get_enabled_tools(session, user)
    classes: set[str] = set()
    for key in enabled_keys:
        classes.update(TOOL_TO_CLASSES.get(key, []))
    return classes


def set_tool_permission(
    session: Session, user_id: int, tool_key: str, enabled: bool,
) -> None:
    """设置用户的工具权限。"""
    from ..auth.models import UserToolPermission

    row = session.query(UserToolPermission).filter_by(
        user_id=user_id, tool_key=tool_key,
    ).first()
    if row:
        row.enabled = enabled
    else:
        session.add(UserToolPermission(
            user_id=user_id, tool_key=tool_key, enabled=enabled,
        ))
    session.flush()


def get_all_tool_permissions(session: Session) -> list[dict]:
    """
    列出所有用户的工具权限（admin 用）。

    返回格式: [{"user_id": 1, "username": "admin", "tools": {"shell": True, ...}}, ...]
    """
    from ..auth.models import User, UserToolPermission

    users = session.query(User).all()
    result = []
    for u in users:
        perms = session.query(UserToolPermission).filter_by(user_id=u.id).all()
        perm_map = {p.tool_key: p.enabled for p in perms}
        # 无记录 = 默认启用
        tools = {t: perm_map.get(t, True) for t in ALL_TOOLS}
        result.append({
            "user_id": u.id,
            "username": u.username,
            "tools": tools,
        })
    return result
