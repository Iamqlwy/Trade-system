"""Agent WebSocket 端点

/ws/agent — Agent 实时通信（带 JWT 鉴权 + 用户隔离 + 连接数限制 + 消息频率限制）
"""

import asyncio
import json
import logging
import re
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

ws_agent_router = APIRouter()

# 每用户最大 Agent WS 连接数
_MAX_AGENT_WS_PER_USER = 2
_user_agent_ws_count: dict[int, int] = {}

# ── 消息级防护常量 ──
_MAX_MESSAGE_LENGTH = 50000          # 单条消息内容最大字符数
_MAX_MESSAGES_PER_MINUTE = 20        # 每分钟最大消息数（按 user_id）
_user_msg_timestamps: dict[int, list[float]] = {}  # user_id → [时间戳]

# ── 注入检测模式（仅记录，不阻断）──
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?above\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an)\s+", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?prior", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?your\s+(rules|instructions|guidelines)", re.IGNORECASE),
]


def _check_ws_rate_limit(user_id: int) -> bool:
    """检查 WebSocket 消息频率限制。返回 True=通过, False=超限。"""
    now = time.time()
    timestamps = _user_msg_timestamps.get(user_id, [])
    # 清理 60 秒前的时间戳
    timestamps = [t for t in timestamps if now - t < 60]
    if len(timestamps) >= _MAX_MESSAGES_PER_MINUTE:
        _user_msg_timestamps[user_id] = timestamps
        return False
    timestamps.append(now)
    _user_msg_timestamps[user_id] = timestamps
    return True


def _detect_injection(text: str) -> bool:
    """检测文本中是否包含明显的注入模式。返回 True=检测到可疑模式。"""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False


@ws_agent_router.websocket("/ws/agent")
async def agent_websocket(ws: WebSocket):
    """Agent WebSocket 连接

    鉴权：通过 query param ?token=<jwt> 传递 JWT。
    前端 → 后端消息格式：
      {"action": "send_message", "session_id": "...", "content": "..."}
      {"action": "interrupt", "session_id": "..."}
      {"action": "restore_session", "session_id": "..."}
      {"action": "list_sessions"}
      {"action": "create_session"}
      {"action": "answer_question", "request_id": "...", "answer": "..."}
    """
    from ..auth.security import decode_token

    # ---- JWT 鉴权 ----
    # 优先从 query param 取，回退到 httponly cookie（agent.js 用 document.cookie
    # 读不到 httponly cookie，但浏览器会自动在 WS 升级请求中带上）
    token = ws.query_params.get("token", "") or ws.cookies.get("access_token", "")
    payload = decode_token(token) if token else None
    if payload is None:
        await ws.close(code=4001, reason="Authentication required")
        return

    user_id: int = payload.get("user_id", 0)
    username: str = payload.get("sub", "")
    role: str = payload.get("role", "")

    # ---- Agent 权限检查 ----
    if role != "admin":
        from ..auth.models import User as _User
        from ..dependencies import repository as _repo
        _s = _repo.SessionLocal()
        try:
            _db_user = _s.query(_User).filter_by(id=user_id).first()
            if not _db_user or not _db_user.can_use_agent:
                await ws.close(code=4003, reason="Agent access denied")
                return
        finally:
            _s.close()

    # ---- 连接数限制 ----
    current_count = _user_agent_ws_count.get(user_id, 0)
    if current_count >= _MAX_AGENT_WS_PER_USER:
        logger.warning(
            "Agent WS 连接超限: user=%d count=%d limit=%d",
            user_id, current_count, _MAX_AGENT_WS_PER_USER,
        )
        await ws.close(code=4003, reason="Too many agent connections")
        return

    _user_agent_ws_count[user_id] = current_count + 1
    await ws.accept()

    from ..services.connection_registry import connection_registry
    connection_registry.register(user_id, username, role)

    logger.info(
        "Agent WS connected: user=%s (id=%d, connections=%d)",
        username, user_id, current_count + 1,
    )

    from ..services.agent_manager import agent_manager
    from ..config import settings

    # 从应用 Settings 统一配置 LLM
    agent_manager.configure_from_settings(settings)

    # 连接状态标志，防止在断开后继续发送
    closed = False
    # 跟踪后台任务，断开时取消
    background_tasks: set[asyncio.Task] = set()

    async def ws_send(text: str) -> None:
        nonlocal closed
        if closed:
            return
        try:
            await ws.send_text(text)
        except Exception:
            closed = True
            logger.warning("WS send failed, marking connection as closed")

    agent_manager.register_user_connection(user_id, ws_send)

    def _track_task(task: asyncio.Task) -> None:
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    try:
        while True:
            raw = await ws.receive_text()
            if raw == "ping":
                await ws.send_text("pong")
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"error": "Invalid JSON"}))
                continue

            action = data.get("action", "")

            if action == "send_message":
                session_id = data.get("session_id", "")
                content = data.get("content", "")
                images = data.get("images", [])  # [{url, name}, ...]
                if not content and not images:
                    await ws.send_text(json.dumps({"error": "content or images required"}))
                    continue

                # ── 消息大小限制 ──
                if len(content) > _MAX_MESSAGE_LENGTH:
                    await ws.send_text(json.dumps({
                        "error": f"消息内容过长（{len(content)} 字符），上限 {_MAX_MESSAGE_LENGTH} 字符",
                    }, ensure_ascii=False))
                    continue

                # ── 频率限制 ──
                if not _check_ws_rate_limit(user_id):
                    await ws.send_text(json.dumps({
                        "error": f"发送过于频繁，每分钟最多 {_MAX_MESSAGES_PER_MINUTE} 条消息",
                    }, ensure_ascii=False))
                    continue

                # ── 注入检测（仅记录日志，不阻断）──
                if isinstance(content, str) and _detect_injection(content):
                    logger.warning(
                        "Agent WS 注入检测: user=%d session=%s content_preview=%s",
                        user_id, session_id, content[:200],
                    )

                # 限制每轮最多 5 张图片
                if len(images) > 5:
                    images = images[:5]

                # 构建多模态 content（有图片时使用 list 格式）
                if images:
                    content_parts = []
                    if content:
                        content_parts.append({"type": "text", "text": content})
                    for img in images:
                        img_url = img.get("url", "")
                        if img_url:
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {"url": img_url},
                            })
                    user_content = content_parts
                else:
                    user_content = content

                # 如果没有 session_id，自动创建会话
                if not session_id:
                    session_id = agent_manager.create_session(user_id=user_id)
                    await ws.send_text(json.dumps({
                        "type": "agent_stream",
                        "event": "session_created",
                        "data": {"session_id": session_id},
                    }))
                else:
                    # 验证会话归属权，防止用户向其他人的会话发送消息
                    session_owner = agent_manager._get_session_owner(session_id)
                    if session_owner is not None and session_owner != user_id:
                        await ws.send_text(json.dumps({
                            "type": "agent_stream",
                            "event": "error",
                            "data": {"message": "无权操作此会话"},
                        }, ensure_ascii=False))
                        continue
                # 确定 agent_type：新会话默认 simple，已有会话从 DB 查
                if data.get("session_id"):
                    agent_type = agent_manager._get_session_agent_type(session_id) or "simple"
                else:
                    agent_type = "simple"
                task = asyncio.create_task(
                    agent_manager.send_message(
                        session_id, agent_type, user_content, ws_send, user_id=user_id,
                    )
                )
                _track_task(task)

            elif action == "interrupt":
                session_id = data.get("session_id", "")
                # 验证会话归属权
                session_owner = agent_manager._get_session_owner(session_id)
                if session_owner is not None and session_owner != user_id:
                    await ws.send_text(json.dumps({
                        "type": "agent_stream",
                        "event": "error",
                        "data": {"message": "无权操作此会话"},
                    }, ensure_ascii=False))
                    continue
                agent_manager.interrupt(session_id)

            elif action == "restore_session":
                session_id = data.get("session_id", "")
                if session_id:
                    # 验证会话归属权
                    session_owner = agent_manager._get_session_owner(session_id)
                    if session_owner is not None and session_owner != user_id:
                        await ws.send_text(json.dumps({
                            "type": "agent_stream",
                            "event": "error",
                            "data": {"message": "无权访问此会话"},
                        }, ensure_ascii=False))
                        continue
                    task = asyncio.create_task(
                        agent_manager.restore_session(session_id, ws_send, user_id=user_id)
                    )
                    _track_task(task)

            elif action == "list_sessions":
                sessions = agent_manager.list_sessions(user_id=user_id)
                await ws.send_text(json.dumps({
                    "type": "agent_stream",
                    "event": "session_list",
                    "data": sessions,
                }, ensure_ascii=False))

            elif action == "create_session":
                session_id = agent_manager.create_session(user_id=user_id)
                await ws.send_text(json.dumps({
                    "type": "agent_stream",
                    "event": "session_created",
                    "data": {"session_id": session_id},
                }))

            elif action == "upgrade_session":
                # 将临时会话（tmp-xxx）升级为真实会话
                import uuid as _uuid
                temp_id = data.get("session_id", "")
                if not temp_id:
                    await ws.send_text(json.dumps({"error": "session_id required"}))
                    continue
                # 验证临时会话归属权
                temp_owner = agent_manager._session_users.get(temp_id)
                if temp_owner is not None and temp_owner != user_id:
                    await ws.send_text(json.dumps({
                        "type": "agent_stream",
                        "event": "error",
                        "data": {"message": "无权操作此会话"},
                    }, ensure_ascii=False))
                    continue
                real_id = "ag_" + _uuid.uuid4().hex[:16]
                agent_manager.upgrade_session(temp_id, real_id, user_id=user_id)
                await ws.send_text(json.dumps({
                    "type": "agent_stream",
                    "event": "session_upgraded",
                    "data": {"old_id": temp_id, "session_id": real_id},
                }, ensure_ascii=False))

            elif action == "answer_question":
                request_id = data.get("request_id", "")
                answer = data.get("answer", "")
                if request_id:
                    # 净化 answer 内容
                    from ..utils.sanitize import sanitize_text_field
                    answer = sanitize_text_field(answer, max_length=5000) or ""
                    agent_manager.answer_question(request_id, answer)

            elif action == "toggle_plan_mode":
                session_id = data.get("session_id", "")
                if not session_id:
                    await ws.send_text(json.dumps({"error": "session_id required"}))
                    continue

                # 验证会话归属权
                session_owner = agent_manager._get_session_owner(session_id)
                if session_owner is not None and session_owner != user_id:
                    await ws.send_text(json.dumps({
                        "type": "agent_stream",
                        "event": "error",
                        "data": {"message": "无权操作此会话"},
                    }, ensure_ascii=False))
                    continue

                # 读取当前 plan mode 状态
                from ..agent.config import get_agent_home
                session_dir = get_agent_home() / "sessions" / session_id
                state_file = session_dir / "state.json"

                current_mode = False
                if state_file.exists():
                    try:
                        state_data = json.loads(state_file.read_text())
                        current_mode = state_data.get("plan_mode", False)
                    except (json.JSONDecodeError, OSError):
                        pass

                new_mode = not current_mode

                # 持久化
                state_data = {}
                if state_file.exists():
                    try:
                        state_data = json.loads(state_file.read_text())
                    except (json.JSONDecodeError, OSError):
                        pass
                state_data["plan_mode"] = new_mode
                session_dir.mkdir(parents=True, exist_ok=True)
                state_file.write_text(json.dumps(state_data))

                # 驱逐 agent 缓存，强制下次消息时用新工具集重建
                agent_manager.evict_agent(session_id)

                # 通知前端
                from ..services.agent_events import make_plan_mode_event
                msg = make_plan_mode_event(session_id, new_mode)
                await ws.send_text(json.dumps(msg, ensure_ascii=False))

            else:
                await ws.send_text(json.dumps({"error": f"Unknown action: {action}"}))

    except WebSocketDisconnect:
        logger.info("Agent WS disconnected: user=%s", username)
    except Exception:
        logger.exception("Agent WS error")
    finally:
        # 减少连接计数
        _user_agent_ws_count[user_id] = max(0, _user_agent_ws_count.get(user_id, 1) - 1)
        if _user_agent_ws_count[user_id] == 0:
            del _user_agent_ws_count[user_id]

        from ..services.connection_registry import connection_registry
        connection_registry.unregister(user_id)

        agent_manager.unregister_user_connection(user_id, ws_send)
        closed = True
        # 取消所有仍在运行的后台任务
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
            logger.info("Cancelled %d background task(s) for user=%s",
                        len(background_tasks), username)


