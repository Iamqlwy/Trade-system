"""LaborMarket — 子 Agent 类型注册表。

复刻自 code/code_agent/subagents/registry.py
"""

from __future__ import annotations

from app.agent.subagents.models import AgentTypeDefinition


class LaborMarket:
    """可用子 Agent 类型的注册表。"""

    def __init__(self):
        self._builtin_types: dict[str, AgentTypeDefinition] = {}

    def add_builtin_type(self, defn: AgentTypeDefinition) -> None:
        """注册内置类型"""
        self._builtin_types[defn.name] = defn

    def get(self, name: str) -> AgentTypeDefinition | None:
        """按名称获取类型定义"""
        return self._builtin_types.get(name)

    def list_types(self) -> list[AgentTypeDefinition]:
        """列出所有可用类型"""
        return list(self._builtin_types.values())
