"""网页内容提取工具

合并自：
  - simple-agent/tools/web.py: web_extract_tool (简单 httpx + html_to_text)
  - search_agent/search/scraper.py: Scraper (trafilatura + 国内外分流)

提供两种提取方式：
  1. simple_extract: 轻量级 httpx + html_to_text（快速、无外部依赖）
  2. scrape: trafilatura 高质量正文提取（国内外智能分流）
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

import httpx

from ..base import Tool, ToolParam, tool_error
from app.agent.utils.url_safety import is_safe_url, is_domestic_url
from app.agent.utils.html import html_to_text

logger = logging.getLogger(__name__)

_COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36"
    ),
}


# ---------------------------------------------------------------------------
# 轻量级提取（httpx + html_to_text）
# ---------------------------------------------------------------------------

def simple_extract(url: str, max_chars: int = 30000) -> str:
    """同步提取网页纯文本（轻量级）"""
    safe, error = is_safe_url(url)
    if not safe:
        return error

    try:
        resp = httpx.get(
            url,
            headers=_COMMON_HEADERS,
            timeout=20,
            follow_redirects=True,
        )
        # 检查重定向目标安全性
        if resp.url != url:
            safe2, err2 = is_safe_url(str(resp.url))
            if not safe2:
                return f"Redirect blocked: {err2}"
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return f"HTTP {e.response.status_code}: {url}"
    except Exception as e:
        return f"Fetch failed: {e}"

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        return f"Unsupported content type: {content_type}"

    text = html_to_text(resp.text)
    if len(text) > max_chars:
        text = text[:max_chars - 200] + "\n... [truncated]"
    return text


# ---------------------------------------------------------------------------
# trafilatura 高质量抓取（异步 + 国内外分流）
# ---------------------------------------------------------------------------

class Scraper:
    """trafilatura 网页抓取器，国内直连、国外走代理"""

    def __init__(self, max_concurrency: int = 5, timeout: int = 10):
        self.max_concurrency = max_concurrency
        self.timeout = timeout
        self._proxy_client: httpx.AsyncClient | None = None
        self._direct_client: httpx.AsyncClient | None = None

    async def _get_proxy_client(self) -> httpx.AsyncClient:
        if self._proxy_client is None:
            self._proxy_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers=_COMMON_HEADERS,
                follow_redirects=True,
                trust_env=True,
            )
        return self._proxy_client

    async def _get_direct_client(self) -> httpx.AsyncClient:
        if self._direct_client is None:
            self._direct_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers=_COMMON_HEADERS,
                follow_redirects=True,
                trust_env=False,
            )
        return self._direct_client

    async def scrape(self, url: str) -> str:
        """抓取单个 URL，返回清洗后的正文"""
        if not url.startswith("http"):
            url = f"https:{url}"

        # 安全检查
        safe, _ = is_safe_url(url)
        if not safe:
            return ""

        domestic = is_domestic_url(url)
        try:
            if domestic:
                client = await self._get_direct_client()
            else:
                client = await self._get_proxy_client()
            response = await client.get(url)
            response.raise_for_status()
        except Exception as e:
            logger.warning("抓取失败 %s: %s", url, e)
            return ""

        try:
            import trafilatura
            extracted = trafilatura.extract(
                response.text,
                include_comments=False,
                include_tables=True,
                include_formatting=False,
                output_format="txt",
                with_metadata=True,
            )
        except ImportError:
            # trafilatura 不可用，降级到 html_to_text
            extracted = html_to_text(response.text)

        if not extracted:
            logger.warning("trafilatura 未能提取正文: %s", url)
            return ""

        text = re.sub(r"\n{3,}", "\n\n", extracted)
        return text[:8000]

    async def scrape_urls(self, urls: list[str]) -> list[dict]:
        """并发抓取多个 URL"""
        if not urls:
            return []

        sem = asyncio.Semaphore(self.max_concurrency)

        async def _scrape_one(url: str) -> dict:
            async with sem:
                content = await self.scrape(url)
                tag = "直连" if is_domestic_url(url) else "代理"
                status = "✓" if content else "✗"
                logger.info("[抓取] %s [%s] %s", status, tag, url[:80])
                return {"url": url, "raw_content": content}

        results = await asyncio.gather(*[_scrape_one(u) for u in urls])
        return [r for r in results if r["raw_content"]]

    async def close(self):
        for c in (self._proxy_client, self._direct_client):
            if c:
                await c.aclose()


# ---------------------------------------------------------------------------
# 函数式工具：web_extract
# ---------------------------------------------------------------------------

def web_extract_tool(url: str) -> str:
    """提取网页内容（同步接口）"""
    if not url or not url.strip():
        return tool_error("url is required.")

    text = simple_extract(url)
    if text.startswith("Blocked:") or text.startswith("HTTP") or text.startswith("Fetch"):
        return tool_error(text)

    return json.dumps({
        "url": url,
        "content": text,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# WebFetch — OOP 工具类
# ---------------------------------------------------------------------------

class WebFetch(Tool):
    """抓取网页内容，返回纯文本"""

    name = "WebFetch"
    description = (
        "Fetch a URL and extract its text content. "
        "Returns the main text of the page (HTML stripped, whitespace cleaned). "
        "Use for reading articles, documentation, or any web page."
    )

    parameters = [
        ToolParam("url", str, "URL to fetch (must include http:// or https://)."),
    ]

    async def call(self, arguments: dict) -> dict:
        url = arguments.get("url", "").strip()
        if not url:
            return {"is_error": True, "message": "url is required."}

        text = simple_extract(url)

        # 检查错误前缀
        if text.startswith("Blocked:") or text.startswith("HTTP") or text.startswith("Fetch"):
            return {"is_error": True, "message": text}

        return {
            "is_error": False,
            "output": json.dumps({
                "url": url,
                "content": text,
            }, ensure_ascii=False),
        }
