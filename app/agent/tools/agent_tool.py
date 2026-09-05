"""子 Agent 委托工具 — 唯一用于委派任务给子 Agent 的工具。

功能：
  - 将任务委派给专门的子 Agent 执行
  - 子 Agent 类型：general-purpose, explore, plan, researcher
  - 子 Agent 有独立的工具集和上下文
  - 返回子 Agent 的执行结果
  - 通过 event_callback 发送子 agent 事件到前端
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Callable, Optional

from app.agent.tools.base import Tool, ToolParam

logger = logging.getLogger(__name__)

# 子 agent 类型的中文标签
_SUBAGENT_LABELS = {
    "general-purpose": "通用助手",
    "explore": "代码探索",
    "plan": "方案规划",
    "researcher": "研究分析",
}


class Agent(Tool):
    """委派任务给子 Agent"""

    name = "Agent"
    description = (
        "Delegate a task to a specialized subagent. "
        "Use for parallel work, research, or complex analysis. "
        "Available subagent types: "
        "'general-purpose' (full coding tools + shell), "
        "'explore' (read-only codebase search), "
        "'plan' (architecture and implementation planning), "
        "'researcher' (web research and reports). "
        "The subagent runs independently and returns its findings."
    )

    def __init__(
        self,
        work_dir: Optional[Path] = None,
        model: str = "qwen3.6-plus",
        base_url: str = "",
        api_key: str = "",
        api_mode: str = "chat",
        event_callback: Optional[Callable] = None,
        session_id: str = "",
        context_file: Optional[str] = None,  # 新增：主会话的 context 文件路径
    ):
        self._work_dir = work_dir
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._api_mode = api_mode
        self._event_cb = event_callback
        self._session_id = session_id
        self._context_file = context_file

    parameters = [
        ToolParam("description", str, "Short (3-5 word) description of the task."),
        ToolParam("prompt", str, "The task for the subagent to perform. Be specific and detailed."),
        ToolParam(
            "subagent_type", str,
            "Type: 'general-purpose', 'explore', 'plan', 'researcher'.",
            default="general-purpose", required=False,
        ),
    ]

    def _emit(self, event: str, data: dict) -> None:
        """发送子 agent 事件到前端"""
        if self._event_cb:
            self._event_cb(event, data)

    async def call(self, arguments: dict) -> dict:
        description = arguments.get("description", "")
        prompt = arguments.get("prompt", "")
        subagent_type = arguments.get("subagent_type", "general-purpose")

        if not prompt:
            return {"is_error": True, "message": "Prompt cannot be empty."}

        sub_agent_id = f"sub_{uuid.uuid4().hex[:8]}"
        label = _SUBAGENT_LABELS.get(subagent_type, subagent_type)

        # 子 agent 的 context 文件路径（相对于 session 目录）
        context_file = f"subagents/{sub_agent_id}.jsonl"

        # 发送 spawned 事件（包含 context_file）
        self._emit("sub_agent", {
            "sub_agent_id": sub_agent_id,
            "action": "spawned",
            "sub_agent_type": subagent_type,
            "task_description": description or prompt[:100],
            "label": f"{label}: {description}" if description else label,
            "context_file": context_file,
        })

        try:
            from app.agent.subagents.runner import run_subagent

            # 获取 session 目录（从 context_file 推导）
            session_dir = None
            if self._context_file:
                session_dir = Path(self._context_file).parent

            # 创建一个包装的 event_callback，将子 agent 的事件标记 sub_agent_id
            def sub_event_cb(event: str, data: dict) -> None:
                data["sub_agent_id"] = sub_agent_id
                self._emit(event, data)

            result, actual_sub_id, saved_context_file = await run_subagent(
                prompt=prompt,
                subagent_type=subagent_type,
                description=description,
                work_dir=self._work_dir,
                model=self._model,
                base_url=self._base_url,
                api_key=self._api_key,
                api_mode=self._api_mode,
                event_callback=sub_event_cb,
                session_dir=session_dir,
            )

            # 发送 completed 事件（包含 context_file）
            output_text = result or ""
            summary = output_text[:200].replace("\n", " ").strip() if output_text else ""
            self._emit("sub_agent", {
                "sub_agent_id": sub_agent_id,
                "action": "completed",
                "sub_agent_type": subagent_type,
                "result_summary": summary,
                "status": "completed",
                "context_file": saved_context_file or context_file,
            })

            return {"is_error": False, "message": "Subagent completed.", "output": output_text}
        except Exception as e:
            logger.exception("Subagent failed")
            self._emit("sub_agent", {
                "sub_agent_id": sub_agent_id,
                "action": "completed",
                "sub_agent_type": subagent_type,
                "status": "error",
                "result_summary": f"错误：{e}",
            })
            return {"is_error": True, "message": f"Subagent failed: {e}"}
