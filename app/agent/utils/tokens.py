"""Token 估算工具

合并自：
  - code_agent/context.py: estimate_text_tokens() (len // 4)
  - simple-agent/agent/core.py: _estimate_tokens()
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """粗略估算文本的 token 数量。

    使用 len(text) // 4 近似（适用于英文和混合文本）。
    对于纯中文文本，实际 token 数通常更高（约 1-2 字/token）。
    """
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """估算消息列表的总 token 数。

    遍历所有消息，提取文本内容并累计。
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total += estimate_tokens(part["text"])
        # 为每条消息添加固定开销（角色、格式等）
        total += 4
    return total


def estimate_tool_tokens(tools: list[dict]) -> int:
    """估算工具定义的 token 数"""
    import json
    total = 0
    for tool in tools:
        total += estimate_tokens(json.dumps(tool, ensure_ascii=False))
    return total
