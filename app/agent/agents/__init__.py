"""Agent 实现包

提供两种 Agent 模式：
  - SimpleAgent:    通用对话 Agent（含文件/Shell/委托等全部工具）
  - ResearcherAgent: 研究 Agent（搜索 + 报告）
"""

from .simple import SimpleAgent
from .researcher import ResearcherAgent

__all__ = ["SimpleAgent", "ResearcherAgent"]
