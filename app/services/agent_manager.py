"""Agent 生命周期管理 + 会话持久化

管理三种 Agent 实例的创建、事件转发、会话恢复。
支持用户级会话隔离（user_id）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Callable

from .agent_events import (
    make_token_event,
    make_thinking_event,
    make_tool_start_event,
    make_tool_end_event,
    make_done_event,
    make_error_event,
    make_restored_event,
    make_ask_user_event,
    make_sub_agent_event,
    make_plan_mode_event,
)

logger = logging.getLogger(__name__)

# Plan mode: tools that are still available in read-only planning mode
_PLAN_MODE_READONLY_TOOLS: set[str] = {
    "ReadFile", "Glob", "Grep", "WebSearchTool", "WebFetch",
    "Think", "AskUserQuestion", "SkillsList", "SkillView",
    "StrategyView", "ExitPlanMode", "Memory",
}


class AgentManager:
    """管理所有 Agent 实例和会话"""

    def __init__(self):
        self._agents: dict[str, Any] = {}
        self._agent_types: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._ws_send: dict[str, Callable] = {}
        self._session_users: dict[str, int] = {}  # session_id → user_id
        self._pending_questions: dict[str, asyncio.Event] = {}  # request_id → event
        self._pending_answers: dict[str, str] = {}  # request_id → answer
        self._titles_generated: set[str] = set()  # 已生成标题的会话
        self._agent_lock = asyncio.Lock()  # 保护 _get_or_create_agent 的并发
        self._user_connections: dict[int, set[Callable]] = {}  # user_id → ws_send callbacks
        self._model: str = ""
        self._base_url: str = ""
        self._api_key: str = ""
        self._api_mode: str = "chat"
        self._small_model: str = ""
        self._small_llm = None  # 懒加载：标题生成复用的小模型客户端

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    def configure(self, model: str = "", base_url: str = "", api_key: str = "", api_mode: str = "chat") -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._api_mode = api_mode

    def configure_from_settings(self, settings: Any) -> None:
        """从主应用 Settings 对象统一配置 LLM"""
        from ..agent.config import get_model_config_from_settings
        cfg = get_model_config_from_settings(settings)
        self._model = cfg["model"]
        self._base_url = cfg["base_url"]
        self._api_key = cfg["api_key"]
        self._api_mode = cfg["api_mode"]
        # 小模型用于标题生成等轻量任务（环境变量 LLM_SMALL_MODEL，默认 qwen3-flash）
        self._small_model = getattr(settings, "llm_small_model", "") or "qwen3.5-flash"
        # 重置懒加载客户端，以便下次使用新配置重建
        self._small_llm = None

    # ------------------------------------------------------------------
    # 事件回调
    # ------------------------------------------------------------------

    def _make_event_callback(self, session_id: str, agent_id: str = "main") -> Callable:
        def callback(event: str, data: dict) -> None:
            ws_send = self._ws_send.get(session_id)
            if not ws_send:
                return

            msg: dict[str, Any] | None = None
            sub_agent_id = data.get("sub_agent_id", "")

            if event == "token":
                msg = make_token_event(session_id, agent_id, data.get("content", ""))
            elif event == "thinking":
                msg = make_thinking_event(session_id, agent_id, data.get("turn", 0), data.get("step", 0))
            elif event == "tool_start":
                msg = make_tool_start_event(
                    session_id, agent_id,
                    data.get("tool_call_id", ""),
                    data.get("name", ""),
                    data.get("args", {}),
                )
            elif event == "tool_end":
                msg = make_tool_end_event(
                    session_id, agent_id,
                    data.get("tool_call_id", ""),
                    data.get("name", ""),
                    data.get("preview", ""),
                    data.get("is_error", False),
                )
            elif event == "sub_agent":
                msg = make_sub_agent_event(
                    session_id, agent_id,
                    action=data.get("action", ""),
                    sub_agent_id=sub_agent_id,
                    sub_agent_type=data.get("sub_agent_type", ""),
                    content=data.get("content", ""),
                    task_description=data.get("task_description", ""),
                    status=data.get("status", ""),
                    result_summary=data.get("result_summary", ""),
                )

                # 持久化子 agent 事件到 context.jsonl
                agent = self._agents.get(session_id)
                if agent and hasattr(agent, "_context"):
                    sub_agent_record = {
                        "role": "_sub_agent",
                        "sub_agent_id": sub_agent_id,
                        "action": data.get("action", ""),
                        "sub_agent_type": data.get("sub_agent_type", ""),
                        "task_description": data.get("task_description", ""),
                        "label": data.get("label", ""),
                        "result_summary": data.get("result_summary", ""),
                        "status": data.get("status", ""),
                        "_meta": {"visible": True, "category": "internal"},
                    }
                    asyncio.ensure_future(agent._context.append_message(sub_agent_record))
            elif event == "error":
                msg = make_error_event(session_id, agent_id, data.get("message", "Unknown error"))

            # 在工具事件中附加 sub_agent_id
            if msg and sub_agent_id and event in ("tool_start", "tool_end"):
                msg.setdefault("data", {})["sub_agent_id"] = sub_agent_id

                # 持久化子 agent 的工具调用到 context.jsonl
                agent = self._agents.get(session_id)
                if agent and hasattr(agent, "_context") and agent._context:
                    tool_record = {
                        "role": f"_{event}",  # "_tool_start" or "_tool_end"
                        "sub_agent_id": sub_agent_id,
                        "tool_call_id": data.get("tool_call_id", ""),
                        "name": data.get("name", ""),
                        "_meta": {"visible": True, "category": "internal"},
                    }
                    if event == "tool_start":
                        tool_record["args"] = data.get("args", {})
                    else:
                        tool_record["preview"] = data.get("preview", "")
                        tool_record["is_error"] = data.get("is_error", False)
                    asyncio.ensure_future(agent._context.append_message(tool_record))

            if msg:
                try:
                    asyncio.create_task(ws_send(json.dumps(msg, ensure_ascii=False)))
                except Exception:
                    logger.exception("Failed to send WS event")

        return callback

    # ------------------------------------------------------------------
    # 消息发送
    # ------------------------------------------------------------------

    async def send_message(
        self,
        session_id: str,
        agent_type: str,
        content: "str | list",
        ws_send: Callable,
        *,
        user_id: int = 0,
    ) -> None:
        """发送消息到 Agent"""
        self._ws_send[session_id] = ws_send
        self._agent_types[session_id] = agent_type
        if user_id:
            self._session_users[session_id] = user_id

        # 提取纯文本（用于斜杠命令检测和摘要）
        if isinstance(content, list):
            text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            content_text = " ".join(text_parts)
        else:
            content_text = content

        stripped = content_text.strip()

        # ── 斜杠命令拦截（在创建 Agent 之前处理，避免为纯命令创建会话） ──
        if stripped.startswith("/"):
            # 有效会话中：保存命令到 context.jsonl（前端可见，agent 不可见）
            context_file = None
            if session_id:
                from ..agent.config import get_agent_home
                ctx_dir = get_agent_home() / "sessions" / session_id
                ctx_dir.mkdir(parents=True, exist_ok=True)
                context_file = ctx_dir / "context.jsonl"
                context_file.touch(exist_ok=True)

            handled = await self._handle_slash_command(
                session_id, stripped, ws_send, user_id,
                context_file=context_file,
            )
            if handled:
                return

        # ── 正常消息：确保 Agent 已创建 ──
        agent = await self._get_or_create_agent(session_id, agent_type)

        if session_id in self._tasks and not self._tasks[session_id].done():
            logger.warning("Agent %s already running, ignoring", session_id)
            return

        async def _run():
            try:
                from app.services.cron_service import _current_user_id
                if user_id:
                    _current_user_id.set(user_id)

                # 新会话第一条消息：立即生成标题（与 LLM 响应并行）
                if session_id not in self._titles_generated:
                    self._titles_generated.add(session_id)
                    asyncio.create_task(self._generate_session_title(session_id, content_text))

                result = await agent.run(content)
                ws = self._ws_send.get(session_id)
                if ws:
                    done_msg = make_done_event(
                        session_id, "main",
                        turns=result.get("turns", 0),
                        api_calls=result.get("api_calls", 0),
                        steps=result.get("steps", 0),
                    )
                    await ws(json.dumps(done_msg, ensure_ascii=False))
                    # 更新会话元数据（消息数、摘要、字符长度）
                    content_len = len(content_text) + len(result.get("final_response", ""))
                    self._update_session_meta(session_id, user_id, agent_type, content_text[:80], content_len)

                # ── 异步记忆提取（不阻塞用户）──
                if result.get("needs_memory_extraction") and user_id > 0:
                    conv_buffer = result.get("conversation_buffer", [])
                    if conv_buffer:
                        asyncio.create_task(
                            self._extract_memories_background(user_id, conv_buffer)
                        )
            except asyncio.CancelledError:
                # 用户主动中断 — 修复可能残留的孤儿 tool_call，然后发送 done 事件
                logger.info("Agent %s interrupted by user", session_id)
                try:
                    agent.fix_orphaned_tool_calls()
                except Exception:
                    logger.debug("fix_orphaned_tool_calls failed (non-critical)", exc_info=True)
                ws = self._ws_send.get(session_id)
                if ws:
                    try:
                        done_msg = make_done_event(session_id, "main", turns=0, api_calls=0)
                        await ws(json.dumps(done_msg, ensure_ascii=False))
                    except Exception:
                        pass
                raise  # 重新抛出让 task 正常结束
            except Exception as e:
                logger.exception("Agent %s failed", session_id)
                ws = self._ws_send.get(session_id)
                if ws:
                    err_msg = make_error_event(session_id, "main", str(e))
                    await ws(json.dumps(err_msg, ensure_ascii=False))
                    # 必须发送 done 事件，否则前端永远卡在 streaming 状态
                    done_msg = make_done_event(session_id, "main", turns=0, api_calls=0)
                    await ws(json.dumps(done_msg, ensure_ascii=False))

        self._tasks[session_id] = asyncio.create_task(_run())

    # ------------------------------------------------------------------
    # 斜杠命令
    # ------------------------------------------------------------------

    async def _handle_slash_command(
        self,
        session_id: str,
        content: str,
        ws_send: Callable,
        user_id: int,
        *,
        context_file: Any | None = None,
    ) -> bool:
        """处理斜杠命令。返回 True 表示已处理（不再转发给 Agent）。

        Args:
            context_file: 有效会话的 context.jsonl 路径。
                提供时，命令会保存到该文件（前端可见），但不进入 agent LLM 上下文。
                None 表示无会话（命令不持久化）。
        """
        parts = content.strip().split(maxsplit=1)
        command = parts[0].lower()

        response_text = ""

        if command == "/help":
            response_text = (
                "**可用命令：**\n\n"
                "- `/help` — 显示此帮助\n"
                "- `/clear` — 清除对话历史\n"
                "- `/skills` — 列出可用技能\n"
                "- `/tools` — 显示已注册的工具\n"
                "- `/model` — 显示当前模型配置\n"
            )

        elif command == "/clear":
            agent = self._agents.get(session_id)
            if agent and hasattr(agent, "_messages"):
                agent._messages.clear()
            response_text = "对话历史已清除。"

        elif command == "/skills":
            from ..agent.skills import scan_skills
            skills = scan_skills(user_id)
            if not skills:
                response_text = "当前没有可用技能。"
            else:
                lines = [f"**可用技能（{len(skills)}）：**\n"]
                for s in skills:
                    lines.append(f"- **{s.name}** — {s.description[:100]}")
                response_text = "\n".join(lines)

        elif command == "/tools":
            # 优先使用已有 agent 的工具注册表（包含用户权限过滤）
            agent = self._agents.get(session_id)
            if agent and hasattr(agent, "_registry"):
                tools = agent._registry.get_all_schemas()
            else:
                # 无 agent（命令先于 agent 创建）→ 临时注册表获取工具列表
                from ..agent.tools import build_full_registry
                temp_reg = build_full_registry()
                tools = temp_reg.get_all_schemas()
            if not tools:
                response_text = "没有注册工具。"
            else:
                lines = [f"**已注册工具（{len(tools)}）：**\n"]
                for t in tools:
                    fn = t.get("function", {})
                    name = fn.get("name", "?")
                    desc = fn.get("description", "")[:80]
                    lines.append(f"- **{name}** — {desc}")
                response_text = "\n".join(lines)

        elif command == "/model":
            response_text = (
                f"**模型配置：**\n\n"
                f"- 模型: `{self._model}`\n"
                f"- Base URL: `{self._base_url or '(default)'}`\n"
                f"- 模式: `{self._api_mode}`\n"
            )

        elif command in ("/exit", "/quit"):
            response_text = "再见！"

        else:
            # 未知命令 — 不拦截，交给 Agent 处理
            return False

        # ── 保存命令 + 响应到 context.jsonl（前端可见，agent 上下文不可见） ──
        if context_file is not None and context_file.exists():
            import json as _json
            try:
                with open(context_file, "a", encoding="utf-8") as f:
                    # 保存命令（role=_command → agent 上下文跳过，前端显示为用户消息）
                    f.write(_json.dumps({
                        "role": "_command",
                        "content": content,
                        "_meta": {"visible": True, "category": "user", "raw_content": content},
                    }, ensure_ascii=False) + "\n")
                    # 保存响应（role=_cmd_response → agent 上下文跳过，前端恢复时显示）
                    f.write(_json.dumps({
                        "role": "_cmd_response",
                        "content": response_text,
                        "_meta": {"visible": True, "category": "cmd_response"},
                    }, ensure_ascii=False) + "\n")
            except OSError:
                logger.debug("Failed to save command to context: %s", content[:50])

        # 通过 WebSocket 发送响应
        # 先发 token 事件（模拟流式输出）
        await ws_send(json.dumps(
            make_token_event(session_id, "main", response_text),
            ensure_ascii=False,
        ))
        # 再发 done 事件
        await ws_send(json.dumps(
            make_done_event(session_id, "main", turns=1, api_calls=0),
            ensure_ascii=False,
        ))
        return True

    # ------------------------------------------------------------------
    # 临时会话 → 真实会话升级
    # ------------------------------------------------------------------

    def upgrade_session(self, temp_id: str, real_id: str, *, user_id: int = 0) -> bool:
        """将临时会话（tmp-xxx）升级为真实会话。

        迁移内存状态（agent、ws_send 等）和 context.jsonl 文件到新 session_id，
        并在数据库中创建真实记录。
        """
        import shutil
        from ..agent.config import get_agent_home

        # 迁移内存状态
        for mapping in (self._agents, self._ws_send, self._session_users,
                        self._agent_types, self._tasks):
            if temp_id in mapping:
                mapping[real_id] = mapping.pop(temp_id)

        # 迁移标题生成状态
        if temp_id in self._titles_generated:
            self._titles_generated.discard(temp_id)

        # 创建数据库记录
        self._save_session_to_db(real_id, user_id)

        # 迁移 context.jsonl（命令历史）到新目录
        sessions_dir = get_agent_home() / "sessions"
        old_dir = sessions_dir / temp_id
        new_dir = sessions_dir / real_id
        new_dir.mkdir(parents=True, exist_ok=True)

        old_ctx = old_dir / "context.jsonl"
        new_ctx = new_dir / "context.jsonl"
        if old_ctx.exists():
            new_ctx.write_bytes(old_ctx.read_bytes())
            try:
                shutil.rmtree(old_dir)
            except OSError:
                pass
        else:
            new_ctx.touch(exist_ok=True)

        return True

    # ------------------------------------------------------------------
    # 中断 / 切换
    # ------------------------------------------------------------------

    def interrupt(self, session_id: str) -> bool:
        """中断正在运行的 Agent 会话。优先取消 task（立即停止 LLM 流），
        回退到设置标志位（等待当前 turn 结束）。"""
        # 优先取消 asyncio task — 这会立即中断正在进行的 LLM 流式调用
        task = self._tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            logger.info("Interrupt: cancelled task for session %s", session_id)
            return True
        # 回退：设置标志位（用于 task 已结束但 agent 仍在的边界情况）
        agent = self._agents.get(session_id)
        if agent and hasattr(agent, "request_interrupt"):
            agent.request_interrupt()
            logger.info("Interrupt: set flag for session %s", session_id)
            return True
        return False

    def switch_mode(self, session_id: str, agent_type: str) -> None:
        self._agents.pop(session_id, None)
        self._agent_types[session_id] = agent_type

    # ------------------------------------------------------------------
    # Agent 创建
    # ------------------------------------------------------------------

    async def _get_or_create_agent(self, session_id: str, agent_type: str = "simple") -> Any:
        if session_id in self._agents:
            return self._agents[session_id]

        async with self._agent_lock:
            # 双重检查：获取锁后再次检查，防止并发创建
            if session_id in self._agents:
                return self._agents[session_id]

            event_cb = self._make_event_callback(session_id)

            from ..agent.config import get_agent_home
            context_file = get_agent_home() / "sessions" / session_id / "context.jsonl"
            context_file.parent.mkdir(parents=True, exist_ok=True)
            context_file.touch(exist_ok=True)

            # 查询用户工具权限
            user_id = self._session_users.get(session_id, 0)
            enabled_tool_classes = None  # None = 全部工具
            if user_id > 0:
                try:
                    from ..dependencies import repository
                    from ..permissions.service import get_enabled_tool_classes
                    session = repository.SessionLocal()
                    try:
                        user = {"user_id": user_id, "role": ""}
                        # 查用户角色
                        from ..auth.models import User
                        u = session.query(User).filter_by(id=user_id).first()
                        if u:
                            user["role"] = u.role
                        enabled_tool_classes = get_enabled_tool_classes(session, user)
                    finally:
                        session.close()
                except Exception:
                    logger.debug("Failed to query tool permissions, using all tools")
                    enabled_tool_classes = None

            # Plan mode: restrict to read-only tools
            plan_mode_active = False
            import json as _json
            state_file = context_file.parent / "state.json"
            if state_file.exists():
                try:
                    plan_mode_active = _json.loads(state_file.read_text()).get("plan_mode", False)
                except (_json.JSONDecodeError, OSError):
                    pass

            if plan_mode_active:
                if enabled_tool_classes is None:
                    enabled_tool_classes = _PLAN_MODE_READONLY_TOOLS
                else:
                    enabled_tool_classes = enabled_tool_classes & _PLAN_MODE_READONLY_TOOLS

            from ..agent.agents import SimpleAgent
            from ..agent.config import get_workspace_dir
            workspace = get_workspace_dir(session_id)

            # 获取记忆服务（DB 模式）
            memory_svc = None
            if user_id > 0:
                try:
                    from .memory_service import memory_service
                    memory_svc = memory_service
                except Exception:
                    logger.debug("memory_service not available")

            agent = SimpleAgent(
                model=self._model,
                base_url=self._base_url,
                api_key=self._api_key,
                api_mode=self._api_mode,
                event_callback=event_cb,
                context_file=context_file,
                enabled_tool_classes=enabled_tool_classes,
                user_id=user_id,
                workspace=workspace,
                session_id=session_id,
                memory_service=memory_svc,
            )

            # 设置 AskUserQuestion 的 WebSocket 交互回调
            self._setup_ask_user_callback(agent, session_id)

            self._agents[session_id] = agent
            return agent

    def _setup_ask_user_callback(self, agent: Any, session_id: str) -> None:
        """为 Agent 的 AskUserQuestion 工具设置 WebSocket 回调

        新回调签名: callback(questions: list[dict]) -> list[str]
        支持 1-4 个问题同时提问，每个问题独立 request_id。
        """
        try:
            ask_tool = agent._registry.find("AskUserQuestion")
            if ask_tool is None or not hasattr(ask_tool, "bind_on_ask"):
                return
        except Exception:
            return

        async def on_ask(questions: list[dict]) -> list[str]:
            """处理多问题批量提问，为每个问题创建独立 request_id 并等待所有回答"""
            import uuid as _uuid

            entries: list[tuple[str, asyncio.Event, list[str]]] = []
            ws = self._ws_send.get(session_id)

            # 为每个问题创建 request_id + event，并通过 WebSocket 发送
            for q in questions:
                request_id = f"ask_{_uuid.uuid4().hex[:8]}"
                event = asyncio.Event()
                self._pending_questions[request_id] = event
                self._pending_answers[request_id] = ""
                opts = q.get("options", [])
                entries.append((request_id, event, opts))

                if ws:
                    msg = make_ask_user_event(
                        session_id, "main",
                        question=q.get("question", ""),
                        header=q.get("header", "Question"),
                        options=opts,
                        multi=bool(q.get("multiSelect", False)),
                        request_id=request_id,
                    )
                    await ws(json.dumps(msg, ensure_ascii=False))

            # 并发等待所有回答（最多 5 分钟）
            events = [e for _, e, _ in entries]
            try:
                await asyncio.wait_for(
                    asyncio.gather(*(e.wait() for e in events)),
                    timeout=300,
                )
            except asyncio.TimeoutError:
                pass  # 超时的问题将回退到第一个选项

            # 收集答案，清理状态
            answers: list[str] = []
            for request_id, event, opts in entries:
                if event.is_set():
                    answers.append(self._pending_answers.pop(request_id, ""))
                else:
                    answers.append(opts[0] if opts else "")
                self._pending_questions.pop(request_id, None)
                self._pending_answers.pop(request_id, None)

            return answers

        ask_tool.bind_on_ask(on_ask)

    def answer_question(self, request_id: str, answer: str) -> bool:
        """处理用户对 AskUserQuestion 的回答"""
        event = self._pending_questions.get(request_id)
        if event is None:
            return False
        self._pending_answers[request_id] = answer
        event.set()
        return True

    # ------------------------------------------------------------------
    # 会话恢复
    # ------------------------------------------------------------------

    def _get_session_owner(self, session_id: str) -> int | None:
        """获取会话的 owner user_id。先查内存，再查数据库。"""
        owner = self._session_users.get(session_id)
        if owner is not None:
            return owner
        try:
            from ..dependencies import repository
            if repository.engine:
                from sqlalchemy import text
                with repository.engine.connect() as conn:
                    row = conn.execute(text(
                        "SELECT user_id FROM agent_sessions WHERE id = :id"
                    ), {"id": session_id}).fetchone()
                    if row:
                        owner = row[0]
                        self._session_users[session_id] = owner
                        return owner
        except Exception:
            logger.debug("Failed to query session owner from DB for %s", session_id)
        return None

    def _get_session_agent_type(self, session_id: str) -> str | None:
        """获取会话的 agent_type。先查内存，再查数据库。"""
        atype = self._agent_types.get(session_id)
        if atype is not None:
            return atype
        try:
            from ..dependencies import repository
            if repository.engine:
                from sqlalchemy import text
                with repository.engine.connect() as conn:
                    row = conn.execute(text(
                        "SELECT agent_type FROM agent_sessions WHERE id = :id"
                    ), {"id": session_id}).fetchone()
                    if row:
                        atype = row[0] or "simple"
                        self._agent_types[session_id] = atype
                        return atype
        except Exception:
            logger.debug("Failed to query session agent_type from DB for %s", session_id)
        return None

    async def restore_session(self, session_id: str, ws_send: Callable, *, user_id: int = 0) -> None:
        """恢复会话历史（仅允许恢复属于当前用户的会话）"""
        self._ws_send[session_id] = ws_send

        # 权限检查：会话必须属于当前用户
        session_owner = self._get_session_owner(session_id)
        if session_owner is not None and session_owner != user_id:
            await ws_send(json.dumps({
                "type": "agent_stream",
                "event": "error",
                "data": {"message": "无权访问此会话"},
            }, ensure_ascii=False))
            return

        from ..agent.config import get_agent_home
        session_dir = get_agent_home() / "sessions" / session_id
        context_file = session_dir / "context.jsonl"

        messages: list[dict] = []
        if context_file.exists():
            with open(context_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # 向后兼容：为旧记录补全 _meta
                    from ..agent.context import _ensure_meta
                    _ensure_meta(record)

                    role = record.get("role", "")
                    meta = record.get("_meta", {})
                    is_visible = meta.get("visible", True)

                    # 始终隐藏系统提示和用量统计
                    if role in ("_system_prompt", "_usage"):
                        continue
                    # 隐藏内部元数据标记（压缩/检查点）
                    if role in ("_checkpoint",):
                        continue
                    # 按可见性标志过滤
                    if not is_visible:
                        continue

                    messages.append(record)

        # _sub_agent 记录已在 context.jsonl 的 messages 中，由前端处理
        # 不再读取 agent_register.jsonl（该文件从未被写入）

        agent_type = self._agent_types.get(session_id, "simple")

        # Read plan mode state for the restored event
        import json as _json2
        plan_mode = False
        state_file = session_dir / "state.json"
        if state_file.exists():
            try:
                plan_mode = _json2.loads(state_file.read_text()).get("plan_mode", False)
            except (_json2.JSONDecodeError, OSError):
                pass

        msg = make_restored_event(session_id, "main", messages, [], plan_mode=plan_mode)
        await ws_send(json.dumps(msg, ensure_ascii=False))

        agent = await self._get_or_create_agent(session_id, agent_type)
        # 预加载上下文到 agent 内存。
        # 无论 agent._messages 是否为空都执行 restore：
        # - 页面刷新后 agent 可能仍在内存中但 _messages 与文件不一致
        # - Context.restore() 已改为幂等（清空后重新读取），可安全多次调用
        if hasattr(agent, "_context") and agent._context:
            try:
                await agent._context.restore()
                agent._messages = list(agent._context.history)
            except Exception:
                logger.warning("Failed to preload context for %s", session_id, exc_info=True)

    # ------------------------------------------------------------------
    # 会话列表（按用户过滤）
    # ------------------------------------------------------------------

    def list_sessions(self, *, user_id: int = 0) -> list[dict]:
        """列出当前用户的会话"""
        # 尝试从数据库获取用户会话列表
        db_sessions = self._list_sessions_from_db(user_id)
        if db_sessions is not None:
            return db_sessions

        # 回退：文件系统扫描（仅当 user_id=0 或无数据库时）
        return self._list_sessions_from_fs(user_id)

    def _list_sessions_from_db(self, user_id: int) -> list[dict] | None:
        """从数据库获取会话列表"""
        try:
            from ..dependencies import repository
            if not repository.engine:
                return None

            from sqlalchemy import text
            with repository.engine.connect() as conn:
                if user_id > 0:
                    rows = conn.execute(text(
                        "SELECT id, title, summary, agent_type, message_count, updated_at "
                        "FROM agent_sessions WHERE user_id = :uid AND agent_type != 'cron' "
                        "ORDER BY updated_at DESC"
                    ), {"uid": user_id}).fetchall()
                else:
                    return None  # 无 user_id 时不查数据库

            return [
                {
                    "id": r[0],
                    "title": r[1] or (r[2][:15] if r[2] else "") or "新对话",
                    "summary": r[2] or "",
                    "agent_type": r[3] or "simple",
                    "message_count": r[4] or 0,
                    "updated_at": r[5].isoformat() if r[5] else "",
                }
                for r in rows
            ]
        except Exception:
            logger.debug("DB session list failed, falling back to FS")
            return None

    def _list_sessions_from_fs(self, user_id: int) -> list[dict]:
        """从文件系统扫描会话（回退方案）"""
        from ..agent.config import get_agent_home
        sessions_dir = get_agent_home() / "sessions"
        if not sessions_dir.exists():
            return []

        result: list[dict] = []
        for d in sessions_dir.iterdir():
            if not d.is_dir():
                continue
            # 如果指定了 user_id，检查会话所有权
            if user_id > 0:
                owner = self._get_session_owner(d.name)
                if owner is not None and owner != user_id:
                    continue

            context_file = d / "context.jsonl"
            if not context_file.exists():
                continue

            # 从 meta.json 读取标题（如果有）
            title = d.name[:8]
            meta_file = d / "meta.json"
            agent_type = "simple"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    title = meta.get("title", "") or title
                    agent_type = meta.get("agent_type", "simple")
                except Exception:
                    pass

            # 跳过定时任务会话
            if agent_type == "cron":
                continue

            msg_count = 0
            summary = "(empty)"
            try:
                with open(context_file, encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                            # 向后兼容：补全 _meta
                            from ..agent.context import _ensure_meta
                            _ensure_meta(record)

                            role = record.get("role", "")
                            is_visible = record.get("_meta", {}).get("visible", True)

                            if role not in ("_system_prompt", "_usage") and is_visible:
                                msg_count += 1
                            if role == "user" and summary == "(empty)" and is_visible:
                                summary = str(record.get("_meta", {}).get(
                                    "raw_content", record.get("content", "")
                                ))[:80]
                        except json.JSONDecodeError:
                            pass
            except OSError:
                pass

            result.append({
                "id": d.name,
                "title": title,
                "summary": summary.replace("\n", " "),
                "message_count": msg_count,
                "updated_at": datetime.fromtimestamp(context_file.stat().st_mtime).isoformat(),
            })

        result.sort(key=lambda x: x["updated_at"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # 会话创建
    # ------------------------------------------------------------------

    def create_session(self, *, user_id: int = 0, agent_type: str = "simple") -> str:
        """创建新会话并关联用户"""
        session_id = "ag_" + uuid.uuid4().hex[:16]

        # 文件系统创建
        from ..agent.config import get_agent_home
        session_dir = get_agent_home() / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "context.jsonl").touch()

        # 内存中记录所有权
        if user_id:
            self._session_users[session_id] = user_id

        # 数据库记录
        self._save_session_to_db(session_id, user_id, agent_type=agent_type)

        return session_id

    def _save_session_to_db(self, session_id: str, user_id: int, agent_type: str = "simple") -> None:
        """保存会话元数据到数据库"""
        if not user_id:
            return
        try:
            from ..dependencies import repository
            if not repository.engine:
                return

            from sqlalchemy import text
            with repository.engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO agent_sessions (id, user_id, title, agent_type, message_count) "
                    "VALUES (:id, :uid, '', :atype, 0)"
                ), {"id": session_id, "uid": user_id, "atype": agent_type})
                conn.commit()
        except Exception:
            logger.debug("DB session save failed (non-critical)")

    def _update_session_meta(self, session_id: str, user_id: int, agent_type: str, summary: str,
                              content_length: int = 0) -> None:
        """更新会话元数据（如果会话不存在则自动创建 — 支持前端临时会话延迟持久化）

        Args:
            content_length: 本轮消息的字符数（用户消息 + 助手回复的总字符长度）
        """
        if not user_id:
            return
        try:
            from ..dependencies import repository
            if not repository.engine:
                return

            from sqlalchemy import text
            with repository.engine.connect() as conn:
                # 防止将 cron 类型降级为 simple（cron 会话不应出现在对话列表中）
                if agent_type == "simple":
                    row = conn.execute(text(
                        "SELECT agent_type FROM agent_sessions WHERE id = :id"
                    ), {"id": session_id}).fetchone()
                    if row and row[0] == "cron":
                        # 只更新 summary 和 message_count，保留 agent_type
                        conn.execute(text(
                            "UPDATE agent_sessions SET summary = :summary, "
                            "message_count = message_count + 1, "
                            "user_message_count = user_message_count + 1, "
                            "total_context_chars = total_context_chars + :chars, "
                            "updated_at = NOW() "
                            "WHERE id = :id AND user_id = :uid"
                        ), {"id": session_id, "uid": user_id, "summary": summary[:200], "chars": content_length})
                        conn.commit()
                        return

                result = conn.execute(text(
                    "UPDATE agent_sessions SET summary = :summary, agent_type = :atype, "
                    "message_count = message_count + 1, "
                    "user_message_count = user_message_count + 1, "
                    "total_context_chars = total_context_chars + :chars, "
                    "updated_at = NOW() "
                    "WHERE id = :id AND user_id = :uid"
                ), {"id": session_id, "uid": user_id, "summary": summary[:200], "atype": agent_type, "chars": content_length})
                # 行不存在（前端临时会话首次发送真实消息）→ 自动 INSERT
                if result.rowcount == 0:
                    conn.execute(text(
                        "INSERT INTO agent_sessions "
                        "(id, user_id, title, summary, agent_type, message_count, user_message_count, total_context_chars) "
                        "VALUES (:id, :uid, '', :summary, :atype, 1, 1, :chars)"
                    ), {
                        "id": session_id, "uid": user_id,
                        "summary": summary[:200], "atype": agent_type, "chars": content_length,
                    })
                conn.commit()
        except Exception:
            logger.debug("DB session meta update failed (non-critical)")

    async def _generate_session_title(self, session_id: str, first_message: str) -> None:
        """生成会话标题：短消息直接提取，长消息用 LLM 总结，LLM 失败时降级为截取"""
        try:
            text = first_message.strip()
            if not text:
                return

            title: str = ""

            # 短消息（<=15字）：直接提取第一行作为标题
            if len(text) <= 15:
                title = text.split('\n')[0].strip()
                title = title.strip('"\'""').strip()
            else:
                # 长消息：尝试用 LLM 生成简洁标题
                try:
                    from ..agent.llm import call_llm, create_llm
                    prompt = f"请为以下对话内容生成一个简洁的标题（不超过10个字，不要加引号）：\n{text[:300]}"

                    if self._small_llm is None:
                        # 小模型可能不在 API 白名单中，直接用主模型
                        model_name = self._small_model or "qwen3.6-plus"
                        self._small_llm = create_llm(
                            api_key=self._api_key,
                            base_url=self._base_url,
                            model_name=model_name,
                            api_mode=self._api_mode,
                        )

                    response = await call_llm(
                        messages=[{"role": "user", "content": prompt}],
                        tools=[],
                        llm=self._small_llm,
                    )

                    llm_title = response["choices"][0]["message"].get("content", "")
                    if llm_title and isinstance(llm_title, str):
                        title = llm_title.strip('"\'""').replace('\n', ' ').strip()
                        if len(title) > 20:
                            title = title[:20]
                except Exception as e:
                    logger.info("LLM title generation failed for %s, falling back to truncation: %s", session_id, e)

                # LLM 失败或返回空：降级为截取消息前 15 字
                if not title:
                    title = text[:15].strip().strip('"\'""')

            if not title:
                return

            self._save_title_to_file(session_id, title)

            try:
                from ..dependencies import repository
                if repository.engine:
                    from sqlalchemy import text
                    with repository.engine.connect() as conn:
                        conn.execute(text(
                            "UPDATE agent_sessions SET title = :title WHERE id = :id"
                        ), {"id": session_id, "title": title})
                        conn.commit()
            except Exception:
                logger.warning("DB title update failed for %s", session_id)

            ws_send = self._ws_send.get(session_id)
            if ws_send:
                await ws_send(json.dumps({
                    "type": "agent_stream",
                    "event": "session_title_updated",
                    "data": {"session_id": session_id, "title": title},
                }, ensure_ascii=False))

            logger.info("Generated title for session %s: %s", session_id, title)

        except Exception as e:
            logger.warning("Failed to generate session title for %s: %s", session_id, e)

    def _save_title_to_file(self, session_id: str, title: str) -> None:
        """将标题保存到会话目录的 meta.json"""
        try:
            from ..agent.config import get_agent_home
            session_dir = get_agent_home() / "sessions" / session_id
            meta_file = session_dir / "meta.json"

            meta = {}
            if meta_file.exists():
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)

            meta["title"] = title

            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.debug("Failed to save title to file for %s", session_id)

    def _read_title_from_file(self, session_id: str) -> str:
        """从会话目录的 meta.json 读取标题"""
        try:
            from ..agent.config import get_agent_home
            meta_file = get_agent_home() / "sessions" / session_id / "meta.json"
            if meta_file.exists():
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)
                return meta.get("title", "")
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # 会话所有权
    # ------------------------------------------------------------------

    # _get_session_owner 定义见上文 restore_session 之前


    # ------------------------------------------------------------------
    # Cron 事件广播
    # ------------------------------------------------------------------

    def register_user_connection(self, user_id: int, ws_send: Callable) -> None:
        """注册用户的 WebSocket 连接（用于 cron 等用户级通知）。"""
        if user_id <= 0:
            return
        self._user_connections.setdefault(user_id, set()).add(ws_send)

    def unregister_user_connection(self, user_id: int, ws_send: Callable) -> None:
        """移除用户的 WebSocket 连接。"""
        conns = self._user_connections.get(user_id)
        if conns:
            conns.discard(ws_send)
            if not conns:
                del self._user_connections[user_id]

    async def broadcast_cron_event(self, user_id: int, event: str, data: dict) -> None:
        """向指定用户的所有 WS 连接广播 cron 事件。"""
        conns = list(self._user_connections.get(user_id, set()))
        if not conns:
            return
        import json
        msg = json.dumps({
            "type": "cron_event",
            "event": event,
            "data": data,
        }, ensure_ascii=False)
        dead: list[Callable] = []
        for ws_send in conns:
            try:
                await ws_send(msg)
            except Exception:
                dead.append(ws_send)
        for cb in dead:
            self.unregister_user_connection(user_id, cb)


    # ------------------------------------------------------------------
    # 会话删除 / 重命名
    # ------------------------------------------------------------------

    async def delete_session(self, session_id: str, *, user_id: int = 0) -> bool:
        """删除会话（文件 + 数据库 + 内存）"""
        # 权限检查
        session_owner = self._get_session_owner(session_id)
        if session_owner is not None and session_owner != user_id:
            return False

        # 1. 清理内存
        self.cleanup(session_id)

        # 2. 删除文件系统
        try:
            from ..agent.config import get_agent_home
            import shutil
            session_dir = get_agent_home() / "sessions" / session_id
            if session_dir.exists():
                shutil.rmtree(session_dir)
        except Exception:
            logger.debug("FS session delete failed for %s", session_id)

        # 3. 删除数据库记录（级联删除 messages）
        try:
            from ..dependencies import repository
            if repository.engine:
                from sqlalchemy import text
                with repository.engine.connect() as conn:
                    if user_id > 0:
                        conn.execute(text(
                            "DELETE FROM agent_sessions WHERE id = :id AND user_id = :uid"
                        ), {"id": session_id, "uid": user_id})
                    else:
                        conn.execute(text(
                            "DELETE FROM agent_sessions WHERE id = :id"
                        ), {"id": session_id})
                    conn.commit()
        except Exception:
            logger.debug("DB session delete failed for %s", session_id)

        return True

    async def rename_session(self, session_id: str, title: str, *, user_id: int = 0) -> bool:
        """重命名会话"""
        # 权限检查
        session_owner = self._get_session_owner(session_id)
        if session_owner is not None and session_owner != user_id:
            return False

        # 保存到文件
        self._save_title_to_file(session_id, title)

        # 更新数据库
        try:
            from ..dependencies import repository
            if repository.engine:
                from sqlalchemy import text
                with repository.engine.connect() as conn:
                    if user_id > 0:
                        conn.execute(text(
                            "UPDATE agent_sessions SET title = :title WHERE id = :id AND user_id = :uid"
                        ), {"id": session_id, "title": title, "uid": user_id})
                    else:
                        conn.execute(text(
                            "UPDATE agent_sessions SET title = :title WHERE id = :id"
                        ), {"id": session_id, "title": title})
                    conn.commit()
        except Exception:
            logger.warning("DB session rename failed for %s", session_id)
            return False

        # 通过 WebSocket 通知前端
        ws_send = self._ws_send.get(session_id)
        if ws_send:
            try:
                await ws_send(json.dumps({
                    "type": "agent_stream",
                    "event": "session_title_updated",
                    "data": {"session_id": session_id, "title": title},
                }, ensure_ascii=False))
            except Exception:
                pass

        return True

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def cleanup(self, session_id: str) -> None:
        self._agents.pop(session_id, None)
        self._agent_types.pop(session_id, None)
        self._ws_send.pop(session_id, None)
        self._session_users.pop(session_id, None)
        task = self._tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    def evict_agent(self, session_id: str) -> None:
        """Evict agent from cache so it's recreated with current plan mode tools.

        Called after plan mode is toggled. Context is preserved in
        context.jsonl and will be restored when the agent is recreated
        on the next message.
        """
        self._agents.pop(session_id, None)
        logger.info("Evicted agent for session %s (plan mode toggle)", session_id)

    # ------------------------------------------------------------------
    # 记忆提取（异步后台任务）
    # ------------------------------------------------------------------

    async def _extract_memories_background(
        self,
        user_id: int,
        conversation_buffer: list[dict],
    ) -> None:
        """异步提取记忆（在后台任务中运行，不阻塞用户）。"""
        try:
            from .memory_service import memory_service
            from .memory_extractor import extract_memories_from_conversation

            llm_config = {
                "model": self._model,
                "base_url": self._base_url,
                "api_key": self._api_key,
                "api_mode": self._api_mode,
            }

            result = await extract_memories_from_conversation(
                user_id=user_id,
                messages=conversation_buffer,
                llm_config=llm_config,
                memory_service=memory_service,
            )

            logger.info(
                "Background memory extraction for user %d: "
                "profile_updated=%s, memories_added=%d",
                user_id,
                result.get("profile_updated", False),
                result.get("memories_added", 0),
            )
        except Exception:
            logger.exception(
                "Background memory extraction failed for user %d", user_id,
            )


agent_manager = AgentManager()



