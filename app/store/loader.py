"""
量化交易系统 - 启动状态恢复

从 MySQL 加载策略、持仓、批次、结算记录，
恢复内存中的策略状态。

⚠️ seq_counter 恢复：
  - 从今日订单中扫描 order_id 提取最大 seq 号，避免重启后 order_id 冲突
  - _extract_strategy_base 通过 rfind("_") + tail.isdigit() 解析，
    而非 rsplit("_", 1)[0]，因为策略ID本身可能含下划线
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from .. import datatypes as dt
from ..constants import OrderType, OrderStatus, PriceType
from ..engine.strategy import Strategy
from ..engine.commission import CommissionCalculator, set_calculator, get_calculator
from ..config import settings
from .repository import Repository

logger = logging.getLogger(__name__)


def restore_strategies(repo: Repository) -> dict[str, Strategy]:
    """从数据库恢复所有策略的内存状态"""
    with repo.SessionLocal() as session:
        strategies = repo.load_strategies(session)
        all_positions = repo.load_positions(session)
        all_lots = repo.load_lots(session)
        all_settlements = repo.load_settlements(session)
        repo.load_commission_configs(session)

        # 恢复序号计数器（查所有历史订单，避免跨日后 seq 冲突）
        all_max_seq = repo.get_max_order_seq(session)
        for sid, strategy in strategies.items():
            # 恢复持仓
            if sid in all_positions:
                strategy.positions = all_positions[sid]

            # 恢复 FIFO 批次
            if sid in all_lots:
                import heapq
                for code, lot_heap in all_lots[sid].items():
                    strategy._lots[code] = lot_heap

            # 恢复结算
            if sid in all_settlements:
                strategy.settlements = all_settlements[sid]

            strategy._seq_counter = all_max_seq.get(sid, 0)

            logger.info("恢复策略 %s: 可用资金=%s, 持仓%d只",
                        sid, strategy.available_cash, len(strategy.positions))

    return strategies


def restore_unfinished_orders(
    repo: Repository,
    strategies: dict[str, Strategy],
    real_only: bool = False,
) -> list[dt.Order]:
    """恢复未完成的订单（用于执行引擎重启）"""
    with repo.SessionLocal() as session:
        all_orders = repo.load_todays_orders(session)

    unfinished = []
    for order in all_orders:
        if order.order_status in (
            OrderStatus.ORDER_SUCCEEDED,
            OrderStatus.ORDER_CANCELED,
            OrderStatus.ORDER_JUNK,
            OrderStatus.ORDER_PART_CANCEL,
        ):
            continue

        # 从 order_id 提取基础策略ID
        base_id = _extract_strategy_base(order.order_id)
        strategy = strategies.get(base_id)
        if strategy is None:
            logger.warning(
                "恢复订单 %s 跳过：策略 %r 未找到（可能已删除），订单将被丢弃",
                order.order_id, base_id,
            )
            continue

        # 按 trade_mode 过滤
        if real_only and strategy.trade_mode != 1:
            continue
        if not real_only and strategy.trade_mode != 0:
            continue

        # 恢复订单到策略
        order.strategy_id = base_id
        strategy.orders[order.order_id] = order

        # 跨日后持仓已解冻（load_positions 将 frozen→available），
        # 但恢复的未完成卖单仍需重新冻结未成交部分，否则同一批股份可被重复卖出
        if order.order_type in (OrderType.STOCK_SELL, OrderType.CREDIT_SELL):
            unfilled = order.order_volume - order.traded_volume
            pos = strategy.positions.get(order.stock_code)
            if pos is not None and unfilled > 0 and pos.available >= unfilled:
                pos.available -= unfilled
                pos.frozen += unfilled

        unfinished.append(order)

    logger.info("恢复 %d 个未完成订单 (real_only=%s)", len(unfinished), real_only)
    return unfinished


def _extract_strategy_base(client_order_id: str) -> str:
    """从 strategy_id_seq 提取基础策略ID"""
    idx = client_order_id.rfind("_")
    if idx > 0:
        tail = client_order_id[idx + 1:]
        if tail.isdigit():
            return client_order_id[:idx]
    return client_order_id
