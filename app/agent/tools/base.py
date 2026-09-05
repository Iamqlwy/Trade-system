"""统一工具基类与注册表

合并两种工具系统：
  - simple-agent: 函数式注册 (registry.register)
  - code_agent: OOP 类 (Tool 基类 + Toolset)

统一后同时支持：
  1. 继承 Tool 基类（推荐新工具使用）
  2. 注册函数 + JSON Schema（兼容旧代码）
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 异常与结果
# ---------------------------------------------------------------------------

class ToolError(Exception):
    """工具执行错误"""
    def __init__(self, message: str, brief: str = ""):
        self.message = message
        self.brief = brief or message


class ToolNotFoundError(ToolError):
    pass


class ToolParseError(ToolError):
    pass


class ToolRuntimeError(ToolError):
    pass


class ToolResult:
    """工具调用结果"""
    def __init__(self, tool_call_id: str, return_value: Any):
        self.tool_call_id = tool_call_id
        self.return_value = return_value
        self.is_error = isinstance(return_value, ToolError) or (
            isinstance(return_value, dict) and bool(return_value.get("is_error"))
        )


# ---------------------------------------------------------------------------
# Tool 参数定义
# ---------------------------------------------------------------------------

class ToolParam:
    """工具参数描述"""
    def __init__(
        self,
        name: str,
        type_: type,
        description: str = "",
        default: Any = None,
        required: bool = True,
    ):
        self.name = name
        self.type = type_
        self.description = description
        self.default = default
        self.required = required


# ---------------------------------------------------------------------------
# Tool 基类（OOP 风格）
# ---------------------------------------------------------------------------

class Tool(ABC):
    """工具基类 — 新工具推荐继承此类。

    子类需定义：
      - name: str
      - description: str
      - parameters: list[ToolParam]
      - async call(arguments: dict) -> Any
    """

    name: str = ""
    description: str = ""
    parameters: list[ToolParam] = []

    async def call(self, arguments: dict) -> Any:  # noqa: ARG002
        raise NotImplementedError

    @property
    def openai_schema(self) -> dict:
        """生成 OpenAI function calling 格式定义"""
        props: dict[str, dict] = {}
        required: list[str] = []

        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }

        for p in self.parameters:
            props[p.name] = {
                "type": type_map.get(p.type, "string"),
                "description": p.description,
            }
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        }


# ---------------------------------------------------------------------------
# 函数式工具包装器
# ---------------------------------------------------------------------------

class _FunctionToolEntry:
    """函数式工具条目（兼容 simple-agent 风格）"""
    __slots__ = ("name", "category", "schema", "handler", "check_fn",
                 "is_async", "description")

    def __init__(
        self,
        name: str,
        category: str,
        schema: dict,
        handler: Callable,
        check_fn: Optional[Callable] = None,
        is_async: bool = False,
        description: str = "",
    ):
        self.name = name
        self.category = category
        self.schema = schema
        self.handler = handler
        self.check_fn = check_fn
        self.is_async = is_async
        self.description = description or schema.get("description", "")


# ---------------------------------------------------------------------------
# 跨步骤去重提醒
# ---------------------------------------------------------------------------

_REMINDER_TEXT = (
    "\n\n<system-reminder>\n"
    "You are repeating the exact same tool call with identical parameters."
    " Please carefully analyze the previous result. If the task is not yet complete,"
    " try a different method or parameters instead of repeating the same call."
    "\n</system-reminder>"
)


def _append_reminder(return_value: Any) -> Any:
    """对去重命中的结果附加提醒"""
    if isinstance(return_value, dict):
        output = return_value.get("output", "")
        if isinstance(output, str):
            return_value["output"] = output + _REMINDER_TEXT
    return return_value


# ---------------------------------------------------------------------------
# ToolRegistry — 统一注册表
# ---------------------------------------------------------------------------

class ToolRegistry:
    """统一工具注册表。

    支持两种注册方式：
      1. add(tool: Tool) — OOP 风格
      2. register_function(name, category, schema, handler) — 函数风格

    通过 get_all_schemas() 统一输出 OpenAI 格式。
    通过 dispatch() 统一分发调用。
    """

    def __init__(self):
        self._class_tools: dict[str, Tool] = {}
        self._func_tools: dict[str, _FunctionToolEntry] = {}
        self._hidden: set[str] = set()
        # 去重
        self._previous_step_calls: list[tuple[str, str]] = []
        self._current_step_calls: list[tuple[str, str]] = []
        self._current_step_tasks: dict[tuple[str, str], asyncio.Task] = {}

    # ---- 注册 ----

    def add(self, tool: Tool) -> None:
        """注册 OOP 风格工具"""
        self._class_tools[tool.name] = tool

    def register(
        self,
        name: str,
        category: str,
        schema: dict,
        handler: Callable,
        check_fn: Optional[Callable] = None,
        is_async: bool = False,
        description: str = "",
    ) -> None:
        """注册函数式工具（兼容 simple-agent 风格）"""
        self._func_tools[name] = _FunctionToolEntry(
            name=name,
            category=category,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            is_async=is_async,
            description=description,
        )

    # 别名
    register_function = register

    # ---- 查询 ----

    def find(self, name: str) -> Tool | _FunctionToolEntry | None:
        """查找工具"""
        return self._class_tools.get(name) or self._func_tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._class_tools or name in self._func_tools

    @property
    def all_tool_names(self) -> list[str]:
        names = set(self._class_tools.keys()) | set(self._func_tools.keys())
        return sorted(names - self._hidden)

    def get_all_schemas(
        self,
        tool_names: Optional[set[str]] = None,
    ) -> list[dict]:
        """获取所有工具的 OpenAI 格式定义"""
        result: list[dict] = []

        # OOP 工具
        for name in sorted(self._class_tools.keys()):
            if name in self._hidden:
                continue
            if tool_names and name not in tool_names:
                continue
            result.append(self._class_tools[name].openai_schema)

        # 函数工具
        for name in sorted(self._func_tools.keys()):
            if name in self._hidden:
                continue
            if tool_names and name not in tool_names:
                continue
            entry = self._func_tools[name]
            if entry.check_fn:
                try:
                    if not entry.check_fn():
                        continue
                except Exception:
                    continue
            schema = {**entry.schema, "name": entry.name}
            result.append({"type": "function", "function": schema})

        return result

    # 别名
    @property
    def openai_tools(self) -> list[dict]:
        return self.get_all_schemas()

    # ---- 隐藏/显示 ----

    def hide(self, name: str) -> bool:
        if self.has(name):
            self._hidden.add(name)
            return True
        return False

    def unhide(self, name: str) -> None:
        self._hidden.discard(name)

    # ---- 步骤管理（去重） ----

    def begin_step(self, previous_calls: list[tuple[str, str]]) -> None:
        self._previous_step_calls = previous_calls
        self._current_step_calls = []
        self._current_step_tasks = {}

    def end_step(self) -> list[tuple[str, str]]:
        return list(self._current_step_calls)

    # ---- 调用分发 ----

    def handle(self, tool_call: dict) -> asyncio.Task[ToolResult]:
        """处理工具调用（异步），支持同步骤/跨步骤去重"""
        func_name = tool_call["function"]["name"]
        args_str = tool_call["function"].get("arguments", "{}")
        call_id = tool_call.get("id", "")
        call_key = (func_name, args_str)

        # 同步骤去重
        if call_key in self._current_step_tasks:
            logger.info("Same-step dedup: reusing %s", func_name)
            return self._current_step_tasks[call_key]

        self._current_step_calls.append(call_key)

        # 解析参数
        try:
            arguments = json.loads(args_str)
        except json.JSONDecodeError:
            async def _parse_error():
                return ToolResult(call_id, ToolParseError(f"Invalid JSON: {args_str}"))
            task = asyncio.create_task(_parse_error())
            self._current_step_tasks[call_key] = task
            return task

        # OOP 工具
        if func_name in self._class_tools:
            is_cross_step_dup = call_key in self._previous_step_calls

            async def _execute_class():
                tool = self._class_tools[func_name]
                try:
                    t0 = time.monotonic()
                    ret = await tool.call(arguments)
                    elapsed = time.monotonic() - t0
                    logger.info("Tool %s completed in %.1fs", func_name, elapsed)
                    if is_cross_step_dup:
                        ret = _append_reminder(ret)
                    return ToolResult(call_id, ret)
                except Exception as e:
                    logger.exception("Tool %s failed", func_name)
                    exc_msg = str(e) or repr(e)
                    return ToolResult(call_id, ToolRuntimeError(f"[{type(e).__name__}] {exc_msg}"))

            task = asyncio.create_task(_execute_class())
            self._current_step_tasks[call_key] = task
            return task

        # 函数工具
        if func_name in self._func_tools:
            entry = self._func_tools[func_name]
            is_cross_step_dup = call_key in self._previous_step_calls

            async def _execute_func():
                try:
                    t0 = time.monotonic()
                    if entry.is_async:
                        ret = await entry.handler(arguments)
                    else:
                        ret = entry.handler(arguments)
                    elapsed = time.monotonic() - t0
                    logger.info("Tool %s completed in %.1fs", func_name, elapsed)
                    if is_cross_step_dup:
                        ret = _append_reminder(ret)
                    return ToolResult(call_id, ret)
                except Exception as e:
                    logger.exception("Tool %s failed", func_name)
                    exc_msg = str(e) or repr(e)
                    return ToolResult(call_id, ToolRuntimeError(f"[{type(e).__name__}] {exc_msg}"))

            task = asyncio.create_task(_execute_func())
            self._current_step_tasks[call_key] = task
            return task

        # 未找到
        async def _not_found():
            return ToolResult(call_id, ToolNotFoundError(f"Unknown tool: {func_name}"))
        task = asyncio.create_task(_not_found())
        self._current_step_tasks[call_key] = task
        return task

    def dispatch_sync(self, name: str, args: dict) -> str:
        """同步分发函数式工具（向后兼容）"""
        entry = self._func_tools.get(name)
        if not entry:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            if entry.is_async:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        return pool.submit(asyncio.run, entry.handler(args)).result(timeout=300)
                return asyncio.run(entry.handler(args))
            return entry.handler(args)
        except Exception as e:
            logger.exception("Tool %s dispatch error: %s", name, e)
            return json.dumps({"error": f"Tool execution failed: {type(e).__name__}: {e}"})


# ---------------------------------------------------------------------------
# 便利函数
# ---------------------------------------------------------------------------

def tool_error(message: str, **extra) -> str:
    """返回错误格式 JSON"""
    result = {"error": str(message)}
    if extra:
        result.update(extra)
    return json.dumps(result, ensure_ascii=False)


def tool_result(data: Any = None, **kwargs) -> str:
    """返回成功格式 JSON"""
    if data is not None:
        return json.dumps(data, ensure_ascii=False)
    return json.dumps(kwargs, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 全局注册表单例
# ---------------------------------------------------------------------------

registry = ToolRegistry()
