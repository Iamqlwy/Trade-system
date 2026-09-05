"""Agent 事件协议定义

统一后端 ↔ 前端的 WebSocket 消息格式。
"""

from __future__ import annotations

import time
from typing import Any


def _now_ts() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# 后端 → 前端事件
# ---------------------------------------------------------------------------

def make_token_event(
    session_id: str,
    agent_id: str,
    content: str,
    sub_agent_id: str = "main",
) -> dict[str, Any]:
    """LLM 流式 token"""
    return {
        "type": "agent_stream",
        "event": "token",
        "session_id": session_id,
        "agent_id": agent_id,
        "sub_agent_id": sub_agent_id,
        "content": content,
        "ts": _now_ts(),
    }


def make_thinking_event(
    session_id: str,
    agent_id: str,
    turn: int = 0,
    step: int = 0,
) -> dict[str, Any]:
    """Agent 正在思考"""
    return {
        "type": "agent_stream",
        "event": "thinking",
        "session_id": session_id,
        "agent_id": agent_id,
        "data": {"turn": turn, "step": step},
        "ts": _now_ts(),
    }


def make_tool_start_event(
    session_id: str,
    agent_id: str,
    tool_call_id: str,
    name: str,
    args: dict,
) -> dict[str, Any]:
    """工具开始执行"""
    return {
        "type": "agent_stream",
        "event": "tool_start",
        "session_id": session_id,
        "agent_id": agent_id,
        "data": {
            "tool_call_id": tool_call_id,
            "name": name,
            "args": args,
        },
        "ts": _now_ts(),
    }


def make_tool_end_event(
    session_id: str,
    agent_id: str,
    tool_call_id: str,
    name: str,
    preview: str,
    is_error: bool = False,
) -> dict[str, Any]:
    """工具执行完成"""
    return {
        "type": "agent_stream",
        "event": "tool_end",
        "session_id": session_id,
        "agent_id": agent_id,
        "data": {
            "tool_call_id": tool_call_id,
            "name": name,
            "preview": preview,
            "is_error": is_error,
        },
        "ts": _now_ts(),
    }


def make_sub_agent_event(
    session_id: str,
    agent_id: str,
    action: str,  # "spawned" | "token" | "completed"
    sub_agent_id: str,
    sub_agent_type: str = "",
    content: str = "",
    task_description: str = "",
    status: str = "",
    result_summary: str = "",
) -> dict[str, Any]:
    """子 Agent 事件"""
    data: dict[str, Any] = {
        "sub_agent_id": sub_agent_id,
        "action": action,
    }
    if sub_agent_type:
        data["sub_agent_type"] = sub_agent_type
    if content:
        data["content"] = content
    if task_description:
        data["task_description"] = task_description
    if status:
        data["status"] = status
    if result_summary:
        data["result_summary"] = result_summary

    return {
        "type": "agent_stream",
        "event": "sub_agent",
        "session_id": session_id,
        "agent_id": agent_id,
        "data": data,
        "ts": _now_ts(),
    }


def make_done_event(
    session_id: str,
    agent_id: str,
    turns: int = 0,
    api_calls: int = 0,
    steps: int = 0,
) -> dict[str, Any]:
    """本轮对话结束"""
    return {
        "type": "agent_stream",
        "event": "done",
        "session_id": session_id,
        "agent_id": agent_id,
        "data": {
            "turns": turns,
            "api_calls": api_calls,
            "steps": steps,
        },
        "ts": _now_ts(),
    }


def make_error_event(
    session_id: str,
    agent_id: str,
    message: str,
) -> dict[str, Any]:
    """错误"""
    return {
        "type": "agent_stream",
        "event": "error",
        "session_id": session_id,
        "agent_id": agent_id,
        "data": {"message": message},
        "ts": _now_ts(),
    }


def make_ask_user_event(
    session_id: str,
    agent_id: str,
    question: str,
    header: str = "Question",
    options: list[str] | None = None,
    multi: bool = False,
    request_id: str = "",
) -> dict[str, Any]:
    """AskUserQuestion 事件 — 向用户提问并等待回答"""
    return {
        "type": "agent_stream",
        "event": "ask_user",
        "session_id": session_id,
        "agent_id": agent_id,
        "data": {
            "question": question,
            "header": header,
            "options": options or [],
            "multi": multi,
            "request_id": request_id,
        },
        "ts": _now_ts(),
    }


def make_restored_event(
    session_id: str,
    agent_id: str,
    messages: list[dict],
    sub_agents: list[dict] | None = None,
    plan_mode: bool = False,
) -> dict[str, Any]:
    """会话恢复完成"""
    return {
        "type": "agent_stream",
        "event": "restored",
        "session_id": session_id,
        "agent_id": agent_id,
        "data": {
            "messages": messages,
            "sub_agents": sub_agents or [],
            "plan_mode": plan_mode,
        },
        "ts": _now_ts(),
    }


def make_plan_mode_event(
    session_id: str,
    plan_mode: bool,
) -> dict[str, Any]:
    """计划模式切换"""
    return {
        "type": "agent_stream",
        "event": "plan_mode_toggled",
        "session_id": session_id,
        "agent_id": "main",
        "data": {"plan_mode": plan_mode},
        "ts": _now_ts(),
    }
