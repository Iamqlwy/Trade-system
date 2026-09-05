"""子 Agent 数据模型。

复刻自 code/code_agent/subagents/models.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ToolPolicy:
    """工具访问策略"""
    mode: Literal["allowlist", "denylist", "inherit"] = "inherit"
    tools: list[str] = field(default_factory=list)


@dataclass
class AgentTypeDefinition:
    """子 Agent 类型定义"""
    name: str
    description: str
    agent_file: Path
    when_to_use: str = ""
    default_model: str | None = None
    tool_policy: ToolPolicy = field(default_factory=ToolPolicy)
