"""系统提示构建器

来自 simple-agent/agent/prompt.py — 组装身份、环境、技能、记忆、工具。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from app.config import settings


AGENT_IDENTITY = """You are Unified Agent, an intelligent AI assistant.
You help users with a wide range of tasks including answering questions,
writing and editing code, analyzing information, creative work, research,
and executing actions via your tools. You communicate clearly, admit
uncertainty when appropriate, and prioritize being genuinely useful
over being verbose."""


def build_system_prompt(
    identity: str = "",
    skills_catalog: str = "",
    memory_block: str = "",
    user_block: str = "",
    workdir: Optional[str] = None,
    sessions_block: str = "",
    workspace: Optional[str] = None,
    agent_type: str = "simple",
    session_token: Optional[str] = None,
    plan_mode: bool = False,
) -> str:
    """组装完整的系统提示。

    层级：
      1. Agent 身份（根据 agent_type 定制）
      2. 环境信息（日期、OS、工作目录、工作区）
      3. 技能目录
      4. 活跃子 agent 会话
      5. 记忆快照
      6. 工具使用指南
    """
    parts: list[str] = []

    # [1] 身份
    parts.append(identity or AGENT_IDENTITY)

    # [2] 环境
    now = datetime.now().strftime("%Y-%m-%d %A %H:%M:%S")
    # Shell 命令在 Docker Linux 容器中执行，必须报告为 Linux
    # （宿主机可能是 Windows，但沙箱内是 Linux bash）
    os_info = "Linux (Docker sandbox)"
    cwd = workdir or os.getcwd()
    env_lines = [
        f"Current time: {now}",
        f"Operating system: {os_info}",
        f"Working directory: {cwd}",
        f"Agent type: {agent_type}",
        f"Read-only data: /data/  (host directories mounted here, e.g. /data/klines)",
    ]
    if workspace:
        env_lines.append(
            f"Agent workspace: {workspace}  "
            "(file tools will use this directory)"
        )
    if session_token:
        env_lines.append(f"Agent session token: {session_token}")
    # Docker 网络提示
    backend_url = f"http://host.docker.internal:{settings.api_port}"
    env_lines.append(
        "IMPORTANT: When accessing the backend API (e.g. via curl or scripts), "
        "do NOT use localhost. Use host.docker.internal instead. "
        f"The backend API is at {backend_url} "
        "(also available via the BACKEND_URL environment variable)."
    )
    env_lines.append(
        "NOTE: The workspace directory inside the container is /workspace. "
        "All file paths are relative to /workspace unless specified otherwise. "
        "The container filesystem is a standard Linux system (/) but is READ-ONLY "
        "except for /workspace (writable, your working area) and /tmp (writable). "
        "Read-only host data is mounted at /data/ (e.g. /data/klines)."
    )
    env_lines.append(
        "Image display: When you generate or reference an image file in the workspace, "
        "render it using Markdown image syntax: ![description](path/to/image.png). "
        "Use relative paths from the workspace root."
    )
    parts.append("## Environment\n" + "\n".join(env_lines))

    # [3] 技能
    if skills_catalog:
        parts.append(f"## Skills\n{skills_catalog}")

    # [4] 活跃会话
    if sessions_block:
        parts.append(f"## Active Sessions\n{sessions_block}")

    # [5] 记忆
    if memory_block:
        parts.append(memory_block)
    if user_block:
        parts.append(user_block)

    # [6] 工具指南
    parts.append("""## Tool Usage
You have access to tools for shell execution, file operations, web search,
task tracking, memory, skill management, and sub-agent delegation.
Use tools proactively to accomplish user goals. When you need multiple
pieces of information, make independent tool calls concurrently.
Always check terminal exit codes — non-zero means the command failed.

IMPORTANT: Once you have gathered enough information and completed the
task, provide your final answer as a text response WITHOUT calling any
more tools. Do not continue calling tools unnecessarily.""")

    # [7] Plan Mode
    if plan_mode:
        parts.append("""## PLAN MODE (Active)

You are currently in PLAN MODE — a read-only analysis and planning phase.
You CANNOT make any changes to the system.

RULES:
- You CANNOT modify files, execute shell commands, or make any changes
- You CAN read files, search the codebase, browse the web, and analyze
- Your goal: produce a DETAILED IMPLEMENTATION PLAN
- Structure your plan: Context → Analysis → Proposed Changes (file-by-file) → Steps → Risks
- When your plan is complete, call ExitPlanMode to present it for user approval
- Do NOT implement anything — only plan and analyze

The user will review your plan and decide whether to proceed with implementation.""")

    return "\n\n".join(parts)
