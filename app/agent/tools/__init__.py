"""统一工具系统

支持两种注册方式：
  1. OOP 风格：继承 Tool 基类，定义 openai_schema 和 call()
  2. 函数风格：通过 register_function() 注册函数和 JSON Schema

通过 ToolRegistry.get_all_schemas() 统一输出 OpenAI 格式。

工具列表：
  文件工具：ReadFile, WriteFile, StrReplaceFile, Glob, Grep
  Shell 工具：Shell
  Web 工具：WebSearchTool, Scraper
  交互工具：AskUserQuestion
  思考工具：Think
  任务工具：TodoWrite
  记忆工具：Memory
  技能工具：SkillsList, SkillView, SkillManage
  定时工具：Cronjob
  策略工具：StrategyView
  子 Agent 工具：Agent (唯一用于委派任务给子 Agent 的工具)
"""

from pathlib import Path
from typing import Optional

from .base import Tool, ToolParam, ToolResult, ToolError, ToolRegistry, registry
from .security import DEFAULT_EXTRA_READ_DIRS

# 文件工具
from .file.read import ReadFile
from .file.write import WriteFile
from .file.replace import StrReplaceFile
from .file.glob import Glob
from .file.grep import Grep

# Shell
from .shell import Shell

# Web
from .web.search import WebSearchTool
from .web.extract import WebFetch, Scraper, simple_extract

# 交互
from .ask_user import AskUserQuestion

# 思考
from .think import Think

# 任务
from .todo import TodoWrite, TodoStore, todo_tool, TODO_SCHEMA

# 记忆
from .memory_tool import Memory

# 技能
from .skills_tools import SkillsList, SkillView, SkillManage

# 定时
from .cronjob import Cronjob

# 策略查看
from .strategy_view import StrategyView

# 子 Agent 委托（唯一的委派工具）
from .agent_tool import Agent

# 计划模式退出
from .exit_plan_mode import ExitPlanMode

__all__ = [
    # 基础
    "Tool", "ToolParam", "ToolResult", "ToolError",
    "ToolRegistry", "registry",
    # 文件
    "ReadFile", "WriteFile", "StrReplaceFile", "Glob", "Grep",
    # Shell
    "Shell",
    # Web
    "WebSearchTool", "WebFetch", "Scraper", "simple_extract",
    # 交互
    "AskUserQuestion",
    # 思考
    "Think",
    # 任务
    "TodoWrite", "TodoStore", "todo_tool", "TODO_SCHEMA",
    # 记忆
    "Memory",
    # 技能
    "SkillsList", "SkillView", "SkillManage",
    # 定时
    "Cronjob",
    # 策略查看
    "StrategyView",
    # 子 Agent
    "Agent",
    # 计划模式
    "ExitPlanMode",
    # 便利函数
    "build_full_registry", "register_all_tools",
]


def build_full_registry(
    work_dir: Path | None = None,
    **agent_kwargs,
) -> ToolRegistry:
    """构建包含所有工具的完整注册表（新建实例）。"""
    work_dir = work_dir or Path.cwd()
    reg = ToolRegistry()
    _populate_registry(reg, work_dir, **agent_kwargs)
    return reg


def register_all_tools(
    reg: ToolRegistry | None = None,
    work_dir: Path | None = None,
    **agent_kwargs,
) -> ToolRegistry:
    """将全部工具注册到指定的注册表（默认注册到全局 registry）。"""
    target = reg or registry
    work_dir = work_dir or Path.cwd()
    _populate_registry(target, work_dir, **agent_kwargs)
    return target


def _populate_registry(
    reg: ToolRegistry,
    work_dir: Path,
    event_callback=None,
    session_id: str = "",
    user_id: int = 0,
    context_file: Optional[str] = None,  # 新增：主会话的 context 文件路径
    enabled_tool_classes: Optional[set[str]] = None,  # 白名单：None=全部注册
    extra_read_dirs: Optional[list[Path]] = None,  # ReadFile 额外允许读取的目录（默认 C:/klines）
    **agent_kwargs,
) -> None:
    """内部：向注册表填充工具

    enabled_tool_classes: 允许注册的工具类名集合。None 表示全部注册。
    extra_read_dirs: ReadFile 额外允许读取的目录列表（如 [Path("C:/klines")]）。
    user_id: 用户 ID（用于沙箱隔离）。
    """
    def _ok(*class_names: str) -> bool:
        if enabled_tool_classes is None:
            return True
        return any(n in enabled_tool_classes for n in class_names)

    # 文件
    if _ok("ReadFile"):
        _extra_dirs = extra_read_dirs if extra_read_dirs is not None else DEFAULT_EXTRA_READ_DIRS
        reg.add(ReadFile(work_dir=work_dir, extra_read_dirs=_extra_dirs))
    if _ok("WriteFile"):
        reg.add(WriteFile(work_dir=work_dir))
    if _ok("StrReplaceFile"):
        reg.add(StrReplaceFile(work_dir=work_dir))
    if _ok("Glob"):
        reg.add(Glob(work_dir=work_dir))
    if _ok("Grep"):
        reg.add(Grep(work_dir=work_dir))

    # Shell（传递 user_id 和 session_id 用于沙箱隔离）
    if _ok("Shell"):
        reg.add(Shell(work_dir=work_dir, user_id=user_id, session_id=session_id))

    # Web
    if _ok("WebSearchTool"):
        reg.add(WebSearchTool())
    if _ok("WebFetch"):
        reg.add(WebFetch())

    # 交互（始终注册）
    reg.add(AskUserQuestion())

    # 思考（始终注册）
    reg.add(Think())

    # 任务（始终注册）
    todo_store = agent_kwargs.get("todo_store")
    reg.add(TodoWrite(todo_store=todo_store))

    # 记忆（始终注册）
    memory_svc = agent_kwargs.get("memory_service")
    mem_user_id = agent_kwargs.get("user_id", 0)
    reg.add(Memory(memory_service=memory_svc, user_id=mem_user_id))

    # 技能（始终注册）
    reg.add(SkillsList())
    reg.add(SkillView())
    reg.add(SkillManage())

    # 计划模式退出（始终注册）
    reg.add(ExitPlanMode())

    # 定时
    if _ok("Cronjob"):
        reg.add(Cronjob())

    # 策略查看
    if _ok("StrategyView"):
        reg.add(StrategyView())

    # 子 Agent 委托（传递 event_callback 以发送子 agent 事件）
    if _ok("Agent"):
        reg.add(Agent(
            work_dir=work_dir,
            model=agent_kwargs.get("model", "qwen3.6-plus"),
            base_url=agent_kwargs.get("base_url", ""),
            api_key=agent_kwargs.get("api_key", ""),
            api_mode=agent_kwargs.get("api_mode", "chat"),
            event_callback=event_callback,
            session_id=session_id,
            context_file=context_file,  # 传递 context_file
        ))
