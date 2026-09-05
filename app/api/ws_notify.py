"""
WebSocket 通知端点 — 实时推送下单确认等通知给用户。

/ws/notifications — 用户通知推送
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

ws_notify_router = APIRouter()


@ws_notify_router.websocket("/ws/notifications")
async def notification_websocket(ws: WebSocket):
    """
    用户通知 WebSocket。

    鉴权：query param ?token=<jwt>
    消息格式：{ "type": "order_confirm", "data": {...} }
    """
    from ..auth.security import decode_token

    token = ws.query_params.get("token", "")
    payload = decode_token(token) if token else None
    if payload is None:
        await ws.close(code=4001, reason="Authentication required")
        return

    user_id: int = payload.get("user_id", 0)

    await ws.accept()

    from ..services.notification_hub import notification_hub
    notification_hub.add_subscriber(user_id, ws)

    logger.info("通知 WebSocket 已连接: user=%d", user_id)

    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        logger.info("通知 WebSocket 已断开: user=%d", user_id)
    except Exception:
        logger.exception("通知 WebSocket 异常: user=%d", user_id)
    finally:
        notification_hub.remove_subscriber(user_id, ws)
        logger.info("通知 WebSocket 已清理: user=%d", user_id)
