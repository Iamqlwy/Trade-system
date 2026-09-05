"""统一 LLM 客户端 — 异步优先，支持 OpenAI + Anthropic

合并自：
  - simple-agent/agent/llm.py: 同步 OpenAI + Anthropic + tenacity 重试
  - code_agent/llm.py: 异步 AsyncOpenAI + LLM dataclass

设计原则：
  - 异步优先（AsyncOpenAI），同步调用者用 asyncio.run() 包装
  - 统一返回 OpenAI 格式（Anthropic 响应自动转换）
  - 支持流式和非流式
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from .config import LLMModel, LLMProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM 数据类
# ---------------------------------------------------------------------------

@dataclass
class LLM:
    """LLM 客户端包装"""
    client: AsyncOpenAI
    model_name: str
    max_context_size: int = 128_000
    capabilities: set[str] = field(default_factory=set)
    api_mode: str = "chat"  # "chat" | "anthropic"

    @property
    def chat_provider(self) -> AsyncOpenAI:
        return self.client


# ---------------------------------------------------------------------------
# 创建 LLM 实例
# ---------------------------------------------------------------------------

def create_llm(
    provider: Optional[LLMProvider] = None,
    model: Optional[LLMModel] = None,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
    api_mode: str = "chat",
) -> LLM:
    """创建 LLM 客户端。

    可以通过 Provider/Model 对象或直接传参。
    """
    if provider and model:
        key = provider.api_key.get_secret_value() or os.getenv("OPENAI_API_KEY", "")
        url = provider.base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        name = model.model
        max_ctx = model.max_context_size
    else:
        key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        url = base_url or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1"
        name = model_name or os.getenv("LLM_MODEL") or "qwen3.6-plus"
        max_ctx = int(os.getenv("OPENAI_MAX_CONTEXT_SIZE", "128000"))

    client = AsyncOpenAI(api_key=key, base_url=url, max_retries=2)

    return LLM(
        client=client,
        model_name=name,
        max_context_size=max_ctx,
        api_mode=api_mode,
    )


# ---------------------------------------------------------------------------
# 异步 LLM 调用（带重试）
# ---------------------------------------------------------------------------

RETRYABLE = (TimeoutError, ConnectionError)


def _is_retryable(exception: BaseException) -> bool:
    if isinstance(exception, RETRYABLE):
        return True
    msg = str(exception).lower()
    for keyword in ("timeout", "connection", "rate limit", "server error",
                    "503", "502", "429", "internal server error"):
        if keyword in msg:
            return True
    return False


def _safe_retry_callback(retry_state):
    """重试耗尽后安全返回最后一次结果"""
    try:
        if hasattr(retry_state, "outcome") and retry_state.outcome is not None:
            return retry_state.outcome.result()
    except Exception:
        pass
    return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception(_is_retryable),
    retry_error_callback=_safe_retry_callback,
)
async def call_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    llm: LLM,
    *,
    temperature: float = 0.7,
    stream: bool = False,  # noqa: ARG001 — reserved for streaming implementation
) -> dict[str, Any]:
    """调用 LLM 并返回 OpenAI 格式响应。

    自动根据 llm.api_mode 选择 OpenAI 或 Anthropic API。
    """
    if llm.api_mode == "anthropic":
        return await _call_anthropic(messages, tools, llm, temperature=temperature)
    return await _call_openai(messages, tools, llm, temperature=temperature)


async def _call_openai(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    llm: LLM,
    *,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """OpenAI Chat Completions API"""
    kwargs: dict[str, Any] = {
        "model": llm.model_name,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    t0 = time.monotonic()
    resp = await llm.client.chat.completions.create(**kwargs)
    elapsed = time.monotonic() - t0
    logger.debug("OpenAI call: model=%s elapsed=%.1fs", llm.model_name, elapsed)

    return resp.model_dump()


def _convert_content_for_anthropic(content: Any) -> Any:
    """将 OpenAI 格式的 content 转换为 Anthropic 格式。

    处理多模态内容：
    - OpenAI: {"type": "image_url", "image_url": {"url": "https://..."}}
    - Anthropic: {"type": "image", "source": {"type": "url", "url": "https://..."}}
    - tool_result 中的 content 也做同样转换
    """
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return content

    result: list[dict] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type", "")
        if part_type == "text":
            result.append({"type": "text", "text": part.get("text", "")})
        elif part_type == "image_url":
            img_url = part.get("image_url", {}).get("url", "")
            if img_url:
                result.append({
                    "type": "image",
                    "source": {"type": "url", "url": img_url},
                })
        elif part_type == "tool_result":
            # tool_result 内部也可能有图片
            inner = part.get("content", "")
            converted_inner = _convert_content_for_anthropic(inner)
            result.append({**part, "content": converted_inner})
        else:
            # 保持原样（可能是已经是 Anthropic 格式的内容）
            result.append(part)
    return result


async def _call_anthropic(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    llm: LLM,
    *,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """Anthropic Messages API，返回转换为 OpenAI 格式"""
    import anthropic

    # 提取 system 消息并转换角色
    system_content: list[dict] = []
    anthropic_msgs: list[dict] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_content.append({"type": "text", "text": content if isinstance(content, str) else ""})
            continue

        anthropic_role = "assistant" if role == "assistant" else "user"
        if role == "tool":
            tool_use_id = msg.get("tool_call_id", "")
            # 转换 tool_result 内容（可能包含图片）
            converted_content = _convert_content_for_anthropic(content) if content else "(no output)"
            tool_result = {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": converted_content,
            }
            # 合并连续的 tool_result 到一个 user 消息
            if (anthropic_msgs
                    and anthropic_msgs[-1]["role"] == "user"
                    and isinstance(anthropic_msgs[-1].get("content"), list)
                    and anthropic_msgs[-1]["content"]
                    and anthropic_msgs[-1]["content"][0].get("type") == "tool_result"):
                anthropic_msgs[-1]["content"].append(tool_result)
            else:
                anthropic_msgs.append({"role": "user", "content": [tool_result]})
            continue

        # 转换用户/助手消息内容（处理多模态）
        anthropic_content = _convert_content_for_anthropic(content)
        anthropic_msgs.append({"role": anthropic_role, "content": anthropic_content})

    # 转换工具定义
    anthropic_tools: list[dict] = []
    for t in tools:
        func = t.get("function", t)
        anthropic_tools.append({
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        })

    # 使用 Anthropic SDK（同步 API 包装为异步）
    api_key = llm.client.api_key
    base_url = str(llm.client.base_url).rstrip("/")
    # Anthropic SDK 的 base_url 需要去掉 /v1 后缀
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]

    sync_client = anthropic.Anthropic(
        base_url=base_url or None,
        api_key=api_key,
        max_retries=2,
    )

    kwargs: dict[str, Any] = {
        "model": llm.model_name,
        "messages": anthropic_msgs,
        "max_tokens": 16000,
        "temperature": temperature,
    }
    if system_content:
        kwargs["system"] = [{"type": "text", "text": "".join(c.get("text", "") for c in system_content)}]
    if anthropic_tools:
        kwargs["tools"] = anthropic_tools

    t0 = time.monotonic()
    # 在线程池中运行同步调用
    import asyncio
    resp = await asyncio.to_thread(sync_client.messages.create, **kwargs)
    elapsed = time.monotonic() - t0
    logger.debug("Anthropic call: model=%s elapsed=%.1fs", llm.model_name, elapsed)

    return _anthropic_to_openai_format(resp)


def _anthropic_to_openai_format(resp) -> dict[str, Any]:
    """将 Anthropic 响应转换为 OpenAI chat.completions 格式"""
    content_blocks = resp.content
    text_parts: list[str] = []
    tool_calls: list[dict] = []

    for block in content_blocks:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "type": "function",
                "function": {
                    "name": block.name,
                    "arguments": json.dumps(block.input) if isinstance(block.input, dict) else str(block.input),
                },
            })

    message: dict[str, Any] = {
        "role": "assistant",
        "content": "\n".join(text_parts) if text_parts else None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls

    return {
        "id": resp.id,
        "model": resp.model,
        "choices": [
            {"index": 0, "message": message, "finish_reason": resp.stop_reason or "stop"},
        ],
        "usage": {
            "prompt_tokens": resp.usage.input_tokens if resp.usage else 0,
            "completion_tokens": resp.usage.output_tokens if resp.usage else 0,
            "total_tokens": (resp.usage.input_tokens + resp.usage.output_tokens) if resp.usage else 0,
        },
    }


# ---------------------------------------------------------------------------
# 流式 LLM 调用（异步生成器）
# ---------------------------------------------------------------------------

async def call_llm_stream(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    llm: LLM,
    *,
    temperature: float = 0.7,
) -> AsyncIterator[dict[str, Any]]:
    """流式调用 LLM，yield 增量事件。

    Yield 的事件格式：
      {"type": "delta", "content": "partial text"}
      {"type": "tool_call_delta", "index": 0, "id": "...", "name": "...", "arguments": "..."}
      {"type": "done", "message": {...完整消息...}, "usage": {...}}

    自动根据 llm.api_mode 选择 OpenAI 或 Anthropic API。
    """
    if llm.api_mode == "anthropic":
        async for event in _stream_anthropic(messages, tools, llm, temperature=temperature):
            yield event
    else:
        async for event in _stream_openai(messages, tools, llm, temperature=temperature):
            yield event


async def _stream_openai(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    llm: LLM,
    *,
    temperature: float = 0.7,
) -> AsyncIterator[dict[str, Any]]:
    """OpenAI 流式 Chat Completions"""
    kwargs: dict[str, Any] = {
        "model": llm.model_name,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    t0 = time.monotonic()
    stream = await llm.client.chat.completions.create(**kwargs)

    # 累积完整消息（用于最终 yield done）
    full_content: list[str] = []
    tool_calls_acc: dict[int, dict] = {}  # index → {id, type, function: {name, arguments}}
    finish_reason = ""

    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        finish_reason = chunk.choices[0].finish_reason or finish_reason

        # 文本增量
        if delta.content is not None:
            full_content.append(delta.content)
            yield {"type": "delta", "content": delta.content}

        # 工具调用增量
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in tool_calls_acc:
                    tool_calls_acc[idx] = {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                acc = tool_calls_acc[idx]
                if tc_delta.id:
                    acc["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        acc["function"]["name"] = tc_delta.function.name
                    if tc_delta.function.arguments:
                        acc["function"]["arguments"] += tc_delta.function.arguments
                        yield {
                            "type": "tool_call_delta",
                            "index": idx,
                            "id": tc_delta.id or "",
                            "name": tc_delta.function.name or "",
                            "arguments": tc_delta.function.arguments,
                        }

    elapsed = time.monotonic() - t0
    logger.debug("OpenAI stream: model=%s elapsed=%.1fs", llm.model_name, elapsed)

    # 构建完整消息
    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(full_content) if full_content else None,
    }
    if tool_calls_acc:
        message["tool_calls"] = [
            tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())
        ]

    yield {
        "type": "done",
        "message": message,
        "finish_reason": finish_reason,
    }


async def _stream_anthropic(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    llm: LLM,
    *,
    temperature: float = 0.7,
) -> AsyncIterator[dict[str, Any]]:
    """Anthropic 流式 Messages API"""
    import anthropic
    import asyncio

    # 复用非流式的消息转换逻辑
    system_content: list[dict] = []
    anthropic_msgs: list[dict] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_content.append({"type": "text", "text": content if isinstance(content, str) else ""})
            continue

        anthropic_role = "assistant" if role == "assistant" else "user"
        if role == "tool":
            tool_use_id = msg.get("tool_call_id", "")
            # 转换 tool_result 内容（可能包含图片）
            converted_content = _convert_content_for_anthropic(content) if content else "(no output)"
            tool_result = {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": converted_content,
            }
            if (anthropic_msgs
                    and anthropic_msgs[-1]["role"] == "user"
                    and isinstance(anthropic_msgs[-1].get("content"), list)
                    and anthropic_msgs[-1]["content"]
                    and anthropic_msgs[-1]["content"][0].get("type") == "tool_result"):
                anthropic_msgs[-1]["content"].append(tool_result)
            else:
                anthropic_msgs.append({"role": "user", "content": [tool_result]})
            continue

        # 转换用户/助手消息内容（处理多模态）
        anthropic_content = _convert_content_for_anthropic(content)
        anthropic_msgs.append({"role": anthropic_role, "content": anthropic_content})

    anthropic_tools: list[dict] = []
    for t in tools:
        func = t.get("function", t)
        anthropic_tools.append({
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        })

    api_key = llm.client.api_key
    base_url = str(llm.client.base_url).rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]

    sync_client = anthropic.Anthropic(
        base_url=base_url or None,
        api_key=api_key,
        max_retries=2,
    )

    kwargs: dict[str, Any] = {
        "model": llm.model_name,
        "messages": anthropic_msgs,
        "max_tokens": 16000,
        "temperature": temperature,
        "stream": True,
    }
    if system_content:
        kwargs["system"] = [{"type": "text", "text": "".join(c.get("text", "") for c in system_content)}]
    if anthropic_tools:
        kwargs["tools"] = anthropic_tools

    t0 = time.monotonic()

    # Anthropic SDK 的流式是同步迭代器，在队列中运行
    import queue
    import threading

    event_queue: queue.Queue = queue.Queue()
    _SENTINEL = object()

    def _run_stream():
        try:
            with sync_client.messages.stream(**kwargs) as stream_ctx:
                for event in stream_ctx:
                    event_type = event.type
                    if event_type == "content_block_start":
                        cb = event.content_block
                        if cb.type == "text":
                            event_queue.put(("text_start", cb.text or ""))
                        elif cb.type == "tool_use":
                            event_queue.put(("tool_start", {"id": cb.id, "name": cb.name}))
                    elif event_type == "content_block_delta":
                        d = event.delta
                        if d.type == "text_delta":
                            event_queue.put(("text_delta", d.text))
                        elif d.type == "input_json_delta":
                            event_queue.put(("tool_args_delta", d.partial_json))
                    elif event_type == "content_block_stop":
                        event_queue.put(("block_stop", None))
                    elif event_type == "message_stop":
                        event_queue.put(("message_stop", None))
        except Exception as e:
            event_queue.put(("error", str(e)))
        finally:
            event_queue.put((_SENTINEL, None))

    thread = threading.Thread(target=_run_stream, daemon=True)
    thread.start()

    # 累积完整消息
    full_content: list[str] = []
    current_tool: dict | None = None
    tool_calls: list[dict] = []
    tool_args_acc: list[str] = []

    while True:
        try:
            ev_type, ev_data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: event_queue.get(timeout=300)
            )
        except Exception:
            # 队列超时或线程异常 — 中止流式读取
            logger.warning("Anthropic stream queue timeout or error")
            yield {"type": "error", "message": "Stream timeout: no event received within 300s"}
            break
        if ev_type is _SENTINEL:
            break

        if ev_type == "error":
            yield {"type": "error", "message": ev_data}
            break
        elif ev_type == "text_start":
            if ev_data:
                full_content.append(ev_data)
                yield {"type": "delta", "content": ev_data}
        elif ev_type == "text_delta":
            full_content.append(ev_data)
            yield {"type": "delta", "content": ev_data}
        elif ev_type == "tool_start":
            current_tool = {"id": ev_data["id"], "type": "function", "function": {"name": ev_data["name"], "arguments": ""}}
            tool_args_acc = []
        elif ev_type == "tool_args_delta":
            tool_args_acc.append(ev_data)
            yield {
                "type": "tool_call_delta",
                "index": len(tool_calls),
                "id": current_tool["id"] if current_tool else "",
                "name": "",
                "arguments": ev_data,
            }
        elif ev_type == "block_stop":
            if current_tool is not None:
                current_tool["function"]["arguments"] = "".join(tool_args_acc)
                tool_calls.append(current_tool)
                current_tool = None
                tool_args_acc = []
        elif ev_type == "message_stop":
            pass

    elapsed = time.monotonic() - t0
    logger.debug("Anthropic stream: model=%s elapsed=%.1fs", llm.model_name, elapsed)

    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(full_content) if full_content else None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls

    yield {
        "type": "done",
        "message": message,
        "finish_reason": "stop",
    }
