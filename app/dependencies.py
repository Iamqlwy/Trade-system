"""
量化交易系统 - 依赖注入

FastAPI 路由使用的共享依赖。

⚠️ Singleton 初始化使用双重检查锁（threading.Lock），防止并发请求
  同时创建多个 executor 实例，导致后台任务泄漏和状态不一致。
"""
import asyncio
import logging
import threading
from pathlib import Path

from .config import settings
from .engine.strategy import Strategy
from .market.data import MarketData
from .engine.sim_executor import SimExecutor
from .engine.real_executor import RealExecutor
from .store.repository import Repository

logger = logging.getLogger(__name__)

# 全局单例
market_data = MarketData()
strategy_manager: dict[str, Strategy] = {}
repository = Repository()
sim_executor: SimExecutor | None = None
real_executor: RealExecutor | None = None
_exec_lock = threading.Lock()

# 策略级并发锁（防止同一策略的并发下单/撤单竞态）
_strategy_locks: dict[str, asyncio.Lock] = {}
_strategy_locks_guard = threading.Lock()


def get_strategy_lock(strategy_id: str) -> asyncio.Lock:
    """获取指定策略的 asyncio.Lock，用于保护下单/撤单等关键操作"""
    with _strategy_locks_guard:
        if strategy_id not in _strategy_locks:
            _strategy_locks[strategy_id] = asyncio.Lock()
        return _strategy_locks[strategy_id]

# ── Monitor Engine ───────────────────────────
_monitor_engine = None
_monitor_lock = threading.Lock()


def get_monitor_engine():
    """获取 MonitorEngine 单例（懒初始化）"""
    global _monitor_engine
    if _monitor_engine is None:
        with _monitor_lock:
            if _monitor_engine is None:
                from .monitor.engine import MonitorEngine
                _monitor_engine = MonitorEngine(
                    market_data=market_data,
                )
                logger.info("MonitorEngine 单例已创建")
    return _monitor_engine


def get_market_data() -> MarketData:
    return market_data


def get_strategies() -> dict[str, Strategy]:
    return strategy_manager


def get_strategy(strategy_id: str) -> Strategy | None:
    return strategy_manager.get(strategy_id)


def get_sim_executor() -> SimExecutor:
    global sim_executor
    if sim_executor is None:
        with _exec_lock:
            if sim_executor is None:
                from .engine.commission import get_calculator
                sim_executor = SimExecutor(market_data, strategy_manager, get_calculator)
                logger.info("SimExecutor 单例已创建")
    return sim_executor


def get_real_executor() -> RealExecutor:
    global real_executor
    if real_executor is None:
        with _exec_lock:
            if real_executor is None:
                real_executor = RealExecutor(strategy_manager)
                logger.info("RealExecutor 单例已创建")
    return real_executor


# ── Kline 1m Aggregator ─────────────────────
_kline_1m = None
_kline_1m_lock = threading.Lock()
_KLINES_1M_DIR = Path("C:/klines/temp_1m")


def get_kline_1m():
    """获取 Kline1mAggregator 单例"""
    global _kline_1m
    if _kline_1m is None:
        with _kline_1m_lock:
            if _kline_1m is None:
                from .market.kline_1m import Kline1mAggregator
                _kline_1m = Kline1mAggregator(
                    market_data=market_data,
                    output_dir=_KLINES_1M_DIR,
                )
                logger.info("Kline1mAggregator 单例已创建")
    return _kline_1m
