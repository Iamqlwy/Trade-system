"""记忆自动提取引擎 — 关键词预过滤 + 批量 LLM 提取

设计原则：
  1. 零成本预过滤：用正则匹配中文偏好表达，不消耗 LLM 算力
  2. 攒批提取：累积足够信号后才触发一次 LLM 调用
  3. 会话级粒度：每次提取处理整段对话，而非逐轮

触发条件（满足任一即提取）：
  - 关键词信号数 >= 3
  - 距上次提取已超过 10 轮用户消息
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 关键词预过滤器
# ---------------------------------------------------------------------------

# 中文偏好表达模式（零 LLM 成本）
_PREFERENCE_PATTERNS: list[re.Pattern] = [
    # 直接偏好声明
    re.compile(r"我(只|偏|喜欢|习惯|倾向)(做|看|关注|买|卖|用|选)"),
    re.compile(r"我不?(看|碰|买|关注|喜欢|想|需要)"),
    re.compile(r"(记住|帮我记|别忘了|以后注意)"),

    # 交易风格声明
    re.compile(r"(短线|长线|波段|日内|T\+0|价值投资|趋势交易)"),
    re.compile(r"(激进|保守|稳健|风险).{0,5}(偏好|风格|策略)"),

    # 板块/个股关注
    re.compile(r"(关注|看好|看好|重点看).{0,10}(板块|方向|赛道|行业)"),

    # 指标/策略偏好
    re.compile(r"(喜欢|常用|偏好|习惯).{0,10}(均线|MACD|RSI|KDJ|布林|成交量|量价)"),
]

# A 股股票代码模式
_STOCK_CODE_PATTERN = re.compile(r"\b[036]\d{5}\.(SZ|SH|BJ)\b")


def has_memory_signal(text: str) -> bool:
    """检测文本是否包含值得记忆的信号（零 LLM 成本）。

    返回 True 表示该轮对话可能包含值得提取的偏好/观察信息。
    """
    if not text:
        return False

    # 关键词模式
    for pattern in _PREFERENCE_PATTERNS:
        if pattern.search(text):
            return True

    # 出现多个股票代码（>=2 个说明用户在关注特定标的）
    codes = _STOCK_CODE_PATTERN.findall(text)
    if len(codes) >= 2:
        return True

    return False


def count_memory_signals(text: str) -> int:
    """计算文本中的记忆信号强度（用于阈值判断）。

    返回 0-N 的整数，值越大表示记忆价值越高。
    """
    if not text:
        return 0

    score = 0
    for pattern in _PREFERENCE_PATTERNS:
        if pattern.search(text):
            score += 1

    codes = _STOCK_CODE_PATTERN.findall(text)
    score += len(codes) // 2  # 每 2 个股票代码算 1 分

    return score


# ---------------------------------------------------------------------------
# LLM 批量提取
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """分析以下交易助手的对话历史，提取值得长期记住的信息。

当前已知用户画像：
{existing_profile}

规则：
1. 只提取与交易相关的持久信息（个股偏好、板块关注、策略风格、技术指标、风险偏好等）
2. 如果信息已与已知画像重复，不要重复提取
3. 区分"画像类"（稳定的交易偏好）和"笔记类"（一次性观察或经验教训）
4. 不要提取临时性信息（如"帮我查一下XX"、"看看今天行情"）
5. 每条信息要简洁（一句话），但要包含关键细节

对话历史：
{conversation}

返回严格的 JSON 格式（不要包含其他文字）：
{{
  "profile_updates": {{
    "trading_style": "short_term 或 swing 或 long_term 或 null",
    "risk_level": "conservative 或 moderate 或 aggressive 或 null",
    "focus_sectors": ["板块1", "板块2"],
    "focus_stocks": ["002594.SZ"],
    "indicators": ["MA", "MACD"]
  }},
  "memories": [
    {{"category": "preference|observation|lesson|context", "content": "简洁的一句话描述"}}
  ]
}}

如果没有值得提取的信息，返回：
{{"profile_updates": {{}}, "memories": []}}"""


async def extract_memories_from_conversation(
    user_id: int,
    messages: list[dict[str, Any]],
    *,
    llm_config: dict[str, Any],
    memory_service: Any,
) -> dict[str, Any]:
    """从对话历史中提取记忆（一次 LLM 调用）。

    Args:
        user_id: 用户 ID
        messages: 对话消息列表 [{"role": "user"/"assistant", "content": "..."}]
        llm_config: {"model", "base_url", "api_key", "api_mode"}
        memory_service: MemoryService 实例

    Returns:
        {"profile_updated": bool, "memories_added": int, "raw_result": dict}
    """
    if not messages:
        return {"profile_updated": False, "memories_added": 0, "raw_result": {}}

    # 构建对话文本（限制长度，防止超 token）
    conversation_parts: list[str] = []
    total_chars = 0
    max_chars = 3000  # ~750 tokens

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role not in ("user", "assistant"):
            continue
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            content = " ".join(text_parts)
        if not content:
            continue

        line = f"{'用户' if role == 'user' else '助手'}: {content[:500]}"
        if total_chars + len(line) > max_chars:
            break
        conversation_parts.append(line)
        total_chars += len(line)

    if not conversation_parts:
        return {"profile_updated": False, "memories_added": 0, "raw_result": {}}

    # 获取当前画像
    existing_profile = memory_service.get_profile(user_id)
    profile_text = json.dumps(
        {k: v for k, v in existing_profile.items() if v},
        ensure_ascii=False,
    ) or "(暂无)"

    # 构建提取 prompt
    prompt = _EXTRACTION_PROMPT.format(
        existing_profile=profile_text,
        conversation="\n".join(conversation_parts),
    )

    # 调用 LLM（非流式，低温度）
    try:
        from ..agent.llm import call_llm, create_llm

        llm = create_llm(
            api_key=llm_config.get("api_key", ""),
            base_url=llm_config.get("base_url", ""),
            model_name=llm_config.get("model", "qwen3.6-plus"),
            api_mode=llm_config.get("api_mode", "chat"),
        )

        resp = await call_llm(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            llm=llm,
            temperature=0.3,
        )

        result_text = resp["choices"][0]["message"].get("content", "")
        result = _parse_extraction_result(result_text)

    except Exception:
        logger.exception("Memory extraction LLM call failed for user %d", user_id)
        return {"profile_updated": False, "memories_added": 0, "raw_result": {}}

    # 写入画像更新
    profile_updated = False
    profile_updates = result.get("profile_updates", {})
    if profile_updates:
        # 过滤掉 None 值和空列表
        clean_updates: dict[str, Any] = {}
        for key, value in profile_updates.items():
            if value is None:
                continue
            if isinstance(value, list) and not value:
                continue
            if isinstance(value, str) and not value:
                continue
            clean_updates[key] = value

        if clean_updates:
            # 合并式更新：列表字段追加去重，标量字段覆盖
            current = memory_service.get_profile(user_id)
            merged: dict[str, Any] = {}
            for key, value in clean_updates.items():
                current_val = current.get(key)
                if isinstance(value, list) and isinstance(current_val, list):
                    # 合并列表并去重
                    combined = list(dict.fromkeys(current_val + value))
                    merged[key] = combined
                else:
                    merged[key] = value

            memory_service.update_profile(user_id, merged)
            profile_updated = True

    # 写入记忆
    memories_to_add = result.get("memories", [])
    memories_added = 0
    if memories_to_add:
        memories_added = memory_service.batch_add_memories(user_id, memories_to_add, source="auto")

    logger.info(
        "Memory extraction for user %d: profile_updated=%s, memories_added=%d",
        user_id, profile_updated, memories_added,
    )

    return {
        "profile_updated": profile_updated,
        "memories_added": memories_added,
        "raw_result": result,
    }


def _parse_extraction_result(text: str) -> dict[str, Any]:
    """从 LLM 响应中解析 JSON 结果"""
    text = text.strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试找到第一个 { 到最后一个 } 之间的内容
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    logger.warning("Failed to parse memory extraction result: %s", text[:200])
    return {"profile_updates": {}, "memories": []}
