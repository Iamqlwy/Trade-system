"""子 Agent 执行器 — 运行子 Agent 并返回输出。

复刻自 code/code_agent/subagents/runner.py

适配说明：
  - 使用 app/agent 的 SimpleAgent 替代原 Soul
  - 通过 ToolRegistry 实现工具策略
  - 子 Agent 运行在独立上下文中，并保存到 session 目录
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

SUMMARY_MIN_LENGTH = 200


async def run_subagent(
    prompt: str,
    subagent_type: str = "general-purpose",
    description: str = "",
    work_dir: Optional[Path] = None,
    model: str = "qwen3.6-plus",
    base_url: str = "",
    api_key: str = "",
    api_mode: str = "chat",
    max_steps: int = 100,
    allowed_tools: Optional[set[str]] = None,
    event_callback: Optional[Callable] = None,
    session_dir: Optional[Path] = None,  # 新增：session 目录路径
) -> str:
    """运行子 Agent 并返回其输出文本。

    Args:
        prompt: 子 Agent 要执行的任务
        subagent_type: 子 Agent 类型 (general-purpose, explore, plan, researcher)
        description: 任务简短描述
        work_dir: 工作目录
        model: LLM 模型
        max_steps: 最大步数
        allowed_tools: 允许使用的工具集 (None 表示全部可用)
        event_callback: 事件回调（用于前端展示子 agent 活动）
        session_dir: session 目录路径（用于保存子 agent 上下文）

    Returns:
        子 Agent 的输出文本
    """
    # 延迟导入避免循环依赖
    from app.agent.agents.simple import SimpleAgent

    # 生成子 agent ID
    sub_agent_id = f"sub_{uuid.uuid4().hex[:8]}"

    # 确定子 agent 的存储位置
    if session_dir:
        subagents_dir = session_dir / "subagents"
        subagents_dir.mkdir(exist_ok=True)
        ctx_file = subagents_dir / f"{sub_agent_id}.jsonl"
    else:
        # 回退：使用临时文件
        import tempfile
        temp_dir = Path(tempfile.mkdtemp(prefix="subagent_"))
        ctx_file = temp_dir / f"{sub_agent_id}.jsonl"

    ctx_file.touch()

    try:
        # 根据类型选择不同提示
        identity = _get_subagent_identity(subagent_type, description)

        # 创建子 Agent
        sub_agent = SimpleAgent(
            model=model,
            base_url=base_url,
            api_key=api_key,
            api_mode=api_mode,
            max_iterations=max_steps,
            context_file=ctx_file,
            event_callback=event_callback,
        )

        # 应用工具策略
        if allowed_tools is not None:
            for name in sub_agent._registry.all_tool_names:
                if name not in allowed_tools:
                    sub_agent._registry.hide(name)

        # 将身份描述注入提示
        full_prompt = f"{identity}\n\n---\n\n{prompt}"
        result = await sub_agent.run(full_prompt)

        output = result.get("final_response", "")

        # 如果输出太短，追加提示让其继续
        if len(output.strip()) < SUMMARY_MIN_LENGTH:
            logger.info("Subagent output too short (%d chars), re-prompting", len(output.strip()))
            followup = (
                f"{output}\n\n"
                "Your output was too short. Please continue and provide a more complete response."
            )
            result2 = await sub_agent.run(followup)
            output2 = result2.get("final_response", "")
            if len(output2.strip()) >= SUMMARY_MIN_LENGTH:
                output = output2
            else:
                output = output + "\n" + output2

        # 返回输出和子 agent ID
        return output, sub_agent_id, str(ctx_file.relative_to(session_dir)) if session_dir else None

    except Exception as e:
        logger.warning("Subagent %s error: %s", subagent_type, e)
        error_msg = f"[Subagent error: {e}]"
        return error_msg, sub_agent_id, str(ctx_file.relative_to(session_dir)) if session_dir else None

    finally:
        # 不再删除子 agent 的 context 文件（已保存到 session 目录）
        pass


def _get_subagent_identity(subagent_type: str, description: str) -> str:
    """根据子 Agent 类型返回系统提示"""
    base_descriptions = {
        "general-purpose": (
            "You are a general-purpose subagent. You help with a variety of tasks "
            "including research, analysis, writing, and problem-solving."
        ),
        "explore": (
            "You are an exploration subagent. You specialize in searching codebases, "
            "finding files, understanding architecture, and gathering information. "
            "Be thorough and report your findings clearly."
        ),
        "plan": (
            "You are a planning subagent. You specialize in designing implementation plans, "
            "breaking down complex tasks, identifying risks, and suggesting approaches. "
            "Think carefully and provide detailed, actionable plans."
        ),
        "researcher": (
            "You are a research subagent. You specialize in web search, information gathering, "
            "fact-checking, and compiling research reports. Search thoroughly, cross-reference "
            "sources, and produce well-structured findings with citations."
        ),
    }

    identity = base_descriptions.get(subagent_type, base_descriptions["general-purpose"])
    if description:
        identity += f"\n\nYour specific task: {description}"
    return identity
