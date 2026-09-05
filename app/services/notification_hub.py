"""
通知中枢 — per-user WebSocket 推送。

管理用户的通知 WebSocket 连接，支持向指定用户推送消息。
用于 API Token 下单确认等需要用户实时响应的场景。

线程安全：使用 threading.Lock，同 MarketData 模式。
"""

import json
import logging
import threading

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class NotificationHub:
    """全局通知中枢（单例）。"""

    def __init__(self):
        self._lock = threading.Lock()
        # user_id -> [ws, ...]
        self._connections: dict[int, list[WebSocket]] = {}

    def add_subscriber(self, user_id: int, ws: WebSocket) -> None:
        """注册一个用户的通知连接。"""
        with self._lock:
            conns = self._connections.setdefault(user_id, [])
            conns.append(ws)
        logger.info(
            "通知连接注册: user=%d (当前 %d 个连接)",
            user_id, len(self._connections.get(user_id, [])),
        )

    def remove_subscriber(self, user_id: int, ws: WebSocket) -> None:
        """移除一个通知连接。"""
        with self._lock:
            conns = self._connections.get(user_id, [])
            self._connections[user_id] = [c for c in conns if c is not ws]
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("通知连接移除: user=%d", user_id)

    async def notify_user(self, user_id: int, message: dict) -> int:
        """
        向指定用户的所有通知连接推送消息。

        返回成功发送的连接数。
        """
        with self._lock:
            conns = list(self._connections.get(user_id, []))

        if not conns:
            logger.debug("通知推送: user=%d 无在线连接，消息未送达", user_id)
            return 0

        payload = json.dumps(message, ensure_ascii=False, default=str)
        sent = 0
        dead = []

        for ws in conns:
            try:
                await ws.send_text(payload)
                sent += 1
            except Exception:
                dead.append(ws)

        # 清理断开的连接
        if dead:
            with self._lock:
                conns = self._connections.get(user_id, [])
                self._connections[user_id] = [c for c in conns if c not in dead]
                if not self._connections[user_id]:
                    del self._connections[user_id]

        if sent > 0:
            logger.info(
                "通知推送: user=%d type=%s 送达 %d/%d",
                user_id, message.get("type", "?"), sent, len(conns),
            )

        return sent

    def has_connections(self, user_id: int) -> bool:
        """检查用户是否有在线通知连接。"""
        with self._lock:
            return bool(self._connections.get(user_id))

    @property
    def online_user_count(self) -> int:
        """当前有通知连接的在线用户数。"""
        with self._lock:
            return len(self._connections)


# 全局单例
notification_hub = NotificationHub()
