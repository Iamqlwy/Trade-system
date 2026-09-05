"""
量化交易系统 - WebSocket 端点

/ws/tick — 实时行情推送（带连接数限制）
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..dependencies import market_data

logger = logging.getLogger(__name__)

ws_router = APIRouter()

# 每用户最大 tick WS 连接数
_MAX_TICK_WS_PER_USER = 5
_user_ws_count: dict[int, int] = {}


@ws_router.websocket("/ws/tick")
async def tick_websocket(ws: WebSocket):
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
    current_count = _user_ws_count.get(user_id, 0)
    if current_count >= _MAX_TICK_WS_PER_USER:
        logger.warning(
            "WebSocket 连接超限: user=%d count=%d limit=%d",
            user_id, current_count, _MAX_TICK_WS_PER_USER,
        )
        await ws.close(code=4003, reason="Too many connections")
        return

    _user_ws_count[user_id] = current_count + 1
    await ws.accept()
    market_data.add_subscriber(ws)

    from ..services.connection_registry import connection_registry
    connection_registry.register(user_id, username, role)

    logger.info(
        "WebSocket client connected: user=%d (%d total, user has %d)",
        user_id, market_data.subscriber_count, current_count + 1,
    )
    try:
        while True:
            # 保持连接存活，客户端发 ping 则回 pong
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端主动断开: user=%d", user_id)
    except Exception:
        logger.exception("WebSocket 异常: user=%d", user_id)
    finally:
        market_data.remove_subscriber(ws)
        _user_ws_count[user_id] = max(0, _user_ws_count.get(user_id, 1) - 1)
        if _user_ws_count[user_id] == 0:
            del _user_ws_count[user_id]

        from ..services.connection_registry import connection_registry
        connection_registry.unregister(user_id)

        logger.info(
            "WebSocket 客户端已清理: user=%d (剩余订阅者: %d)",
            user_id, market_data.subscriber_count,
        )
