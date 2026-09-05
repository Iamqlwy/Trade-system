"""统一上下文管理 — 消息历史 + JSONL 持久化 + Token 追踪 + 可见性控制

来自 code_agent/context.py — 异步 Context 类
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypedDict

import aiofiles
import aiofiles.os


# ---------------------------------------------------------------------------
# 消息可见性元数据
# ---------------------------------------------------------------------------

MessageCategory = Literal['system', 'user', 'assistant', 'tool', 'internal', 'metadata']


class MessageMeta(TypedDict, total=False):
    """消息可见性元数据。

    Attributes:
        visible: 前端是否可见
        raw_content: 原始内容（用户输入加工前）
        category: 分类标签（system/user/assistant/tool/internal/metadata）
    """
    visible: bool
    raw_content: str
    category: MessageCategory


# 各 role 的默认可见性规则
_DEFAULT_VISIBILITY: dict[str, dict] = {
    # 前端不可见 — 内部系统信息
    '_system_prompt':  {'visible': False, 'category': 'system'},
    '_usage':          {'visible': False, 'category': 'metadata'},
    '_checkpoint':     {'visible': False, 'category': 'metadata'},
    '_compact':        {'visible': False, 'category': 'metadata'},
    # 前端可见 — 需要渲染 UI
    '_sub_agent':      {'visible': True,  'category': 'internal'},
    '_tool_start':     {'visible': True,  'category': 'internal'},
    '_tool_end':       {'visible': True,  'category': 'internal'},
    # 斜杠命令：前端可见（渲染历史记录），但不进入 agent LLM 上下文
    '_command':        {'visible': True,  'category': 'user'},
    # 斜杠命令的响应：前端可见（显示为 AI 回复），但不进入 agent LLM 上下文
    '_cmd_response':   {'visible': True,  'category': 'assistant'},
    # 标准角色 — 前端可见
    'user':            {'visible': True,  'category': 'user'},
    'assistant':       {'visible': True,  'category': 'assistant'},
    'tool':            {'visible': True,  'category': 'tool'},
}


def _get_default_meta(role: str) -> dict:
    """根据 role 返回默认可见性元数据。"""
    meta = _DEFAULT_VISIBILITY.get(role)
    if meta:
        return dict(meta)  # 返回副本
    # 未知 role 默认可见（宁可多显示也不误隐藏）
    return {'visible': True, 'category': 'internal'}


def _ensure_meta(record: dict) -> dict:
    """确保记录包含 _meta 字段（向后兼容：为旧记录补全默认值）。"""
    if '_meta' not in record:
        role = record.get('role', '')
        record['_meta'] = _get_default_meta(role)
        # 用户消息：自动保存原始内容
        if role == 'user' and 'content' in record:
            record['_meta']['raw_content'] = record['content']
    return record


class Context:
    """内存中的消息历史，支持 JSONL 持久化。

    功能：
      - restore(): 从 JSONL 恢复消息历史
      - append_message(): 追加消息（同时写入磁盘）
      - write_system_prompt(): 写入系统提示
      - update_token_count(): 更新 token 计数
      - clear(): 清空上下文并轮转文件
    """

    def __init__(self, file_backend: Path):
        self._file_backend = file_backend
        self._history: list[dict] = []
        self._token_count: int = 0
        self._pending_token_estimate: int = 0
        self._system_prompt: str | None = None

    async def restore(self) -> bool:
        """从 JSONL 文件恢复上下文。返回是否有数据恢复。

        支持多次调用：如果 _history 已有数据，先清空再从文件重新读取。
        这样即使 restore_session 预加载失败（_history 部分填充），
        后续 _run_conversation 再次调用 restore() 也能正确恢复。
        """
        if not self._file_backend.exists() or self._file_backend.stat().st_size == 0:
            return False

        # 清空旧状态，从文件重新读取（幂等）
        self._history.clear()
        self._token_count = 0
        self._system_prompt = None

        async with aiofiles.open(self._file_backend, encoding="utf-8", errors="replace") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # 向后兼容：为旧记录补全 _meta
                _ensure_meta(record)
                role = record.get("role", "")
                if role == "_system_prompt":
                    self._system_prompt = record.get("content", "")
                elif role == "_usage":
                    self._token_count = record.get("token_count", 0)
                elif role in ("_checkpoint", "_compact", "_sub_agent", "_tool_start", "_tool_end", "_command", "_cmd_response"):
                    pass  # 内部元数据/斜杠命令，不加载到 LLM 上下文
                else:
                    self._history.append(record)
        return True

    @property
    def history(self) -> list[dict]:
        return self._history

    @property
    def token_count(self) -> int:
        return self._token_count

    @property
    def token_count_with_pending(self) -> int:
        return self._token_count + self._pending_token_estimate

    @property
    def system_prompt(self) -> str | None:
        return self._system_prompt

    @property
    def file_backend(self) -> Path:
        return self._file_backend

    async def write_system_prompt(self, prompt: str) -> None:
        """写入系统提示（作为 JSONL 文件的第一行，标记为前端不可见）"""
        record = {
            "role": "_system_prompt",
            "content": prompt,
            "_meta": {"visible": False, "category": "system", "raw_content": prompt},
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        if not self._file_backend.exists() or self._file_backend.stat().st_size == 0:
            self._file_backend.write_text(line, encoding="utf-8")
        else:
            # 前置到现有文件
            tmp_path = self._file_backend.with_suffix(".tmp")
            with (
                tmp_path.open("w", encoding="utf-8") as tmp_f,
                self._file_backend.open(encoding="utf-8") as src_f,
            ):
                tmp_f.write(line)
                while True:
                    chunk = src_f.read(64 * 1024)
                    if not chunk:
                        break
                    tmp_f.write(chunk)
            tmp_path.replace(self._file_backend)
        self._system_prompt = prompt

    async def append_message(self, message: dict | list[dict], meta: dict | None = None) -> None:
        """追加消息到历史和磁盘。

        Args:
            message: 消息 dict 或消息列表
            meta: 可选的可见性元数据覆盖。未提供时根据 role 自动推断。
                  典型字段: visible (bool), category (str), raw_content (str)
        """
        messages = [message] if isinstance(message, dict) else message

        for msg in messages:
            # 确保每条消息都有 _meta
            if '_meta' not in msg:
                msg['_meta'] = dict(meta) if meta else _get_default_meta(msg.get('role', ''))
            # 用户消息：自动保存原始内容
            if msg.get('role') == 'user' and 'content' in msg:
                if 'raw_content' not in msg.get('_meta', {}):
                    msg.setdefault('_meta', {})['raw_content'] = msg['content']

        self._history.extend(messages)
        self._pending_token_estimate += self._estimate_tokens(messages)

        async with aiofiles.open(self._file_backend, "a", encoding="utf-8") as f:
            for msg in messages:
                await f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    async def update_token_count(self, token_count: int) -> None:
        """更新 token 计数（标记为前端不可见）"""
        self._token_count = token_count
        self._pending_token_estimate = 0
        record = {
            "role": "_usage",
            "token_count": token_count,
            "_meta": {"visible": False, "category": "metadata"},
        }
        async with aiofiles.open(self._file_backend, "a", encoding="utf-8") as f:
            await f.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def clear(self) -> None:
        """清空上下文并轮转文件"""
        rotated = self._file_backend.with_suffix(".jsonl.bak")
        if self._file_backend.exists():
            await aiofiles.os.replace(self._file_backend, rotated)
            self._file_backend.touch()
        self._history.clear()
        self._token_count = 0
        self._pending_token_estimate = 0
        self._system_prompt = None

    def _estimate_tokens(self, messages: list[dict]) -> int:
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if "text" in part:
                            total_chars += len(part["text"])
                        elif part.get("type") in ("image_url", "image"):
                            total_chars += 400  # ~100 tokens per image
        return total_chars // 4


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def should_auto_compact(
    token_count: int,
    max_context_size: int,
    trigger_ratio: float,
    reserved_context_size: int,
) -> bool:
    """判断是否需要自动压缩上下文"""
    return (
        token_count >= max_context_size * trigger_ratio
        or token_count + reserved_context_size >= max_context_size
    )
