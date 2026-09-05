"""研究 Agent — 深度搜索 + 知识检索 + 报告生成

来自 search_agent/agent.py — SearchAgent 类

功能：
  - research(): 启动研究任务（standard / detailed / deep 模式）
  - expand(): 在已有研究中补充搜索
  - ask(): 基于已有上下文回答问题
  - 会话持久化
  - 结构化追踪
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.agent.llm import create_llm  # noqa: F401
from app.agent.config import get_agent_home

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class Source:
    """搜索结果来源"""
    url: str
    title: str = ""
    snippet: str = ""
    source_type: str = "web"  # "web" | "knowledge_base"

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "source_type": self.source_type,
        }


@dataclass
class SearchSession:
    """研究会话"""
    session_id: str
    query: str
    mode: str = "research_report"
    sub_queries: dict[str, str] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)
    visited_urls: set[str] = field(default_factory=set)
    report: str = ""
    report_history: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "mode": self.mode,
            "sub_queries": self.sub_queries,
            "sources": [s.to_dict() for s in self.sources],
            "visited_urls": list(self.visited_urls),
            "report": self.report,
            "report_history": self.report_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SearchSession:
        sources = [Source(**s) for s in data.get("sources", [])]
        return cls(
            session_id=data["session_id"],
            query=data["query"],
            mode=data.get("mode", "research_report"),
            sub_queries=data.get("sub_queries", {}),
            sources=sources,
            visited_urls=set(data.get("visited_urls", [])),
            report=data.get("report", ""),
            report_history=data.get("report_history", []),
        )


@dataclass
class SearchResult:
    """研究结果"""
    session_id: str
    report: str
    sources: list[dict]
    sub_queries: list[str]
    total_sources: int
    kb_sources: int = 0
    web_sources: int = 0
    mode: str = "research_report"


# ---------------------------------------------------------------------------
# 时间工具
# ---------------------------------------------------------------------------

def now_ms() -> int:
    return int(time.time() * 1000)


def elapsed_ms(start_ms: int) -> int:
    return now_ms() - start_ms


# ---------------------------------------------------------------------------
# 研究 Agent
# ---------------------------------------------------------------------------

class ResearcherAgent:
    """研究 Agent — 搜索、知识检索、报告生成"""

    def __init__(
        self,
        model: str = "qwen3.6-plus",
        base_url: str = "",
        api_key: str = "",
        api_mode: str = "chat",
        event_callback: Optional[Callable] = None,
    ):
        self._llm = create_llm(
            api_key=api_key,
            base_url=base_url,
            model_name=model,
            api_mode=api_mode,
        )
        self._event_cb = event_callback
        self.sessions: dict[str, SearchSession] = {}

    def _emit(self, event: str, data: dict) -> None:
        if self._event_cb:
            self._event_cb(event, data)

    async def research(
        self,
        query: str,
        mode: str = "research_report",
        context: str = "",
        session_id: Optional[str] = None,
    ) -> SearchResult:
        """启动研究任务。

        Args:
            query: 研究问题
            mode: "research_report" | "detailed_report" | "deep"
            context: 附加上下文
            session_id: 继续已有会话
        """
        if session_id and session_id in self.sessions:
            return await self._continue_research(session_id, query)

        sid = session_id or str(uuid.uuid4())[:12]
        full_query = f"{query}\n\n附加上下文: {context}" if context else query

        logger.info("开始研究: %s", query[:100])
        session = SearchSession(session_id=sid, query=full_query, mode=mode)
        self.sessions[sid] = session

        # 使用 web 搜索获取信息
        from app.agent.tools.web.search import search_web_async
        from app.agent.tools.web.extract import Scraper

        # 搜索
        sources = await search_web_async(query, num_results=5)
        for s in sources:
            source = Source(url=s["url"], title=s.get("title", ""),
                          snippet=s.get("snippet", ""), source_type="web")
            session.sources.append(source)
            session.visited_urls.add(s["url"])

        # 抓取网页内容
        if sources:
            scraper = Scraper()
            urls = [s["url"] for s in sources[:5]]
            scraped = await scraper.scrape_urls(urls)
            for item in scraped:
                url = item["url"]
                content = item.get("raw_content", "")
                if content:
                    # 用 URL 作为 sub_query key
                    session.sub_queries[url] = content[:2000]
            await scraper.close()

        # 生成报告
        combined_context = "\n\n".join(
            f"## {k}\n\n{v}" for k, v in session.sub_queries.items()
        )

        if not combined_context.strip():
            report = f"# 研究报告\n\n问题: {query}\n\n未找到相关搜索结果。"
        else:
            report = await self._generate_report(query, combined_context)

        session.report = report
        session.report_history.append(report)

        return self._build_result(session)

    async def expand(self, session_id: str, topic: str) -> SearchResult:
        """在已有研究中补充搜索某个方向。"""
        if session_id not in self.sessions:
            raise ValueError(f"会话不存在: {session_id}")

        session = self.sessions[session_id]
        logger.info("补充搜索: %s", topic[:80])

        from app.agent.tools.web.search import search_web_async
        from app.agent.tools.web.extract import Scraper

        sources = await search_web_async(topic, num_results=3)
        for s in sources:
            if s["url"] not in session.visited_urls:
                source = Source(url=s["url"], title=s.get("title", ""),
                              snippet=s.get("snippet", ""), source_type="web")
                session.sources.append(source)
                session.visited_urls.add(s["url"])

        # 抓取新 URL
        if sources:
            scraper = Scraper()
            urls = [s["url"] for s in sources[:3] if s["url"] not in session.sub_queries]
            if urls:
                scraped = await scraper.scrape_urls(urls)
                for item in scraped:
                    session.sub_queries[item["url"]] = item.get("raw_content", "")[:2000]
                await scraper.close()

        # 重新生成报告
        combined_context = "\n\n".join(
            f"## {k}\n\n{v}" for k, v in session.sub_queries.items()
        )

        if not combined_context.strip():
            report = f"# 研究报告\n\n问题: {session.query}\n\n未找到相关搜索结果。"
        else:
            report = await self._generate_report(session.query, combined_context)

        session.report = report
        session.report_history.append(report)

        return self._build_result(session)

    async def ask(self, session_id: str, question: str) -> str:
        """基于已有上下文回答问题，不做新搜索。"""
        if session_id not in self.sessions:
            raise ValueError(f"会话不存在: {session_id}")

        session = self.sessions[session_id]
        context = "\n\n".join(session.sub_queries.values())

        prompt = (
            f"Based on the following research context, answer the question concisely.\n\n"
            f"## Context\n{context}\n\n"
            f"## Question\n{question}"
        )

        full_content: list[str] = []
        stream = await self._llm.client.chat.completions.create(
            model=self._llm.model_name,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_content.append(token)
                self._emit("token", {"content": token})
        return "".join(full_content)

    # ---- 状态查询 ----

    def get_session(self, session_id: str) -> SearchSession | None:
        return self.sessions.get(session_id)

    def list_sessions(self) -> list[str]:
        return list(self.sessions.keys())

    # ---- 持久化 ----

    def _auto_save_path(self) -> Path:
        p = get_agent_home() / "research_sessions"
        p.mkdir(parents=True, exist_ok=True)
        return p / "sessions.json"

    def save_sessions(self, path: str | Path | None = None) -> None:
        """持久化所有会话到磁盘"""
        target = Path(path) if path else self._auto_save_path()
        data = {sid: sess.to_dict() for sid, sess in self.sessions.items()}
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("已保存 %d 个会话 → %s", len(data), target)

    def load_sessions(self, path: str | Path | None = None) -> int:
        """从磁盘恢复会话"""
        target = Path(path) if path else self._auto_save_path()
        if not target.exists():
            return 0
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            for sid, sdata in data.items():
                if sid not in self.sessions:
                    self.sessions[sid] = SearchSession.from_dict(sdata)
            logger.info("已恢复 %d 个会话 ← %s", len(data), target)
            return len(data)
        except Exception as e:
            logger.warning("加载会话失败: %s", e)
            return 0

    # ---- 内部方法 ----

    async def _continue_research(self, session_id: str, new_topic: str) -> SearchResult:
        """增量研究"""
        session = self.sessions[session_id]

        from app.agent.tools.web.search import search_web_async
        from app.agent.tools.web.extract import Scraper

        sources = await search_web_async(new_topic, num_results=3)
        for s in sources:
            if s["url"] not in session.visited_urls:
                source = Source(url=s["url"], title=s.get("title", ""),
                              snippet=s.get("snippet", ""), source_type="web")
                session.sources.append(source)
                session.visited_urls.add(s["url"])

        if sources:
            scraper = Scraper()
            urls = [s["url"] for s in sources[:3] if s["url"] not in session.sub_queries]
            if urls:
                scraped = await scraper.scrape_urls(urls)
                for item in scraped:
                    session.sub_queries[item["url"]] = item.get("raw_content", "")[:2000]
                await scraper.close()

        combined_context = "\n\n".join(
            f"## {k}\n\n{v}" for k, v in session.sub_queries.items()
        )

        if not combined_context.strip():
            report = f"# 研究报告\n\n问题: {session.query}\n\n未找到相关搜索结果。"
        else:
            report = await self._generate_report(session.query, combined_context)

        session.report = report
        session.report_history.append(report)

        return self._build_result(session)

    async def _generate_report(self, query: str, text_context: str) -> str:
        """使用 LLM 流式生成研究报告"""
        prompt = (
            f"Write a comprehensive research report based on the following query and collected information.\n\n"
            f"## Query\n{query}\n\n"
            f"## Collected Information\n{text_context}\n\n"
            f"## Instructions\n"
            f"- Write in a clear, structured format with headings\n"
            f"- Cite sources where possible\n"
            f"- Highlight key findings\n"
            f"- Write in the same language as the query"
        )

        try:
            # 使用流式调用
            full_content: list[str] = []
            stream = await self._llm.client.chat.completions.create(
                model=self._llm.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.35,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_content.append(token)
                    self._emit("token", {"content": token})

            return "".join(full_content)
        except Exception as e:
            logger.warning("报告生成失败: %s", e)
            self._emit("error", {"message": str(e)})
            return f"# 研究报告\n\n问题: {query}\n\n报告生成失败: {e}"

    def _build_result(self, session: SearchSession) -> SearchResult:
        kb_count = sum(1 for s in session.sources if s.source_type == "knowledge_base")
        web_count = sum(1 for s in session.sources if s.source_type == "web")

        return SearchResult(
            session_id=session.session_id,
            report=session.report,
            sources=[s.to_dict() for s in session.sources],
            sub_queries=list(session.sub_queries.keys()),
            total_sources=len(session.sources),
            kb_sources=kb_count,
            web_sources=web_count,
            mode=session.mode,
        )
