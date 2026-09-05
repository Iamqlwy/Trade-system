"""HTML → 纯文本转换工具

合并自：
  - simple-agent/tools/web.py: _html_to_text()
"""

from __future__ import annotations

import re


_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    """将 HTML 转换为纯文本。

    - 移除 script 和 style 块
    - 将 <br>、块级元素替换为换行
    - 剥离所有标签
    - 折叠多余空白
    """
    # 移除 script 和 style 块
    html = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", "", html, flags=re.IGNORECASE)
    # <br> → 换行
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    # 块级元素闭合 → 换行
    for tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr",
                "table", "blockquote", "section", "article"):
        html = re.sub(rf"</{tag}>", "\n", html, flags=re.IGNORECASE)
    # 剥离剩余标签
    text = _TAG_RE.sub("", html)
    # HTML 实体解码
    text = _decode_entities(text)
    # 折叠空白
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _decode_entities(text: str) -> str:
    """解码常见 HTML 实体"""
    import html as html_mod
    return html_mod.unescape(text)


def strip_tags(html: str) -> str:
    """仅剥离标签，不做其他处理（用于标题等短文本）"""
    return _TAG_RE.sub("", html).strip()
