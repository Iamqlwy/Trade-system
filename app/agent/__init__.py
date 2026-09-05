"""Unified Agent — 统一 AI Agent 框架

合并了 simple-agent、code_agent 和 search_agent 三个独立项目。
提供两种 Agent 模式：
  - simple:    通用对话 Agent（技能、记忆、定时任务、Web 搜索、Shell、子 Agent 委托）
  - researcher: 研究 Agent（深度搜索、知识检索、报告生成）

工具系统：
  文件工具：ReadFile, WriteFile, StrReplaceFile, Glob, Grep
  Shell 工具：Shell（异步子进程执行）
  Web 工具：WebSearchTool, WebFetch, Scraper
  交互工具：AskUserQuestion
  思考工具：Think
  任务工具：TodoWrite, TodoStore, todo
  技能工具：SkillsList, SkillView, SkillManage
  定时工具：Cronjob
  子 Agent 工具：Agent（唯一用于委派任务给子 Agent 的工具）

子 Agent 系统：
  LaborMarket: 子 Agent 类型注册表
  run_subagent: 子 Agent 执行器
"""

from app.agent.agents import SimpleAgent, ResearcherAgent
from app.agent.tools import (
    Tool, ToolParam, ToolResult, ToolError,
    ToolRegistry, registry,
    Shell, AskUserQuestion, Think,
    TodoWrite, TodoStore, todo_tool, TODO_SCHEMA,
    SkillsList, SkillView, SkillManage,
    Cronjob, Agent,
    WebSearchTool, WebFetch,
    build_full_registry, register_all_tools,
)
from app.agent.subagents import (
    ToolPolicy, AgentTypeDefinition,
    LaborMarket,
    run_subagent,
)
from app.agent.skills import (
    SkillMeta, SkillFull,
    scan_skills, load_skill, load_skill_file, build_catalog,
)

__version__ = "0.1.0"

__all__ = [
    # Agent 模式
    "SimpleAgent", "ResearcherAgent",
    # 工具基础
    "Tool", "ToolParam", "ToolResult", "ToolError",
    "ToolRegistry", "registry",
    "build_full_registry", "register_all_tools",
    # Shell
    "Shell",
    # Web
    "WebSearchTool", "WebFetch",
    # 交互
    "AskUserQuestion",
    # 思考
    "Think",
    # 任务
    "TodoWrite", "TodoStore", "todo_tool", "TODO_SCHEMA",
    # 技能
    "SkillsList", "SkillView", "SkillManage",
    "SkillMeta", "SkillFull",
    "scan_skills", "load_skill", "load_skill_file", "build_catalog",
    # 定时
    "Cronjob",
    # 子 Agent
    "Agent",
    # 子 Agent
    "ToolPolicy", "AgentTypeDefinition",
    "LaborMarket",
    "run_subagent",
]
