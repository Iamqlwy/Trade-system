"""Web 搜索工具

合并自：
  - simple-agent/tools/web.py: web_search_tool (同步, regex 解析)
  - search_agent/search/searcher.py: Searcher._search_web (异步, DDG 重定向解析)

采用 Bing + DuckDuckGo 双引擎策略：
  - 优先 Bing（国内可用，结果质量高）
  - Bing 失败/无结果时自动回退到 DuckDuckGo
"""

from __future__ import annotations

import asyncio
import base64
import html as html_mod
import json
import logging
import re
import urllib.parse
from typing import Any

import httpx

from ..base import Tool, ToolParam, tool_error
from app.agent.utils.html import strip_tags

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
}

_web_search_semaphore = asyncio.Semaphore(1)


# ---------------------------------------------------------------------------
# DDG URL 解析
# ---------------------------------------------------------------------------

def extract_ddg_real_url(href: str) -> str:
    """从 DuckDuckGo 重定向 URL 中提取真实目标 URL。

    DuckDuckGo HTML 搜索结果中的链接格式：
    - 普通结果: /l/?uddg=<url-encoded-real-url>&rut=...
    - 广告结果: /y.js?...&u=<base64(url-encoded-real-url)>...
    """
    href = html_mod.unescape(href)

    # 普通结果
    if "duckduckgo.com/l/" in href:
        parsed = urllib.parse.urlparse(href if "//" in href[:8] else f"https:{href}")
        qs = urllib.parse.parse_qs(parsed.query)
        uddg = qs.get("uddg", [])
        if uddg:
            return urllib.parse.unquote(uddg[0])

    # 广告结果
    if "duckduckgo.com/y.js" in href:
        parsed = urllib.parse.urlparse(href if "//" in href[:8] else f"https:{href}")
        qs = urllib.parse.parse_qs(parsed.query)
        u_param = qs.get("u", [])
        if u_param:
            try:
                decoded = base64.urlsafe_b64decode(u_param[0]).decode("utf-8")
                return urllib.parse.unquote(decoded)
            except Exception:
                return ""

    # 其他 DDG 内部链接 → 丢弃
    if "duckduckgo.com" in href:
        return ""
    return href


def parse_ddg_html(html: str, top_k: int = 10) -> list[dict[str, str]]:
    """解析 DuckDuckGo HTML 搜索结果，返回 [{title, url, snippet}, ...]"""
    results: list[dict[str, str]] = []

    link_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (href, title) in enumerate(links[:top_k]):
        title = strip_tags(title).strip()
        snippet = ""
        if i < len(snippets):
            snippet = strip_tags(snippets[i]).strip()
        if href and title:
            real_url = extract_ddg_real_url(href)
            if not real_url:
                continue
            results.append({"title": title, "url": real_url, "snippet": snippet})

    return results


# ---------------------------------------------------------------------------
# Bing 搜索（国内回退）
# ---------------------------------------------------------------------------

def parse_bing_html(html: str, top_k: int = 10) -> list[dict[str, str]]:
    """解析 Bing HTML 搜索结果，返回 [{title, url, snippet}, ...]"""
    results: list[dict[str, str]] = []

    # Bing 搜索结果结构: <li class="b_algo"> 包含 <h2><a href="...">title</a></h2> 和 <p class="b_lineclamp...">snippet</p>
    item_pattern = re.compile(
        r'<li\s+class="b_algo"[^>]*>(.*?)</li>',
        re.DOTALL,
    )
    link_pattern = re.compile(
        r'<h2[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<p[^>]*class="[^"]*b_(lineclamp|paratsu)[^"]*"[^>]*>(.*?)</p>',
        re.DOTALL,
    )

    items = item_pattern.findall(html)

    for item_html in items[:top_k]:
        link_match = link_pattern.search(item_html)
        if not link_match:
            continue
        url = html_mod.unescape(link_match.group(1))
        title = strip_tags(link_match.group(2)).strip()

        snippet = ""
        snip_match = snippet_pattern.search(item_html)
        if snip_match:
            snippet = strip_tags(snip_match.group(2)).strip()

        if title and url:
            # Bing 有时返回相对 URL
            if url.startswith("/"):
                url = f"https://www.bing.com{url}"
            results.append({"title": title, "url": url, "snippet": snippet})

    return results


async def _search_bing_async(query: str, num_results: int = 5) -> list[dict[str, str]]:
    """异步 Bing 搜索（国内可用）"""
    if not query or not query.strip():
        return []

    num_results = min(max(num_results, 1), 10)
    search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={num_results}"

    try:
        async with _web_search_semaphore:
            async with httpx.AsyncClient(
                headers=_HEADERS,
                timeout=httpx.Timeout(15),
                follow_redirects=True,
                trust_env=True,
            ) as client:
                resp = await client.get(search_url)
                html = resp.text
    except Exception as e:
        logger.warning("Bing search failed: %s", e)
        return []

    return parse_bing_html(html, num_results)


def _search_bing_sync(query: str, num_results: int = 5) -> list[dict[str, str]]:
    """同步 Bing 搜索"""
    if not query or not query.strip():
        return []

    num_results = min(max(num_results, 1), 10)
    search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={num_results}"

    try:
        resp = httpx.get(
            search_url,
            headers=_HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Bing search failed: %s", e)
        return []

    return parse_bing_html(resp.text, num_results)


# ---------------------------------------------------------------------------
# 异步搜索（供 research agent 等异步调用者使用）
# ---------------------------------------------------------------------------

async def search_web_async(query: str, num_results: int = 5) -> list[dict[str, str]]:
    """异步 Web 搜索 — 先 Bing，失败后回退 DDG"""
    if not query or not query.strip():
        return []

    num_results = min(max(num_results, 1), 10)

    # 先尝试 Bing
    results = await _search_bing_async(query, num_results)
    if results:
        return results

    # Bing 无结果，回退 DuckDuckGo
    logger.info("Bing 无结果，回退到 DuckDuckGo 搜索: %s", query[:50])
    results = await _search_ddg_async(query, num_results)
    return results


async def _search_ddg_async(query: str, num_results: int = 5) -> list[dict[str, str]]:
    """异步 DuckDuckGo 搜索"""
    try:
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        async with _web_search_semaphore:
            async with httpx.AsyncClient(
                headers=_HEADERS,
                timeout=httpx.Timeout(15),
                follow_redirects=True,
                trust_env=True,
            ) as client:
                resp = await client.get(search_url)
                html = resp.text
    except Exception as e:
        logger.warning("DuckDuckGo search failed: %s", e)
        return []

    return parse_ddg_html(html, num_results)


# ---------------------------------------------------------------------------
# 同步搜索（供函数式工具注册使用）
# ---------------------------------------------------------------------------

def web_search_tool(query: str, num_results: int = 5) -> str:
    """Web 搜索（同步接口）— Bing + DDG 双引擎"""
    if not query or not query.strip():
        return tool_error("query is required.")

    num_results = min(max(num_results, 1), 10)

    # 先 Bing
    results = _search_bing_sync(query, num_results)
    if results:
        return json.dumps({
            "query": query,
            "results": results,
            "count": len(results),
            "engine": "bing",
        }, ensure_ascii=False)

    # 回退 DuckDuckGo
    try:
        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=_HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
        results = parse_ddg_html(resp.text, num_results)
        if results:
            return json.dumps({
                "query": query,
                "results": results,
                "count": len(results),
                "engine": "duckduckgo",
            }, ensure_ascii=False)
    except Exception as e:
        logger.warning("DDG sync search failed: %s", e)

    return json.dumps({
        "query": query,
        "results": [],
        "count": 0,
        "engine": "none",
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# OOP 工具类
# ---------------------------------------------------------------------------

class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web. Returns title, URL, and snippet. "
        "Uses DuckDuckGo with Bing fallback for reliability."
    )
    parameters = [
        ToolParam("query", str, "Search query.", required=True),
        ToolParam("num_results", int, "Number of results (1-10, default 5).", default=5, required=False),
    ]

    async def call(self, arguments: dict) -> Any:
        query = arguments.get("query", "")
        num_results = arguments.get("num_results", 5)
        results = await search_web_async(query, num_results)
        return {
            "query": query,
            "results": results,
            "count": len(results),
        }

