"""
量化交易系统 - 行情数据管理

线程安全的实时 tick 存储 + WebSocket 广播。
xtquant 的行情回调来自非 asyncio 线程，需要用 threading.Lock 保护。

⚠️ 线程模型：
  - _lock（threading.Lock）保护 _ticks 字典，因为 update_ticks 由 xtquant 线程调用
  - _sub_lock（threading.Lock）保护 _subscribers 列表，add/remove 来自 WebSocket 连接/断开
  - broadcast() 是 async 方法运行在事件循环，取出 subscribers 快照后逐个发送，
    发送在锁外进行以避免持有锁期间的 await 阻塞 xtquant 线程
"""
import asyncio
import json
import logging
import threading
from decimal import Decimal
from typing import Optional

from fastapi import WebSocket

from .. import datatypes as dt

logger = logging.getLogger(__name__)


class MarketData:
    """全局行情存储（单例）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._ticks: dict[str, dt.Tick] = {}
        self._stock_codes: set[str] = set()
        self._subscribers: list[WebSocket] = []
        self._sub_lock = threading.Lock()

    # ── 行情更新（xtquant 线程调用） ─────────────

    def update_ticks(self, ticks_data: list[dict]) -> None:
        """接收 xtquant 拉取的原始 tick 数据"""
        with self._lock:
            for d in ticks_data:
                code = d.get("stock_code", "")
                if not code:
                    continue
                tick = dt.Tick(
                    stock_code=code,
                    last_price=Decimal(str(d.get("lastPrice", 0))),
                    open=Decimal(str(d.get("open", 0))),
                    high=Decimal(str(d.get("high", 0))),
                    low=Decimal(str(d.get("low", 0))),
                    amount=Decimal(str(d.get("amount", 0))),
                    volume=int(d.get("volume", 0) or 0),
                    ask_price=[
                        Decimal(str(d.get("ask1", 0))),
                        Decimal(str(d.get("ask2", 0))),
                        Decimal(str(d.get("ask3", 0))),
                        Decimal(str(d.get("ask4", 0))),
                        Decimal(str(d.get("ask5", 0))),
                    ],
                    bid_price=[
                        Decimal(str(d.get("bid1", 0))),
                        Decimal(str(d.get("bid2", 0))),
                        Decimal(str(d.get("bid3", 0))),
                        Decimal(str(d.get("bid4", 0))),
                        Decimal(str(d.get("bid5", 0))),
                    ],
                    ask_volume=[int(v or 0) for v in d.get("ask_volumes", [0, 0, 0, 0, 0])],
                    bid_volume=[int(v or 0) for v in d.get("bid_volumes", [0, 0, 0, 0, 0])],
                    timestamp=int(d.get("time", 0) or 0),
                )
                self._ticks[code] = tick

    def update_stock_codes(self, codes: set[str]) -> None:
        with self._lock:
            self._stock_codes = codes

    def get_tick(self, stock_code: str) -> Optional[dt.Tick]:
        with self._lock:
            tick = self._ticks.get(stock_code)
            if tick is None:
                return None
            # 返回深拷贝，防止调用方（如 SimExecutor）修改共享的 Tick 对象
            return dt.Tick(
                stock_code=tick.stock_code,
                last_price=tick.last_price,
                open=tick.open,
                high=tick.high,
                low=tick.low,
                amount=tick.amount,
                volume=tick.volume,
                ask_price=list(tick.ask_price),
                bid_price=list(tick.bid_price),
                ask_volume=list(tick.ask_volume),
                bid_volume=list(tick.bid_volume),
                timestamp=tick.timestamp,
            )

    def get_all_ticks(self) -> dict[str, dt.Tick]:
        """返回所有 tick 的浅拷贝字典。

        ⚠️ 注意：返回的 Tick 对象是内部引用的直接拷贝（非深拷贝），
        调用方不应修改返回的 Tick 对象，否则会污染全局行情存储。
        若只需读取价格，请使用 get_price() 方法。
        """
        with self._lock:
            return dict(self._ticks)

    def get_price(self, stock_code: str) -> Optional[Decimal]:
        """轻量级接口：仅返回最新价，避免深拷贝整个 Tick 对象。"""
        with self._lock:
            tick = self._ticks.get(stock_code)
            if tick is None:
                return None
            return tick.last_price

    @property
    def subscriber_count(self) -> int:
        with self._sub_lock:
            return len(self._subscribers)

    @property
    def tick_count(self) -> int:
        with self._lock:
            return len(self._ticks)

    # ── WebSocket 订阅 ──────────────────────────

    def add_subscriber(self, ws: WebSocket) -> None:
        with self._sub_lock:
            self._subscribers.append(ws)

    def remove_subscriber(self, ws: WebSocket) -> None:
        with self._sub_lock:
            self._subscribers = [s for s in self._subscribers if s is not ws]

    async def broadcast(self) -> None:
        """广播最新行情给所有 WebSocket 订阅者"""
        with self._sub_lock:
            subs = list(self._subscribers)
        if not subs:
            return

        with self._lock:
            ticks_snapshot = {k: self._tick_to_dict(v) for k, v in self._ticks.items()}

        payload = json.dumps(ticks_snapshot, ensure_ascii=False, default=str)
        dead = []
        for ws in subs:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
                logger.debug("移除广播失败的 WebSocket 订阅者")
        for ws in dead:
            self.remove_subscriber(ws)

    @staticmethod
    def _tick_to_dict(tick: dt.Tick) -> dict:
        return {
            "stock_code": tick.stock_code,
            "last_price": str(tick.last_price),
            "open": str(tick.open),
            "high": str(tick.high),
            "low": str(tick.low),
            "amount": str(tick.amount),
            "volume": tick.volume,
            "ask_price": [str(p) for p in tick.ask_price],
            "bid_price": [str(p) for p in tick.bid_price],
            "ask_volume": tick.ask_volume,
            "bid_volume": tick.bid_volume,
            "timestamp": tick.timestamp,
        }
