"""Todo 工具 — 任务列表管理。

合并两个来源：
  - code/code_agent/tools/todo/ — TodoWrite 类（OOP 风格，JSON 输入）
  - code/simple-agent/tools/todo.py — TodoStore（内存任务跟踪 + merge 支持）

功能：
  - 创建/更新/查看任务列表
  - 支持 pending/in_progress/completed/cancelled 状态
  - merge 模式：按 id 增量更新
  - 上下文压缩时注入活跃任务列表
"""

from __future__ import annotations

import json
from typing import Any

from app.agent.tools.base import Tool, ToolParam


VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}


# ---------------------------------------------------------------------------
# TodoStore — 内存任务存储（来自 simple-agent）
# ---------------------------------------------------------------------------

class TodoStore:
    """内存任务存储，支持 merge 更新和上下文注入。"""

    def __init__(self):
        self._items: list[dict[str, str]] = []

    def write(self, todos: list[dict[str, Any]], merge: bool = False) -> list[dict[str, str]]:
        if not merge:
            self._items = [self._validate(t) for t in self._dedupe_by_id(todos)]
        else:
            existing = {item["id"]: item for item in self._items}
            for t in self._dedupe_by_id(todos):
                item_id = str(t.get("id", "")).strip()
                if not item_id:
                    continue
                if item_id in existing:
                    if "content" in t and t["content"]:
                        existing[item_id]["content"] = str(t["content"]).strip()
                    if "status" in t and t["status"]:
                        status = str(t["status"]).strip().lower()
                        if status in VALID_STATUSES:
                            existing[item_id]["status"] = status
                else:
                    validated = self._validate(t)
                    existing[validated["id"]] = validated
                    self._items.append(validated)
            seen: set[str] = set()
            rebuilt: list[dict[str, str]] = []
            for item in self._items:
                current = existing.get(item["id"], item)
                if current["id"] not in seen:
                    rebuilt.append(current)
                    seen.add(current["id"])
            self._items = rebuilt
        return self.read()

    def read(self) -> list[dict[str, str]]:
        return [item.copy() for item in self._items]

    def format_for_injection(self) -> str | None:
        """格式化活跃任务列表，用于注入上下文压缩后的提示词"""
        active = [i for i in self._items if i["status"] in ("pending", "in_progress")]
        if not active:
            return None
        markers = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]", "cancelled": "[~]"}
        lines = ["[Active task list preserved across context compression]"]
        for item in active:
            m = markers.get(item["status"], "[?]")
            lines.append(f"- {m} {item['id']}. {item['content']} ({item['status']})")
        return "\n".join(lines)

    @staticmethod
    def _validate(item: dict[str, Any]) -> dict[str, str]:
        item_id = str(item.get("id", "")).strip() or "?"
        content = str(item.get("content", "")).strip() or "(no description)"
        status = str(item.get("status", "pending")).strip().lower()
        if status not in VALID_STATUSES:
            status = "pending"
        return {"id": item_id, "content": content, "status": status}

    @staticmethod
    def _dedupe_by_id(todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        last_index: dict[str, int] = {}
        for i, item in enumerate(todos):
            item_id = str(item.get("id", "")).strip() or "?"
            last_index[item_id] = i
        return [todos[i] for i in sorted(last_index.values())]


# ---------------------------------------------------------------------------
# TodoWrite — OOP 风格工具（来自 code_agent）
# ---------------------------------------------------------------------------

class TodoWrite(Tool):
    """任务列表管理工具。

    接受 JSON 数组格式的任务列表，支持 id/subject/status 字段。
    当提供 TodoStore 时，使用 Store 作为后端（支持 merge 和注入）。
    """

    name = "TodoWrite"
    description = "Create and manage a structured task list for tracking progress."

    def __init__(self, todo_store: TodoStore | None = None):
        self._store = todo_store
        self._todos: list[dict] = []

    parameters = [
        ToolParam("todos", str, "JSON array of todo items with id, subject, status fields."),
    ]

    async def call(self, arguments: dict) -> dict:
        todos_str = arguments.get("todos", "[]")
        try:
            todos = json.loads(todos_str)
        except json.JSONDecodeError:
            return {"is_error": True, "message": "Invalid JSON for todos."}

        # 如果有 TodoStore，同步写入 store
        if self._store is not None:
            store_items = []
            for t in todos:
                store_items.append({
                    "id": str(t.get("id", t.get("subject", "?"))),
                    "content": str(t.get("subject", t.get("content", ""))),
                    "status": str(t.get("status", "pending")),
                })
            self._store.write(store_items)

        self._todos = todos
        lines = []
        for t in todos:
            status_icon = {
                "pending": "○", "in_progress": "◐",
                "completed": "●", "deleted": "✕",
            }.get(t.get("status", "pending"), "?")
            lines.append(f"{status_icon} {t.get('subject', '')}")
        return {"is_error": False, "message": f"Task list ({len(todos)} items).", "output": "\n".join(lines)}


# ---------------------------------------------------------------------------
# todo — 函数风格工具（来自 simple-agent，带 TodoStore）
# ---------------------------------------------------------------------------

def todo_tool(
    todos: list[dict[str, Any]] | None = None,
    merge: bool = False,
    store: TodoStore | None = None,
) -> str:
    """todo 函数工具 — 需要 TodoStore 实例"""
    if store is None:
        return json.dumps({"error": "TodoStore not initialized."})

    if todos is not None:
        items = store.write(todos, merge)
    else:
        items = store.read()

    pending = sum(1 for i in items if i["status"] == "pending")
    in_progress = sum(1 for i in items if i["status"] == "in_progress")
    completed = sum(1 for i in items if i["status"] == "completed")
    cancelled = sum(1 for i in items if i["status"] == "cancelled")

    return json.dumps({
        "todos": items,
        "summary": {
            "total": len(items),
            "pending": pending, "in_progress": in_progress,
            "completed": completed, "cancelled": cancelled,
        },
    }, ensure_ascii=False)


TODO_SCHEMA = {
    "name": "todo",
    "description": (
        "Manage your task list. Use for complex tasks with 3+ steps. "
        "Call with no params to read. Provide 'todos' array to write. "
        "Each item: {id, content, status: pending|in_progress|completed|cancelled}. "
        "merge=false replaces list; merge=true updates by id."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": list(VALID_STATUSES)},
                    },
                    "required": ["id", "content", "status"],
                },
            },
            "merge": {"type": "boolean", "description": "Update by id (true) or replace all (false)."},
        },
        "required": [],
    },
}
