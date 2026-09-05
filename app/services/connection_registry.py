"""
集中化连接注册表 — 跨 WebSocket 端点的在线用户追踪。

所有 WebSocket 端点（tick、agent、monitor）在连接/断开时注册/注销，
提供统一的"谁在线"视图供管理面板使用。

线程安全：使用 threading.Lock，同 MarketData 模式。
"""

import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionRegistry:
    """追踪所有 WebSocket 端点的在线用户（单例）。"""

    def __init__(self):
        self._lock = threading.Lock()
        # user_id -> {"username": str, "role": str, "connection_count": int, "connected_since": datetime}
        self._users: dict[int, dict] = {}

    def register(self, user_id: int, username: str, role: str) -> None:
        """注册一个连接。同一用户多连接时只计数 +1。"""
        with self._lock:
            entry = self._users.get(user_id)
            if entry is None:
                self._users[user_id] = {
                    "username": username,
                    "role": role,
                    "connection_count": 1,
                    "connected_since": datetime.now(),
                }
                logger.info(
                    "用户上线: user=%d username=%s role=%s (在线总人数: %d)",
                    user_id, username, role, len(self._users),
                )
            else:
                entry["connection_count"] += 1
                # 如果用户名/角色有更新（如登录后切换），刷新
                entry["username"] = username
                entry["role"] = role

    def unregister(self, user_id: int) -> None:
        """注销一个连接。计数归零时移除用户。"""
        with self._lock:
            entry = self._users.get(user_id)
            if entry is None:
                return
            entry["connection_count"] -= 1
            if entry["connection_count"] <= 0:
                del self._users[user_id]
                logger.info(
                    "用户下线: user=%d (在线总人数: %d)",
                    user_id, len(self._users),
                )

    @property
    def unique_online_count(self) -> int:
        """当前在线唯一用户数。"""
        with self._lock:
            return len(self._users)

    def get_online_users(self) -> list[dict]:
        """返回当前在线用户列表（快照）。"""
        with self._lock:
            return [
                {
                    "user_id": uid,
                    "username": data["username"],
                    "role": data["role"],
                    "connected_since": data["connected_since"],
                }
                for uid, data in self._users.items()
            ]


# 全局单例
connection_registry = ConnectionRegistry()
