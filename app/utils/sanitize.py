"""通用输入净化模块

对用户提交的文本字段进行 HTML 标签剥离、控制字符移除、长度截断，
防止 XSS 注入和资源耗尽。

用法：
    from app.utils.sanitize import sanitize_str, sanitize_text_field
"""

from __future__ import annotations

import re

# ── 控制字符正则 ──────────────────────────────────
# 保留 \n (0x0a), \r (0x0d), \t (0x09)，其余 C0 控制字符全部移除
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# ── HTML 标签正则（轻量版，不依赖 BeautifulSoup）──
_TAG_RE = re.compile(r"<[^>]*>")


def _strip_tags(text: str) -> str:
    """剥离所有 HTML/XML 标签"""
    return _TAG_RE.sub("", text)


def _remove_control_chars(text: str) -> str:
    """移除控制字符（保留 \\n \\r \\t）"""
    return _CONTROL_CHARS_RE.sub("", text)


def sanitize_str(v: str | None, max_length: int = 10000) -> str | None:
    """净化单行/短文本字段。

    - 剥离 HTML 标签
    - 移除控制字符
    - 折叠换行为空格（适用于单行字段：name, nickname, remark 等）
    - 截断到 max_length

    Parameters
    ----------
    v : str | None
        原始输入，None 原样返回。
    max_length : int
        截断长度上限，默认 10000。

    Returns
    -------
    str | None
    """
    if v is None:
        return None
    text = _strip_tags(v)
    text = _remove_control_chars(text)
    # 折叠换行和多余空白为单个空格（单行语义）
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    if len(text) > max_length:
        text = text[:max_length]
    return text


def sanitize_text_field(v: str | None, max_length: int = 50000) -> str | None:
    """净化长文本字段（保留换行）。

    适用于 bio, description, detail, prompt, content 等允许换行的字段。
    与 sanitize_str 的区别：保留换行符，不折叠空白。

    Parameters
    ----------
    v : str | None
        原始输入，None 原样返回。
    max_length : int
        截断长度上限，默认 50000。

    Returns
    -------
    str | None
    """
    if v is None:
        return None
    text = _strip_tags(v)
    text = _remove_control_chars(text)
    # 去除首尾空白（保留内部换行）
    text = text.strip()
    if len(text) > max_length:
        text = text[:max_length]
    return text
