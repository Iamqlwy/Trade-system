"""Memory 工具 — 持久化记忆，跨会话保持（MySQL 后端）。

通过 memory_service 操作 user_memories 表，实现结构化记忆管理。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent.tools.base import Tool, ToolParam

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Memory Tool — Tool 基类封装
# ---------------------------------------------------------------------------

class Memory(Tool):
    """持久化记忆工具（DB 模式）。

    通过 memory_service 写入/读取 MySQL user_memories 表。
    """

    name = "memory"
    description = (
        "Save durable information to persistent memory that survives across sessions. "
        "Use proactively for user preferences, trading observations, and lessons learned. "
        "Actions: add, remove."
    )

    parameters = [
        ToolParam("action", str, "Action: add, remove."),
        ToolParam("content", str, "Entry content for add.", default="", required=False),
        ToolParam("old_text", str, "Substring to match for remove.", default="", required=False),
    ]

    def __init__(
        self,
        memory_service: Any | None = None,
        user_id: int = 0,
    ):
        self._service = memory_service
        self._user_id = user_id

    def bind_service(self, service: Any, user_id: int = 0) -> None:
        """绑定 MemoryService 实例。"""
        self._service = service
        self._user_id = user_id

    async def call(self, arguments: dict) -> dict:
        action = arguments.get("action", "")
        content = arguments.get("content", "")
        old_text = arguments.get("old_text", "")

        if self._service is None or self._user_id <= 0:
            return {"is_error": True, "message": "Memory not available."}

        return self._call_db(action, content, old_text)

    def _call_db(self, action: str, content: str, old_text: str) -> dict:
        """DB 模式：通过 memory_service 操作"""
        assert self._service is not None
        try:
            if action == "add":
                if not content:
                    return {"is_error": True, "message": "content is required for 'add'."}
                result = self._service.add_memory(
                    self._user_id, "observation", content, source="auto",
                )
                return {
                    "is_error": False,
                    "output": json.dumps(result, ensure_ascii=False),
                    "message": "Memory saved.",
                }

            elif action == "remove":
                if not old_text:
                    return {"is_error": True, "message": "old_text is required for 'remove'."}
                # 模糊匹配：查找包含 old_text 的记忆
                memories = self._service.get_memories(self._user_id, limit=200)
                matched = [m for m in memories if old_text in m["content"]]
                if not matched:
                    return {"is_error": True, "message": f"No memory matched '{old_text}'."}
                if len(matched) > 1:
                    names = [m["content"][:30] for m in matched[:5]]
                    return {
                        "is_error": True,
                        "message": f"Multiple memories matched: {names}. Be more specific.",
                    }
                self._service.remove_memory(self._user_id, matched[0]["id"])
                return {"is_error": False, "message": "Memory removed."}

            else:
                return {"is_error": True, "message": f"Unknown action '{action}'. Use: add, remove."}

        except Exception as e:
            return {"is_error": True, "message": f"Memory operation failed: {e}"}
