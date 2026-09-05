"""AskUserQuestion 工具 — 向用户提问以澄清需求或获取偏好。

复刻自 code/code_agent/tools/ask_user/

功能：
  - 支持 1-4 个问题同时提问（questions 数组）
  - 兼容旧的单问题格式（question + options）
  - 回调式交互 (bind_on_ask)
  - 无回调时返回第一个选项（降级）
"""

from __future__ import annotations

from typing import Callable, Optional

from app.agent.tools.base import Tool, ToolParam


class AskUserQuestion(Tool):
    """向用户提问"""

    name = "AskUserQuestion"
    description = "Ask the user a question to clarify requirements or get preferences."

    def __init__(self):
        self._on_ask: Optional[Callable] = None

    parameters = [
        ToolParam(
            "questions", list,
            "Questions to ask (1-4). Each item has: question (str), header (str), options (str[]), multiSelect (bool).",
            required=False,
        ),
        ToolParam("question", str, "Single question text (legacy, use questions[] instead).", required=False),
        ToolParam("header", str, "Short label for the question.", default="Question", required=False),
        ToolParam("options", str, "Comma-separated options (legacy, use questions[].options instead).", required=False),
        ToolParam("multi", bool, "Allow multiple selections (legacy).", default=False, required=False),
    ]

    def bind_on_ask(self, callback: Callable) -> None:
        """设置交互回调:
        新模式: callback(questions: list[dict]) -> list[str]
        旧模式: callback(question, header, options, multi) -> str
        """
        self._on_ask = callback

    async def call(self, arguments: dict) -> dict:
        # ── 新格式: questions 数组 ──
        questions_raw = arguments.get("questions")
        if questions_raw and isinstance(questions_raw, list):
            questions = []
            for q in questions_raw:
                if isinstance(q, dict):
                    questions.append({
                        "question": q.get("question", ""),
                        "header": q.get("header", "Question"),
                        "options": q.get("options", []) if isinstance(q.get("options"), list) else [],
                        "multiSelect": bool(q.get("multiSelect", False)),
                    })
            if not questions:
                return {"is_error": True, "message": "questions array is empty", "output": ""}

            if self._on_ask:
                answers = await self._on_ask(questions)
                # answers 可能是 list[str]（新回调）或 str（旧回调降级）
                if isinstance(answers, list):
                    parts = []
                    for i, (q, a) in enumerate(zip(questions, answers)):
                        parts.append(f"Question {i + 1} ({q['header']}): {a}")
                    return {"is_error": False, "message": "\n".join(parts), "output": "\n".join(parts)}
                else:
                    return {"is_error": False, "message": f"User answered: {answers}", "output": str(answers)}
            else:
                return {
                    "is_error": False,
                    "message": "No interactive handler. Using first options.",
                    "output": "; ".join(
                        (q["options"][0] if q.get("options") else "")
                        for q in questions
                    ),
                }

        # ── 旧格式: 单问题 ──
        question = arguments.get("question", "")
        header = arguments.get("header", "Question")
        options_str = arguments.get("options", "")
        multi = arguments.get("multi", False)

        options = [o.strip() for o in options_str.split(",") if o.strip()]

        if self._on_ask:
            # 新回调可能只接受 questions 列表，需要适配
            import inspect
            try:
                sig = inspect.signature(self._on_ask)
                if len(sig.parameters) == 1:
                    # 新回调: 接受 questions 列表
                    answers = await self._on_ask([{
                        "question": question,
                        "header": header,
                        "options": options,
                        "multiSelect": multi,
                    }])
                    answer = answers[0] if isinstance(answers, list) else str(answers)
                else:
                    # 旧回调: 接受 4 个参数
                    answer = await self._on_ask(question, header, options, multi)
            except (ValueError, TypeError):
                answer = await self._on_ask(question, header, options, multi)
            return {"is_error": False, "message": f"User answered: {answer}", "output": answer}
        else:
            return {
                "is_error": False,
                "message": "No interactive handler. Using first option.",
                "output": options[0] if options else "",
            }
