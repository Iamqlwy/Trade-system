"""通用 Agent — 异步对话循环 + 流式输出 + 工具执行 + 上下文压缩

来自 simple-agent/agent/core.py — AIAgent 类

功能：
  - 流式 LLM 调用（OpenAI + Anthropic）
  - 工具执行循环
  - 上下文自动压缩
  - 会话持久化
  - 中断支持
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

from app.agent.llm import call_llm_stream, LLM, create_llm
from app.agent.agents.prompts import build_system_prompt
from app.agent.context import Context
from app.agent.tools.base import ToolRegistry, ToolError  # noqa: F401
from app.agent.tools import register_all_tools

logger = logging.getLogger(__name__)

# 模型上下文窗口（用于压缩阈值计算）
_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o": 128000, "gpt-4-turbo": 128000, "gpt-4": 8192,
    "gpt-3.5-turbo": 16385, "gpt-4o-mini": 128000,
    "claude-opus-4": 200000, "claude-sonnet-4": 200000, "claude-haiku-4": 200000,
    "claude-3-opus": 200000, "claude-3-sonnet": 200000, "claude-3-haiku": 200000,
    "claude-3.5-sonnet": 200000, "claude-3.5-haiku": 200000,
    "deepseek-v3": 131072, "deepseek-r1": 131072,
    "gemini-2.0": 1048576, "gemini-1.5": 2097152,
    "qwen": 131072, "llama": 131072,
}


def _get_context_threshold(model: str) -> int:
    """返回模型上下文窗口的 80%"""
    model_lower = model.lower()
    for prefix, window in _MODEL_CONTEXT_WINDOWS.items():
        if prefix in model_lower:
            return int(window * 0.8)
    return int(os.getenv("CONTEXT_THRESHOLD", "100000"))


class SimpleAgent:
    """通用对话 Agent（流式）"""

    def __init__(
        self,
        model: str = "qwen3.6-plus",
        base_url: str = "",
        api_key: str = "",
        api_mode: str = "chat",
        max_iterations: int = 50,
        tool_registry: Optional[ToolRegistry] = None,
        event_callback: Optional[Callable] = None,
        context_file: Optional[Path] = None,
        enabled_tool_classes: Optional[set[str]] = None,
        todo_store: Optional[Any] = None,
        user_id: int = 0,
        workspace: Optional[Path] = None,
        session_id: Optional[str] = None,
        memory_service: Optional[Any] = None,
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.api_mode = api_mode
        self.max_iterations = max_iterations
        self._event_cb = event_callback
        self._context_file = context_file  # 保存 context_file 路径
        self._user_id = user_id
        self._workspace = workspace
        self._session_id = session_id

        # 创建工作区目录
        if workspace is not None:
            workspace.mkdir(parents=True, exist_ok=True)

        # 记忆系统（仅 DB 模式，通过 memory_service 操作 MySQL）
        self._memory_service = memory_service

        # 任务存储
        if todo_store is not None:
            self._todo_store = todo_store
        else:
            from app.agent.tools.todo import TodoStore
            self._todo_store = TodoStore()

        # 工具注册表：每个 Agent 创建自己的注册表（确保 Agent 工具有正确的 event_callback）
        if tool_registry is not None:
            self._registry = tool_registry
        else:
            self._registry = ToolRegistry()
            register_all_tools(
                reg=self._registry,
                work_dir=workspace,
                event_callback=event_callback,
                model=model,
                base_url=base_url,
                api_key=api_key,
                api_mode=api_mode,
                context_file=str(context_file) if context_file else None,
                enabled_tool_classes=enabled_tool_classes,
                memory_service=self._memory_service,
                todo_store=self._todo_store,
                user_id=self._user_id,
                session_id=self._session_id or "",
            )

        self._messages: list[dict[str, Any]] = []
        self._system_prompt: str = ""
        self._interrupt_requested = False
        self._task_id = os.urandom(4).hex()

        # 持久化上下文（写入 context.jsonl 以便恢复会话）
        self._context: Optional[Context] = None
        if context_file is not None:
            self._context = Context(context_file)

        # ── 记忆提取追踪 ──
        self._memory_signal_count: int = 0
        self._user_turns_count: int = 0
        self._conversation_buffer: list[dict[str, Any]] = []

    @property
    def messages(self) -> list[dict]:
        return self._messages

    def request_interrupt(self) -> None:
        self._interrupt_requested = True

    def fix_orphaned_tool_calls(self) -> None:
        """中断后修复上下文：为缺少结果的 tool_call 补充合成结果。

        场景：用户在工具执行期间中断，assistant 消息包含 tool_calls，
        但部分或全部 tool result 尚未写入 _messages。这会导致 LLM API
        在下一轮调用时报错（tool_calls 无对应 tool 结果）。
        """
        # 收集已有结果的 tool_call_id
        completed_ids: set[str] = set()
        for msg in self._messages:
            if msg.get("role") == "tool" and "tool_call_id" in msg:
                completed_ids.add(msg["tool_call_id"])

        # 从后往前找最近的带 tool_calls 的 assistant 消息
        orphans: list[dict] = []
        for msg in reversed(self._messages):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tc_id = tc.get("id", "")
                    if tc_id and tc_id not in completed_ids:
                        orphans.append(tc)
                break  # 只处理最近一条

        if not orphans:
            return

        logger.info(
            "Session %s: fixing %d orphaned tool_call(s) after interrupt",
            self._session_id, len(orphans),
        )

        synthetic_results: list[dict] = []
        for tc in orphans:
            tc_id = tc.get("id", "")
            func_name = tc.get("function", {}).get("name", "unknown")
            synthetic_results.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": json.dumps({
                    "interrupted": True,
                    "message": f"Tool execution of '{func_name}' was interrupted by the user. "
                               "The result is unavailable. If the user wants to retry, "
                               "you may call this tool again.",
                }),
            })

        # 追加到内存消息列表
        self._messages.extend(synthetic_results)

        # 持久化到 context.jsonl
        if self._context is not None:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._context.append_message(synthetic_results, meta={
                        "visible": True, "category": "tool",
                    })
                )
            except RuntimeError:
                pass

    def _emit(self, event: str, data: dict) -> None:
        """发送事件到回调"""
        if self._event_cb:
            self._event_cb(event, data)

    def _build_system_prompt(self) -> str:
        """构建完整的系统提示（集成 skills、memory、todo）。"""
        from app.agent.skills import build_catalog

        # Skills 目录（Tier 1）— 传入 user_id 扫描用户级+官方目录
        skills_catalog = build_catalog(self._user_id)

        # Memory 块：通过 memory_service 从 MySQL 读取（结构化画像 + 笔记）
        memory_block = ""
        user_block = ""
        if self._memory_service and self._user_id > 0:
            profile_block = self._memory_service.format_profile_for_prompt(self._user_id)
            memories_block = self._memory_service.format_memories_for_prompt(self._user_id)
            if profile_block:
                memory_block = profile_block
            if memories_block:
                user_block = memories_block

        # 构建主提示
        plan_mode_active = False
        if self._context_file:
            state_file = self._context_file.parent / "state.json"
            if state_file.exists():
                try:
                    plan_mode_active = json.loads(state_file.read_text()).get("plan_mode", False)
                except (json.JSONDecodeError, OSError):
                    pass

        prompt = build_system_prompt(
            skills_catalog=skills_catalog,
            memory_block=memory_block,
            user_block=user_block,
            workdir=str(self._workspace) if self._workspace else None,
            workspace=str(self._workspace) if self._workspace else None,
            agent_type="simple",
            session_token=self._session_id,
            plan_mode=plan_mode_active,
        )

        # 注入活跃任务列表（跨压缩保持）
        if self._todo_store:
            todo_block = self._todo_store.format_for_injection()
            if todo_block:
                prompt += f"\n\n{todo_block}"

        return prompt

    async def run(self, user_message: "str | list") -> dict[str, Any]:
        """执行一轮完整对话"""
        self._interrupt_requested = False
        try:
            return await self._run_conversation(user_message)
        finally:
            self._interrupt_requested = False

    async def _run_conversation(self, user_message: "str | list") -> dict[str, Any]:
        # 构建完整的系统提示（包含 skills、memory、todo）
        self._system_prompt = self._build_system_prompt()
        tools = self._registry.get_all_schemas()

        # 恢复已有上下文（如果存在）
        if self._context is not None and not self._messages:
            await self._context.restore()
            self._messages = list(self._context.history)

        user_msg = {"role": "user", "content": user_message}
        messages = [
            {"role": "system", "content": self._system_prompt},
            *self._messages,
            user_msg,
        ]
        self._messages.append(user_msg)
        if self._context is not None:
            await self._context.append_message(user_msg, meta={
                "visible": True, "category": "user", "raw_content": user_message,
            })

        # ── 记忆信号追踪 ──
        self._user_turns_count += 1
        user_text = user_message if isinstance(user_message, str) else " ".join(
            p.get("text", "") for p in user_message if isinstance(p, dict) and p.get("type") == "text"
        ) if isinstance(user_message, list) else str(user_message)
        from app.services.memory_extractor import count_memory_signals
        self._memory_signal_count += count_memory_signals(user_text)
        self._conversation_buffer.append(user_msg)

        llm = create_llm(
            api_key=self.api_key,
            base_url=self.base_url,
            model_name=self.model,
            api_mode=self.api_mode,
        )

        total_api_calls = 0

        for turn in range(self.max_iterations):
            if self._interrupt_requested:
                return {"final_response": "[Interrupted by user]", "turns": turn, "interrupted": True}

            self._emit("thinking", {"turn": turn + 1})

            # 流式 LLM 调用
            try:
                msg = await self._stream_llm(messages, tools, llm)
                total_api_calls += 1
            except Exception as e:
                logger.exception("LLM call failed on turn %d", turn)
                self._emit("error", {"message": str(e)})
                return {"final_response": f"API error: {e}", "turns": turn, "error": True}

            # 没有工具调用 → 对话结束
            if not msg.get("tool_calls"):
                messages.append(msg)
                self._messages.append(msg)
                if self._context is not None:
                    await self._context.append_message(msg, meta={
                        "visible": True, "category": "assistant",
                    })

                # 将助手回复加入对话缓冲
                self._conversation_buffer.append(msg)

                # 判断是否需要触发记忆提取
                needs_extraction = self._should_extract_memory()

                return {
                    "final_response": msg.get("content", ""),
                    "turns": turn + 1,
                    "api_calls": total_api_calls,
                    "needs_memory_extraction": needs_extraction,
                    "conversation_buffer": self._conversation_buffer if needs_extraction else [],
                }

            # 执行工具
            tool_msgs = await self._execute_tools(msg["tool_calls"], llm)
            messages.append(msg)
            self._messages.append(msg)
            messages.extend(tool_msgs)
            self._messages.extend(tool_msgs)
            if self._context is not None:
                await self._context.append_message(msg, meta={
                    "visible": True, "category": "assistant",
                })
                await self._context.append_message(tool_msgs, meta={
                    "visible": True, "category": "tool",
                })

            # 上下文压缩检查
            if self._estimate_tokens(messages) > _get_context_threshold(self.model):
                messages = await self._compress_context(messages, llm)
                self._messages = messages[1:]

        return {"final_response": "Reached maximum iterations.", "turns": self.max_iterations, "limit": True}

    def _should_extract_memory(self) -> bool:
        """判断是否应触发记忆提取。

        触发条件（满足任一）：
          - 关键词信号数 >= 3
          - 用户消息轮次 >= 8 且信号数 >= 1
        不触发时对话缓冲清空，不浪费 LLM 算力。
        """
        if self._memory_signal_count >= 3:
            return True
        if self._user_turns_count >= 8 and self._memory_signal_count >= 1:
            return True
        # 不触发：清空缓冲区
        self._conversation_buffer.clear()
        return False

    async def _stream_llm(self, messages: list[dict], tools: list[dict], llm: LLM) -> dict:
        """流式调用 LLM，转发 token 事件，返回完整消息（带 5 分钟整体超时）"""
        final_message: dict = {}

        try:
            async with asyncio.timeout(300):
                async for event in call_llm_stream(messages, tools, llm):
                    ev_type = event.get("type")

                    if ev_type == "delta":
                        self._emit("token", {"content": event["content"]})

                    elif ev_type == "tool_call_delta":
                        # 工具调用增量 — 前端可选展示
                        self._emit("tool_call_delta", {
                            "index": event["index"],
                            "id": event.get("id", ""),
                            "name": event.get("name", ""),
                            "arguments": event.get("arguments", ""),
                        })

                    elif ev_type == "done":
                        final_message = event["message"]

                    elif ev_type == "error":
                        raise RuntimeError(event.get("message", "LLM stream error"))
        except asyncio.TimeoutError:
            logger.warning("LLM stream timed out after 300s")
            raise RuntimeError("LLM 请求超时（5分钟），请重试")

        # 流结束但没有 done 事件（连接中断等）— 返回安全默认值
        if not final_message:
            logger.warning("LLM stream ended without done event")
            final_message = {"role": "assistant", "content": "[Stream ended unexpectedly]"}

        return final_message

    async def _execute_tools(self, tool_calls: list[dict], llm: LLM) -> list[dict]:  # noqa: ARG002
        """执行工具调用并返回结果消息"""
        results: list[dict] = []

        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            args_str = func.get("arguments", "{}")

            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}

            tool_call_id = tc.get("id", "")
            self._emit("tool_start", {
                "tool_call_id": tool_call_id,
                "name": name,
                "args": args,
            })

            logger.debug("Tool call: %s %s", name, str(args)[:200])

            task = self._registry.handle(tc)
            tool_result = await task

            is_error = tool_result.is_error

            # 检查工具返回结果是否包含图片（如 ReadFile 读取图片文件）
            images: list[dict] = []
            if not is_error and isinstance(tool_result.return_value, dict):
                images = tool_result.return_value.get("images", [])

            result_str: str
            if is_error:
                rv = tool_result.return_value
                if isinstance(rv, ToolError):
                    result_str = json.dumps({"error": rv.message}, ensure_ascii=False)
                elif isinstance(rv, dict):
                    error_msg = rv.get("message") or rv.get("error") or "Unknown error"
                    result_str = json.dumps({"error": str(error_msg)}, ensure_ascii=False)
                else:
                    result_str = json.dumps({"error": str(rv)}, ensure_ascii=False)
            else:
                val = tool_result.return_value
                result_str = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False, default=str)

            preview = result_str[:200] + "..." if len(result_str) > 200 else result_str
            self._emit("tool_end", {
                "tool_call_id": tool_call_id,
                "name": name,
                "preview": preview,
                "is_error": is_error,
            })

            # 构建工具结果消息（有图片时使用多模态 content）
            if images:
                content_parts: list[dict] = []
                if result_str:
                    content_parts.append({"type": "text", "text": result_str})
                for img in images:
                    img_url = img.get("url", "")
                    if img_url:
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": img_url},
                        })
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": content_parts if content_parts else result_str,
                })
            else:
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_str,
                })

        return results

    def _estimate_tokens(self, messages: list[dict]) -> int:
        total_chars = sum(len(str(msg)) for msg in messages)
        return (total_chars + 3) // 4

    async def _compress_context(self, messages: list[dict], llm: LLM) -> list[dict]:
        """通过 LLM 摘要压缩中间消息（非流式），并持久化完整压缩后上下文到 context"""
        if len(messages) <= 6:
            return messages

        system = messages[0]
        recent = messages[-4:]
        middle = messages[1:-4]

        if len(middle) < 2:
            return messages

        # 构建中间消息的文本表示（保留角色信息）
        middle_text = []
        for m in middle:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, str):
                text = content[:500]
            elif isinstance(content, list):
                text = str(content)[:500]
            else:
                text = str(content)[:500]
            middle_text.append(f"[{role}]: {text}")

        summary_prompt = (
            "Summarize the key actions, findings, and decisions from this "
            "conversation fragment. Be concise but include all important details:\n\n"
            + "\n".join(middle_text)
        )

        try:
            # 压缩用非流式更简单
            from app.agent.llm import call_llm as async_call_llm
            summary_resp = await async_call_llm(
                messages=[{"role": "user", "content": summary_prompt}],
                tools=[],
                llm=llm,
            )
            summary = summary_resp["choices"][0]["message"].get("content", "")
        except Exception:
            summary = f"[{len(middle)} messages compressed]"

        # 构建完整的压缩后上下文
        compressed_messages = [
            system,
            {"role": "user", "content": f"[Context compressed — {len(middle)} turns summarized]\n\n{summary}"},
        ]
        compressed_messages.extend(recent)

        # 压缩后重新注入活跃任务列表（跨压缩保持连续性）
        if self._todo_store:
            todo_block = self._todo_store.format_for_injection()
            if todo_block:
                compressed_messages[1]["content"] += f"\n\n{todo_block}"

        # 持久化完整的压缩后上下文到 context.jsonl
        if self._context is not None:
            compact_record = {
                "role": "_compact",
                "compressed_messages": compressed_messages,  # 完整的压缩后上下文
                "compressed_count": len(middle),
                "_meta": {"visible": False, "category": "metadata"},
            }
            await self._context.append_message(compact_record)

        logger.info("Context compressed: %d -> %d messages", len(messages), len(compressed_messages))
        return compressed_messages
