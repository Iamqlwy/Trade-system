"""
量化交易系统 - 健康监控

后台 asyncio task，定期记录系统关键指标：
  - 策略数量、运行中订单数、成交数
  - 执行器队列深度
  - 数据库连接池状态
  - WebSocket 订阅者数量
  - 内存使用（基础）

超阈值时输出 WARNING 级别告警。
"""

import asyncio
import gc
import logging
import os

logger = logging.getLogger(__name__)


async def health_monitor_loop(
    interval: float = 60.0,
    strategy_manager=None,
    sim_executor=None,
    real_executor=None,
    repository=None,
    market_data=None,
) -> None:
    """
    健康监控后台循环。

    Args:
        interval: 检查间隔（秒）
        strategy_manager: 策略管理器 dict
        sim_executor: SimExecutor 实例
        real_executor: RealExecutor 实例
        repository: Repository 实例
        market_data: MarketData 实例
    """
    logger.info("健康监控启动: 间隔=%.0fs", interval)

    while True:
        try:
            _log_health_metrics(
                strategy_manager, sim_executor, real_executor,
                repository, market_data,
            )
        except Exception:
            logger.exception("健康监控异常")
        await asyncio.sleep(interval)


def _log_health_metrics(
    strategy_manager, sim_executor, real_executor,
    repository, market_data,
) -> None:
    """记录单次健康检查指标"""
    metrics: dict[str, object] = {}

    # 基础内存信息（不依赖 psutil）
    try:
        # /proc/self/status on Linux; fallback on Windows
        if os.name == "posix":
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb = int(line.split()[1])
                        metrics["mem_rss_mb"] = round(kb / 1024, 1)
                        break
    except Exception:
        pass

    # GC 统计
    try:
        gc_stats = gc.get_stats()
        if gc_stats:
            metrics["gc_collections"] = sum(s.get("collections", 0) for s in gc_stats)
    except Exception:
        pass

    # 策略状态
    if strategy_manager is not None:
        metrics["strategies"] = len(strategy_manager)
        total_orders = 0
        total_positions = 0
        total_trades = 0
        for s in strategy_manager.values():
            total_orders += len(s.orders)
            total_positions += len(s.positions)
            total_trades += len(s.trades)
        metrics["total_orders"] = total_orders
        metrics["total_positions"] = total_positions
        metrics["total_trades"] = total_trades

    # 模拟执行器
    if sim_executor is not None:
        metrics["sim_running"] = len(sim_executor.orders_running)
        metrics["sim_done"] = len(sim_executor.orders_over)
        metrics["sim_trades"] = len(sim_executor.trades_done)
        try:
            metrics["sim_queue"] = sim_executor._order_queue.qsize()
        except Exception:
            pass

    # 实盘执行器
    if real_executor is not None:
        metrics["real_running"] = len(real_executor.orders_running)
        metrics["real_done"] = len(real_executor.orders_over)
        metrics["real_trades"] = len(real_executor.trades_done)
        try:
            metrics["real_queue"] = real_executor._callback_queue.qsize()
        except Exception:
            pass

    # 数据库连接池
    if repository is not None:
        try:
            pool = repository.engine.pool
            metrics["db_pool_size"] = pool.size()
            metrics["db_checked_out"] = pool.checkedout()
            metrics["db_checked_in"] = pool.checkedin()
            metrics["db_overflow"] = pool.overflow()
        except Exception:
            pass

    # 行情订阅（使用公开属性以避免绕过 MarketData 的线程锁）
    if market_data is not None:
        try:
            metrics["ws_subscribers"] = market_data.subscriber_count
            metrics["tick_count"] = market_data.tick_count
        except Exception:
            pass

    # 输出
    if metrics:
        parts = [f"{k}={v}" for k, v in metrics.items()]
        logger.info("HEALTH: %s", ", ".join(parts))

    # 告警检查
    _check_alerts(metrics)


def _check_alerts(metrics: dict) -> None:
    """检查告警阈值"""

    # 队列积压
    sim_q = metrics.get("sim_queue", 0)
    if isinstance(sim_q, int) and sim_q > 100:
        logger.warning("ALERT: 模拟订单队列积压 %d", sim_q)

    real_q = metrics.get("real_queue", 0)
    if isinstance(real_q, int) and real_q > 100:
        logger.warning("ALERT: 实盘回调队列积压 %d", real_q)

    # 数据库连接池
    db_overflow = metrics.get("db_overflow", 0)
    if isinstance(db_overflow, int) and db_overflow > 0:
        logger.warning("ALERT: 数据库连接池溢出 %d", db_overflow)

    db_checked_out = metrics.get("db_checked_out", 0)
    db_pool_size = metrics.get("db_pool_size", 5)
    if isinstance(db_checked_out, int) and isinstance(db_pool_size, int):
        if db_checked_out >= db_pool_size:
            logger.warning(
                "ALERT: 数据库连接池耗尽 checked_out=%d pool_size=%d",
                db_checked_out, db_pool_size,
            )
