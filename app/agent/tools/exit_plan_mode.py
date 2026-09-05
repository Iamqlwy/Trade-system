"""ExitPlanMode tool — signals that the plan is ready for user review.

When in plan mode, the agent calls this tool after producing a detailed
implementation plan. The user can then review and decide whether to exit
plan mode and begin implementation.
"""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolParam


class ExitPlanMode(Tool):
    name = "ExitPlanMode"
    description = (
        "Signal that the implementation plan is complete and ready for user review. "
        "Call this AFTER presenting a detailed, structured plan in your text response. "
        "The user will review the plan and decide whether to exit plan mode for implementation."
    )
    parameters = [
        ToolParam(
            name="plan_summary",
            type_=str,
            description="One-line summary of the plan for the user to review",
            required=True,
        ),
    ]

    async def call(self, arguments: dict) -> Any:
        return {
            "status": "plan_ready_for_review",
            "summary": arguments.get("plan_summary", ""),
        }
