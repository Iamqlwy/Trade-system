"""Think 工具 — 记录思考过程，不执行任何操作。

复刻自 code/code_agent/tools/think/

功能：
  - 记录中间思考步骤
  - 用于分步推理 (step-by-step thinking)
  - 无副作用，纯记录
"""

from __future__ import annotations

from app.agent.tools.base import Tool, ToolParam


class Think(Tool):
    """记录思考"""

    name = "Think"
    description = "Use this to think through a problem step by step without taking any action."

    parameters = [
        ToolParam("thought", str, "The thought to record."),
    ]

    async def call(self, arguments: dict) -> dict:
        thought = arguments.get("thought", "")
        return {"is_error": False, "message": "Thought recorded.", "output": thought}
