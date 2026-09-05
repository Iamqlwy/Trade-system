"""
量化交易系统 - 模拟撮合执行器

后台 asyncio task，每 10ms 轮询一次：
  1. 从队列获取新订单
  2. 用最新行情尝试撮合运行中订单
  3. 处理撤单请求
  4. 清理已完成订单

⚠️ 撮合逻辑约定：
  - 盘口 ask_volume/bid_volume 单位为「手」，需 ×100 转为「股」
  - 限价买单用 ask_price（卖方挂单），限价卖单用 bid_price（买方挂单），不可反过来
  - _execute_trade 先调用 strategy.trade() 校验（返回 False 则拒绝成交不记录），
    再追加到 trades_done，顺序不可颠倒

⚠️ 订单完成后结算：
  - _on_order_done 仅处理 ORDER_SUCCEEDED 和 ORDER_PART_CANCEL 两种终态
  - 部分成交后撤单（ORDER_PART_CANCEL）：已成交部分也需解冻价差和实际手续费
  - 手续费按实际成交比例 _calc_actual_commission 重算，非下单时预估值
  - 策略查找：优先使用 order.strategy_id，回退到 order_id.rsplit("_", 1)[0]（兼容旧数据）
"""
import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal

from .. import datatypes as dt
from ..constants import OrderType, OrderStatus, PriceType, SHARES_PER_LOT
from ..logutils.audit import log_trade_executed
from .utils import calc_ratio_commission, is_order_done

logger = logging.getLogger(__name__)


class SimExecutor:
    """模拟盘执行器 —— tick-based order matching"""

    def __init__(self, market_data, strategy_manager, commission_calculators):
        self.market = market_data
        self.strategies = strategy_manager
        self.commission_calculators = commission_calculators
        self._running = False
        self._task: asyncio.Task | None = None

        # 运行中订单
        self.orders_running: list[dt.Order] = []
        # 已完成订单
        self.orders_over: list[dt.Order] = []
        # 成交记录
        self.trades_done: list[dt.Trade] = []
        # 队列
        self._order_queue: asyncio.Queue[dt.Order] = asyncio.Queue()
        self._cancel_queue: asyncio.Queue[str] = asyncio.Queue()

        self._trade_id_counter = 1

    # ── 外部接口 ─────────────────────────────────

    async def enqueue_order(self, order: dt.Order) -> None:
        await self._order_queue.put(order)

    async def cancel_order(self, order_id: str) -> None:
        await self._cancel_queue.put(order_id)

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def restore_orders(self, orders: list[dt.Order]) -> None:
        """启动时恢复未完成订单"""
        for o in orders:
            o.order_status = OrderStatus.ORDER_REPORTED
            o.status_msg = "Order restored"
        self.orders_running.extend(orders)
        logger.info("SimExecutor: 恢复 %d 个未完成订单", len(orders))

    # ── 主循环 ─────────────────────────────────

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._process_cancels()
                await self._process_new_orders()
                self._process_running_orders()
                self._cleanup_completed()
            except Exception:
                logger.exception("SimExecutor loop error")
                # 检查是否有订单持续导致异常，标记为废单防止无限重试
                self._evict_stuck_orders()
            await asyncio.sleep(0.01)  # 10ms

    def _evict_stuck_orders(self) -> None:
        """将反复导致异常的订单标记为废单，避免主循环死循环"""
        stuck = []
        for order in self.orders_running:
            if is_order_done(order):
                continue
            tick = self.market.get_tick(order.stock_code)
            if tick is None:
                continue
            try:
                if order.price_type == PriceType.FIX_PRICE:
                    self._simulate_fix_price(order, tick)
                elif order.price_type == PriceType.LATEST_PRICE:
                    self._simulate_latest_price(order, tick)
            except Exception:
                stuck.append(order)
        for order in stuck:
            order.order_status = OrderStatus.ORDER_JUNK
            order.status_msg = "SimExecutor: 订单反复异常，自动标记为废单"
            logger.error("SimExecutor: 订单 %s 反复导致异常，已标记为废单", order.order_id)

    async def _process_cancels(self) -> None:
        while not self._cancel_queue.empty():
            order_id = await self._cancel_queue.get()
            self._cancel_order_by_id(order_id)

    async def _process_new_orders(self) -> None:
        while not self._order_queue.empty():
            order = await self._order_queue.get()
            order.order_status = OrderStatus.ORDER_REPORTED
            order.status_msg = "Order placed (sim)"
            self.orders_running.append(order)

    # ── 撮合逻辑 ─────────────────────────────────

    def _process_running_orders(self) -> None:
        for order in self.orders_running:
            if is_order_done(order):
                continue
            tick = self.market.get_tick(order.stock_code)
            if tick is None:
                continue
            if order.price_type == PriceType.FIX_PRICE:
                self._simulate_fix_price(order, tick)
            elif order.price_type == PriceType.LATEST_PRICE:
                self._simulate_latest_price(order, tick)

    def _simulate_fix_price(self, order: dt.Order, tick: dt.Tick) -> None:
        waiting = order.order_volume - order.traded_volume
        if waiting <= 0:
            return

        if order.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY):
            self._match_buy_fix(order, tick, waiting)
        else:
            self._match_sell_fix(order, tick, waiting)

    def _match_buy_fix(self, order: dt.Order, tick: dt.Tick, waiting: int) -> None:
        for i in range(5):
            if tick.ask_price[i] <= Decimal("0") or tick.ask_volume[i] == 0:
                continue
            if order.price < tick.ask_price[i]:
                return
            avail = tick.ask_volume[i] * SHARES_PER_LOT  # 手→股
            if avail <= 0:
                continue
            vol = min(waiting, avail)
            self._execute_trade(order, tick.ask_price[i], vol)
            waiting -= vol
            if waiting <= 0:
                return

    def _match_sell_fix(self, order: dt.Order, tick: dt.Tick, waiting: int) -> None:
        for i in range(5):
            if tick.bid_price[i] <= Decimal("0") or tick.bid_volume[i] == 0:
                continue
            if order.price > tick.bid_price[i]:
                return
            avail = tick.bid_volume[i] * SHARES_PER_LOT
            if avail <= 0:
                continue
            vol = min(waiting, avail)
            self._execute_trade(order, tick.bid_price[i], vol)
            waiting -= vol
            if waiting <= 0:
                return

    def _simulate_latest_price(self, order: dt.Order, tick: dt.Tick) -> None:
        waiting = order.order_volume - order.traded_volume
        if waiting <= 0:
            return
        is_buy = order.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY)
        if is_buy and (tick.ask_price[0] <= Decimal("0") or tick.ask_volume[0] == 0):
            return
        if not is_buy and (tick.bid_price[0] <= Decimal("0") or tick.bid_volume[0] == 0):
            return
        if tick.last_price > Decimal("0"):
            self._execute_trade(order, tick.last_price, waiting)

    def _execute_trade(self, order: dt.Order, price: Decimal, volume: int) -> None:
        trade = dt.Trade(
            traded_id=str(self._trade_id_counter),
            strategy_id=order.strategy_id,
            order_id=order.order_id,
            stock_code=order.stock_code,
            account_type=order.account_type,
            account_id=order.account_id,
            order_type=int(order.order_type),
            order_sysid=order.order_sysid,
            traded_price=price,
            traded_volume=volume,
            traded_amount=dt.round2(price * Decimal(volume)),
            traded_time=dt.datetime.now(),
            order_remark=order.order_remark,
        )
        self._trade_id_counter += 1

        # 更新策略状态
        strategy = self.strategies.get(order.strategy_id)
        if strategy is not None:
            if not strategy.trade(trade):
                logger.error("SIM trade rejected by strategy: %s %s %s股 @%s"
                            " — marking order as junk to prevent infinite retry",
                            order.stock_code, order.order_id, volume, price)
                order.order_status = OrderStatus.ORDER_JUNK
                order.status_msg = "Trade rejected by strategy (insufficient frozen_cash or position)"
                return
            strategy.add_trade(trade)

        self.trades_done.append(trade)

        # 更新订单
        self._update_order_on_trade(order, trade)

        logger.info("SIM 成交: %s %s %s股 @%s", order.stock_code,
                     "B" if order.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY) else "S",
                     volume, price)
        log_trade_executed(
            trade_id=trade.traded_id,
            order_id=order.order_id,
            strategy_id=order.strategy_id,
            stock_code=order.stock_code,
            order_type=OrderType(order.order_type).name,
            volume=volume,
            price=price,
            amount=trade.traded_amount,
            trade_mode="SIM",
        )

    @staticmethod
    def _update_order_on_trade(order: dt.Order, trade: dt.Trade) -> None:
        old_vol = order.traded_volume
        old_price = order.traded_price
        order.traded_volume += trade.traded_volume
        order.traded_amount = dt.round2(order.traded_amount + trade.traded_amount)

        if order.traded_volume >= order.order_volume:
            order.order_status = OrderStatus.ORDER_SUCCEEDED
        else:
            order.order_status = OrderStatus.ORDER_PART_SUCC

        if old_vol == 0:
            order.traded_price = trade.traded_price
        else:
            total_amt = old_price * Decimal(old_vol) + trade.traded_price * Decimal(trade.traded_volume)
            order.traded_price = dt.round2(total_amt / Decimal(order.traded_volume))

    # ── 撤单 ─────────────────────────────────────

    def _cancel_order_by_id(self, order_id: str) -> None:
        for order in self.orders_running:
            if order.order_id == order_id:
                if is_order_done(order):
                    return
                unfilled = order.order_volume - order.traded_volume
                unfilled_comm = calc_ratio_commission(order.commission, unfilled, order.order_volume)

                if order.traded_volume > 0:
                    order.order_status = OrderStatus.ORDER_PART_CANCEL
                else:
                    order.order_status = OrderStatus.ORDER_CANCELED
                order.status_msg = "Order canceled (sim)"

                # 更新策略
                strategy = self.strategies.get(order.strategy_id)
                if strategy is not None:
                    strategy.cancel_order(order, unfilled, unfilled_comm)
                    strategy.orders[order_id] = order

                logger.info("SIM 撤单: %s, 未成交=%d股", order_id, unfilled)
                return

    # ── 完成处理 ─────────────────────────────────

    def _cleanup_completed(self) -> None:
        remaining = []
        completed = []
        for order in self.orders_running:
            if is_order_done(order):
                completed.append(order)
            else:
                remaining.append(order)

        for order in completed:
            self._on_order_done(order)

        self.orders_running = remaining
        # 移到已完成列表（用于持久化）
        self.orders_over.extend(completed)

    def _on_order_done(self, order: dt.Order) -> None:
        """订单完成后：结算手续费、解冻多余资金"""
        strategy = self.strategies.get(order.strategy_id)
        if strategy is None:
            logger.error("SimExecutor: 订单 %s 的 strategy_id='%s' 在策略管理器中未找到",
                         order.order_id, order.strategy_id)
            return

        # 解冻因价格差多冻结的资金（仅完全成交）
        if order.order_status == OrderStatus.ORDER_SUCCEEDED:
            self._settle_completed_order(order, strategy)
        elif order.order_status == OrderStatus.ORDER_PART_CANCEL:
            # 部分成交后撤单：结算已成交部分的价差和手续费
            self._settle_partial_fill(order, strategy)

    def _settle_completed_order(self, order: dt.Order, strategy) -> None:
        if order.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY):
            actual_cost = dt.round2(Decimal(order.traded_volume) * order.traded_price)
            frozen_cost = dt.round2(Decimal(order.order_volume) * order.price)
            if frozen_cost > actual_cost:
                excess = dt.round2(frozen_cost - actual_cost)
                strategy.unfreeze_excess_cash(excess)
            self._deduct_buy_commission(order, strategy)
        else:
            self._deduct_sell_commission(order, strategy)

    def _settle_partial_fill(self, order: dt.Order, strategy) -> None:
        if order.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY):
            actual_cost = dt.round2(Decimal(order.traded_volume) * order.traded_price)
            actual_comm = self._calc_actual_commission(order)
            frozen_total = dt.round2(Decimal(order.order_volume) * order.price + order.commission)
            consumed = dt.round2(actual_cost + actual_comm)
            if frozen_total > consumed:
                excess = dt.round2(frozen_total - consumed)
                strategy.unfreeze_excess_cash(excess)
            if not strategy.deduct_frozen_cash(actual_comm):
                logger.error("PART_CANCEL: 扣除冻结手续费失败 order=%s comm=%s frozen=%s",
                           order.order_id, actual_comm, strategy.frozen_cash)
            strategy.spread_commission_to_cost(order.stock_code, actual_comm)
        else:
            actual_comm = self._calc_actual_commission(order)
            if not strategy.deduct_available_cash(actual_comm):
                logger.error("PART_CANCEL: 扣除卖出手续费失败 order=%s comm=%s available=%s",
                           order.order_id, actual_comm, strategy.available_cash)

    def _calc_actual_commission(self, order: dt.Order) -> Decimal:
        """按实际成交比例重新计算手续费"""
        return calc_ratio_commission(order.commission, order.traded_volume, order.order_volume)

    def _deduct_buy_commission(self, order: dt.Order, strategy) -> None:
        actual_comm = self._calc_actual_commission(order)
        if not strategy.deduct_frozen_cash(actual_comm):
            logger.error("买入手续费扣除失败 order=%s comm=%s frozen=%s",
                       order.order_id, actual_comm, strategy.frozen_cash)
        strategy.spread_commission_to_cost(order.stock_code, actual_comm)

    def _deduct_sell_commission(self, order: dt.Order, strategy) -> None:
        actual_comm = self._calc_actual_commission(order)
        if not strategy.deduct_available_cash(actual_comm):
            logger.error("卖出手续费扣除失败 order=%s comm=%s available=%s",
                       order.order_id, actual_comm, strategy.available_cash)

