"""
量化交易系统 - 请求关联 ID 管理

为每个 API 请求 / 订单生成唯一 ID，贯穿整个调用链
（API → Executor → Strategy → Database），便于追踪和定位 bug。

使用 contextvars 实现，天然支持 asyncio 并发隔离。
"""

import logging
import uuid
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Optional, Generator

# ── 上下文变量 ──────────────────────────────────

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_order_id_var: ContextVar[Optional[str]] = ContextVar("order_id", default=None)
_strategy_id_var: ContextVar[Optional[str]] = ContextVar("strategy_id", default=None)
_api_token_id_var: ContextVar[Optional[int]] = ContextVar("api_token_id", default=None)


# ── 获取 / 设置 ─────────────────────────────────

def get_request_id() -> Optional[str]:
    return _request_id_var.get()


def set_request_id(rid: str) -> None:
    _request_id_var.set(rid)


def get_order_id() -> Optional[str]:
    return _order_id_var.get()


def set_order_id(oid: str) -> None:
    _order_id_var.set(oid)


def get_strategy_id() -> Optional[str]:
    return _strategy_id_var.get()


def set_strategy_id(sid: str) -> None:
    _strategy_id_var.set(sid)


def get_api_token_id() -> Optional[int]:
    return _api_token_id_var.get()


def set_api_token_id(tid: int) -> None:
    _api_token_id_var.set(tid)


def generate_request_id() -> str:
    """生成 12 位 hex 请求 ID"""
    return uuid.uuid4().hex[:12]


# ── 上下文管理器 ─────────────────────────────────

@contextmanager
def correlate_order(order_id: str, strategy_id: str = "") -> Generator[None, None, None]:
    """
    在 with 块内的所有日志自动携带 order_id 和 strategy_id。

    Usage:
        with correlate_order("test_5", "test"):
            logger.info("处理订单")  # 日志自动包含 order_id=test_5
    """
    oid_token = _order_id_var.set(order_id)
    sid_token = _strategy_id_var.set(strategy_id) if strategy_id else None
    try:
        yield
    finally:
        _order_id_var.reset(oid_token)
        if sid_token is not None:
            _strategy_id_var.reset(sid_token)


@contextmanager
def correlate_request(request_id: str) -> Generator[None, None, None]:
    """
    在 with 块内的所有日志自动携带 request_id。

    Usage:
        with correlate_request("a1b2c3d4e5f6"):
            logger.info("处理请求")
    """
    token = _request_id_var.set(request_id)
    try:
        yield
    finally:
        _request_id_var.reset(token)


# ── 日志过滤器 ──────────────────────────────────

class CorrelationFilter(logging.Filter):
    """
    自动将 request_id / order_id / strategy_id 注入到 LogRecord。

    添加到 handler 后，所有经过该 handler 的日志记录都会自动携带
    当前上下文中的关联 ID（如果存在）。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or ""
        record.order_id = get_order_id() or ""
        record.strategy_id = get_strategy_id() or ""
        record.api_token_id = get_api_token_id() or ""
        return True
