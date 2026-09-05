"""统一上下文压缩

合并自：
  - code_agent/soul/compaction.py: SimpleCompaction（LLM 摘要压缩）
  - simple-agent/agent/core.py: _compress_context（内联压缩）

提供统一的 Compaction 接口。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.utils.tokens import estimate_tokens


COMPACT_PROMPT = """
You are a helpful assistant that compacts conversation context.
Summarize the conversation above, preserving key information, decisions, code changes, and open questions.
Focus on what is most relevant for continuing work.
Keep the summary concise but complete.
"""


@dataclass
class CompactionResult:
    """压缩结果"""
    messages: list[dict]
    estimated_token_count: int = 0


class SimpleCompaction:
    """使用 LLM 进行上下文摘要压缩。

    将较早的消息压缩为一段摘要，保留最近 N 条消息。
    """

    def __init__(self, max_preserved_messages: int = 2):
        self.max_preserved_messages = max_preserved_messages

    async def compact(
        self,
        messages: list[dict],
        llm,  # LLM 实例
        *,
        custom_instruction: str = "",
    ) -> CompactionResult:
        """执行压缩。

        Args:
            messages: 完整消息列表
            llm: LLM 客户端（需要有 client 和 model_name 属性）
            custom_instruction: 自定义压缩指令
        """
        to_compact, to_preserve = self._prepare(messages, custom_instruction)
        if to_compact is None:
            return CompactionResult(list(to_preserve), self._estimate_tokens(to_preserve))

        # 使用 LLM 生成摘要
        response = await llm.client.chat.completions.create(
            model=llm.model_name,
            messages=[
                {"role": "system", "content": COMPACT_PROMPT},
                {"role": "user", "content": to_compact},
            ],
        )
        summary = response.choices[0].message.content or ""

        result_messages: list[dict] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "<system>Previous context has been compacted:</system>"},
                    {"type": "text", "text": summary},
                ],
            }
        ]
        result_messages.extend(to_preserve)

        token_count = response.usage.total_tokens if response.usage else 0
        return CompactionResult(result_messages, token_count)

    def _prepare(
        self,
        messages: list[dict],
        custom_instruction: str = "",
    ) -> tuple[str | None, list[dict]]:
        """准备压缩。返回 (待压缩文本, 保留的消息列表)。"""
        if len(messages) <= self.max_preserved_messages:
            return None, list(messages)

        history = list(messages)
        preserve_start = len(history)
        n_preserved = 0
        for i in range(len(history) - 1, -1, -1):
            if history[i].get("role") in ("user", "assistant"):
                n_preserved += 1
                if n_preserved == self.max_preserved_messages:
                    preserve_start = i
                    break

        to_compact_msgs = history[:preserve_start]
        to_preserve = history[preserve_start:]

        if not to_compact_msgs:
            return None, to_preserve

        lines = []
        for i, msg in enumerate(to_compact_msgs):
            content = msg.get("content", "")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
                )
            else:
                text = str(content)
            lines.append(f"## Message {i + 1}\nRole: {msg['role']}\n{text}")

        prompt = "\n\n".join(lines) + "\n\n" + COMPACT_PROMPT
        if custom_instruction:
            prompt += f"\n\n**Focus instruction:** {custom_instruction}"

        return prompt, to_preserve

    @staticmethod
    def _estimate_tokens(messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += estimate_tokens(content)
            elif isinstance(content, list):
                for p in content:
                    if isinstance(p, dict) and "text" in p:
                        total += estimate_tokens(p["text"])
        return total
