"""实时 1 分钟 K 线聚合器

从 MarketData 单例读取实时 tick，聚合为 1 分钟 K 线。
增量刷盘到 C:/klines/temp_1m/{ts_code}.csv，每 3 秒执行一次：
  - 同一分钟内 → 只修改文件最后一行
  - 新一分钟   → 追加一行

⚠️ 数据单位：
  - 价格：元
  - 成交量：股（与 1m 历史 CSV 一致）
  - 成交额：元
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FLUSH_INTERVAL = 3  # 秒

# 与 C:/klines/1m/ 现有 CSV 一致的中文表头
CSV_HEADER = "日期,开盘,最高,最低,收盘,成交量(股),成交额(元)\n"


@dataclass
class MinuteBar:
    """1 分钟 K 线"""
    stock_code: str = ""
    minute: str = ""          # "YYYY-MM-DD HH:MM:SS"
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0           # 股
    amount: float = 0.0       # 元


@dataclass
class _FileState:
    """跟踪每个文件最后写入状态，用于增量刷新"""
    last_minute: str = ""              # 最后写入的分钟 key
    last_line_start: int = 0           # 最后一行在文件中的起始字节偏移
    last_line_bytes: bytes = b""       # 最后一行的字节内容


class Kline1mAggregator:
    """实时 1m K 线聚合器（增量刷盘）"""

    def __init__(self, market_data: Any, output_dir: Path):
        self._market_data = market_data
        self._output_dir = output_dir   # C:/klines/temp_1m/

        # 内存中的 bars: {stock_code: {minute_str: MinuteBar}}
        self._bars: dict[str, dict[str, MinuteBar]] = defaultdict(dict)

        # tick 增量跟踪
        self._last_volume: dict[str, int] = {}
        self._last_amount: dict[str, float] = {}

        # 文件状态跟踪（增量刷盘用）
        self._file_states: dict[str, _FileState] = {}

        self._current_date: str = ""
        self._running = False
        self._task = None

    async def start(self) -> None:
        import asyncio
        self._running = True
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._task = asyncio.create_task(self._aggregation_loop())
        logger.info("Kline1mAggregator 启动，输出目录: %s", self._output_dir)

    async def stop(self) -> None:
        import asyncio
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._flush()
        logger.info("Kline1mAggregator 已停止")

    async def _aggregation_loop(self) -> None:
        import asyncio
        flush_counter = 0
        while self._running:
            try:
                self._aggregate()
                flush_counter += 1
                if flush_counter >= FLUSH_INTERVAL:
                    self._flush()
                    flush_counter = 0
            except Exception:
                logger.exception("K线聚合循环异常")
            await asyncio.sleep(1)

    def _aggregate(self) -> None:
        """从 MarketData 采样 tick，更新 1m bars"""
        from .trading_hours import is_continuous_auction
        if not is_continuous_auction():
            return

        ticks = self._market_data.get_all_ticks()
        if not ticks:
            return

        now = datetime.now()
        current_minute = now.strftime("%Y-%m-%d %H:%M")
        current_date = now.strftime("%Y-%m-%d")

        # 跨日清空
        if self._current_date and self._current_date != current_date:
            self._flush()
            self._bars.clear()
            self._last_volume.clear()
            self._last_amount.clear()
            self._file_states.clear()
        self._current_date = current_date

        for code, tick in ticks.items():
            price = float(tick.last_price)
            if price <= 0:
                continue

            bars = self._bars[code]

            if current_minute not in bars:
                bars[current_minute] = MinuteBar(
                    stock_code=code,
                    minute=f"{current_minute}:00",  # "YYYY-MM-DD HH:MM:00"
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=0,
                    amount=0.0,
                )

            bar = bars[current_minute]
            bar.high = max(bar.high, price)
            bar.low = min(bar.low, price)
            bar.close = price

            # 增量成交量/额（tick.volume 是当日累计）
            tick_volume = tick.volume
            tick_amount = float(tick.amount)
            prev_vol = self._last_volume.get(code, 0)
            prev_amt = self._last_amount.get(code, 0.0)
            bar.volume += max(tick_volume - prev_vol, 0)
            bar.amount += max(tick_amount - prev_amt, 0.0)
            self._last_volume[code] = tick_volume
            self._last_amount[code] = tick_amount

    # ── 增量刷盘 ──────────────────────────────

    def _format_row(self, bar: MinuteBar) -> str:
        """格式化一行 CSV（与现有 1m CSV 一致）"""
        return (
            f"{bar.minute},"
            f"{bar.open:.2f},"
            f"{bar.high:.2f},"
            f"{bar.low:.2f},"
            f"{bar.close:.2f},"
            f"{bar.volume},"
            f"{bar.amount:.2f}"
        )

    def _flush(self) -> None:
        """增量刷盘：每只股票只修改最后一行或追加新行

        ⚠️ last_line_bytes 必须包含尾部 b"\\n"，以保证：
          - 替换时 write+truncate 精确覆盖旧行（含 \\n），不留残余字节
          - 追加时 last_line_start 偏移量正确
        """
        if not self._bars:
            return

        for code, bars in self._bars.items():
            if not bars:
                continue

            # 取当前分钟的最新 bar
            latest_minute = max(bars.keys())
            bar = bars[latest_minute]
            row_line = self._format_row(bar) + "\n"
            row_bytes = row_line.encode("gbk")          # 含尾部 \n

            csv_path = self._output_dir / f"{code}.csv"
            state = self._file_states.get(code)

            try:
                if state is None:
                    # 首次：探测文件末尾状态
                    state = self._init_file_state(csv_path)
                    self._file_states[code] = state

                if not csv_path.exists():
                    # 文件不存在 → 新建（带 BOM + 表头）
                    header_bytes = CSV_HEADER.encode("gbk")
                    with open(csv_path, "wb") as f:
                        f.write(b"\xef\xbb\xbf")  # UTF-8 BOM
                        f.write(header_bytes)
                        f.write(row_bytes)         # 含 \n
                    state.last_minute = latest_minute
                    state.last_line_bytes = row_bytes                      # 含 \n
                    state.last_line_start = 3 + len(header_bytes)          # BOM + header
                    continue

                if state.last_minute == latest_minute:
                    # 同一分钟 → 原地替换最后一行（含 \n，精确覆盖）
                    with open(csv_path, "r+b") as f:
                        f.seek(state.last_line_start)
                        f.write(row_bytes)         # 含 \n
                        f.truncate()
                    state.last_line_bytes = row_bytes                      # 含 \n
                else:
                    # 新一分钟 → 追加一行
                    with open(csv_path, "ab") as f:
                        f.write(row_bytes)         # 含 \n
                    state.last_minute = latest_minute
                    state.last_line_start += len(state.last_line_bytes)
                    state.last_line_bytes = row_bytes                      # 含 \n

            except Exception:
                logger.exception("增量刷盘失败: %s", code)

    def _init_file_state(self, csv_path: Path) -> _FileState:
        """读取已有文件，定位最后一行的起始偏移

        ⚠️ last_line_bytes 包含尾部 b"\\n"，与 _flush() 写入格式一致。
        """
        state = _FileState()
        if not csv_path.exists():
            return state

        try:
            raw = csv_path.read_bytes()
            if not raw:
                return state

            # 找最后一行：从末尾往前搜索 \n
            # 跳过末尾可能的空行
            end = len(raw)
            while end > 0 and raw[end - 1:end] == b"\n":
                end -= 1
            if end == 0:
                return state

            # 找最后一行起始位置
            line_start = raw.rfind(b"\n", 0, end)
            line_start = line_start + 1 if line_start >= 0 else 0

            last_line = raw[line_start:end]

            # 解析最后一行的分钟（第一列）
            try:
                decoded = last_line.decode("gbk", errors="replace").strip()
                minute_str = decoded.split(",")[0]  # "YYYY-MM-DD HH:MM:SS"
                # 转为 "YYYY-MM-DD HH:MM" 用于比较
                state.last_minute = minute_str[:16]
            except Exception:
                pass

            state.last_line_start = line_start
            # 包含尾部 \n，与 _flush() 中 row_bytes（含 \n）保持一致
            state.last_line_bytes = last_line + b"\n"
        except Exception:
            logger.debug("初始化文件状态失败: %s", csv_path)

        return state

    # ── 查询接口 ──────────────────────────────

    def get_bars(self, stock_code: str, minutes: int = 5) -> list[MinuteBar]:
        """获取指定股票最近 N 分钟的 1m K 线"""
        bars = self._bars.get(stock_code, {})
        if not bars:
            return []
        sorted_bars = sorted(bars.values(), key=lambda b: b.minute)
        return sorted_bars[-minutes:]

    def get_bar_series(self, stock_code: str, minutes: int = 5) -> list[dict]:
        """获取最近 N 分钟的 1m K 线（dict 格式，方便脚本使用）"""
        return [
            {
                "minute": b.minute,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "amount": b.amount,
            }
            for b in self.get_bars(stock_code, minutes)
        ]
