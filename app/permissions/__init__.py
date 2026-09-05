"""
权限模块 - 策略/监控访问控制

提供 FastAPI 依赖函数，在 API 端点层面执行权限检查。
"""

from .dependencies import (
    require_strategy_access,
    require_strategy_trade,
    require_strategy_modify,
    require_admin_user,
    require_monitor_access,
    require_monitor_modify,
    get_accessible_strategy_ids,
)
from .service import (
    ALL_TOOLS,
    TOOL_TO_CLASSES,
    get_enabled_tools,
    get_enabled_tool_classes,
    set_tool_permission,
    get_all_tool_permissions,
)

__all__ = [
    # FastAPI 依赖
    "require_strategy_access",
    "require_strategy_trade",
    "require_strategy_modify",
    "require_admin_user",
    "require_monitor_access",
    "require_monitor_modify",
    # 工具函数
    "get_accessible_strategy_ids",
    # 工具权限
    "ALL_TOOLS",
    "TOOL_TO_CLASSES",
    "get_enabled_tools",
    "get_enabled_tool_classes",
    "set_tool_permission",
    "get_all_tool_permissions",
]
