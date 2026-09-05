"""
量化交易系统 - 策略状态管理

每个 Strategy 是一个独立的虚拟账户，包含：
  - 资金池（可用/冻结/初始）
  - 持仓（按股票代码索引）
  - FIFO 批次（按股票代码索引，用于成本核算和除权除息）
  - 委托订单（按 order_id 索引）
  - 成交记录（按时间序）
  - 结算盈亏（按股票代码索引，按持仓周期区分）

⚠️ 下单/成交/撤单资金流：
  - 下单时：available_cash → frozen_cash（全额冻结：成交量×价格 + 预估手续费）
  - 成交时：frozen_cash → 扣除实际成本（买入）或 available_cash ← 收入（卖出）
  - 撤单时：frozen_cash → available_cash（仅解冻未成交部分）
  - 订单完成后：解冻「下单冻结 - 实际成交」的价差，手续费按实际比例扣除

⚠️ 除权除息（apply_dividend）：
  - 送股/转增股直接加到 total/available 等字段，等比例分配
  - 现金红利扣除红利税后直接加 available_cash
  - 除权后 avg_price 会被调低（扣减现金红利），Settlement.on_sell 使用独立的
    avg_cost_price（不受除权影响）计算清仓盈亏，避免收益重复计算
  - 配股（allotment）：不保证足额缴款，资金不足时实际缴款数 floor 处理
"""
import logging
import heapq
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from .. import datatypes as dt
from ..constants import OrderType, OrderStatus

logger = logging.getLogger(__name__)


def _is_same_day(d1: datetime, d2: datetime) -> bool:
    return d1.date() == d2.date()


def _tax_rate_from_days(days: int) -> Decimal:
    """股息红利税：持股1月内20%，1年内10%，1年以上0%"""
    if days <= 30:
        return Decimal("0.20")
    if days <= 365:
        return Decimal("0.10")
    return Decimal("0.00")


class Strategy:
    """策略级虚拟账户"""

    def __init__(
        self,
        strategy_id: str = "test",
        name: str = "",
        description: str = "",
        detail: str = "",
        trade_mode: int = 0,
        initial_cash: Decimal = Decimal("1000000"),
        available_cash: Decimal = Decimal("1000000"),
        frozen_cash: Decimal = Decimal("0"),
    ):
        self.strategy_id = strategy_id
        self.name = name
        self.description = description
        self.detail = detail
        self.trade_mode = trade_mode   # 0=模拟, 1=实盘
        self.initial_cash = initial_cash
        self.available_cash = available_cash
        self.frozen_cash = frozen_cash

        # stock_code → Position
        self.positions: dict[str, dt.Position] = {}
        # stock_code → list[Lot] (managed as heap for FIFO)
        self._lots: dict[str, list[dt.Lot]] = defaultdict(list)
        # order_id → Order
        self.orders: dict[str, dt.Order] = {}
        # list[Trade]
        self.trades: list[dt.Trade] = []
        # stock_code → Settlement
        self.settlements: dict[str, dt.Settlement] = {}
        # 序号计数器（用于生成 order_id = strategy_id_seq）
        self._seq_counter: int = 0

    # ── 资金查询 ─────────────────────────────────

    @property
    def total_cash(self) -> Decimal:
        return self.available_cash + self.frozen_cash

    @property
    def total_assets(self) -> Decimal:
        """当前总资产 = 现金 + 持仓市值（成本价）"""
        pos_val = sum(
            Decimal(p.total) * p.avg_price
            for p in self.positions.values()
            if p.total > 0
        )
        return self.available_cash + self.frozen_cash + pos_val

    def next_seq(self) -> int:
        self._seq_counter += 1
        return self._seq_counter

    def get_order_id(self) -> str:
        return f"{self.strategy_id}_{self.next_seq()}"

    # ── 下单冻结 ─────────────────────────────────

    def order_stock_by_order(self, order: dt.Order) -> bool:
        """根据 Order 对象冻结资金/持仓"""
        ok = False
        if order.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY):
            ok = self._order_buy(order.stock_code, order.order_volume, order.price, order.commission)
        elif order.order_type in (OrderType.STOCK_SELL, OrderType.CREDIT_SELL):
            ok = self._order_sell(order.stock_code, order.order_volume)
        if ok:
            self.orders[order.order_id] = order
        return ok

    def _order_buy(self, stock_code: str, volume: int, price: Decimal, commission: Decimal) -> bool:
        cost = dt.round2(Decimal(volume) * price)
        total = dt.round2(cost + commission)
        if self.available_cash < total:
            return False
        self.available_cash = dt.round2(self.available_cash - total)
        self.frozen_cash = dt.round2(self.frozen_cash + total)
        return True

    def _order_sell(self, stock_code: str, volume: int) -> bool:
        pos = self.positions.get(stock_code)
        if pos is None or pos.available < volume:
            return False
        pos.available -= volume
        pos.frozen += volume
        return True

    # ── 成交处理 ─────────────────────────────────

    def trade(self, trade: dt.Trade) -> bool:
        """处理一笔成交，更新持仓和资金"""
        if trade.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY):  # BUY
            return self._trade_buy(
                trade.stock_code, trade.traded_volume,
                trade.traded_price, trade.traded_time,
                trade.order_remark,
            )
        elif trade.order_type in (OrderType.STOCK_SELL, OrderType.CREDIT_SELL):  # SELL
            return self._trade_sell(
                trade.stock_code, trade.traded_volume,
                trade.traded_price, trade.traded_time,
            )
        return False

    def _trade_buy(self, stock_code: str, volume: int, price: Decimal,
                   trade_time: datetime, remark: str) -> bool:
        cost = dt.round2(Decimal(volume) * price)
        if self.frozen_cash < cost:
            return False
        self.frozen_cash = dt.round2(self.frozen_cash - cost)

        pos = self.positions.get(stock_code)
        if pos is None:
            pos = dt.Position(stock_code=stock_code)
            self.positions[stock_code] = pos

        old_total = pos.total
        if old_total == 0 and remark:
            pos.remark = remark
        pos.total += volume
        pos.unavailable += volume

        if pos.total > 0:
            weighted = pos.avg_price * Decimal(old_total) + price * Decimal(volume)
            pos.avg_price = dt.round2(weighted / Decimal(pos.total))

        # FIFO 批次
        lot = dt.Lot(self.strategy_id, stock_code, volume, trade_time, price)
        heapq.heappush(self._lots[stock_code], lot)

        # 结算记录
        settle = self.settlements.get(stock_code)
        if settle is not None:
            if settle.is_closed:
                if _is_same_day(settle.close_time or datetime.min, trade_time):
                    settle.is_closed = False
                    settle.close_time = None
                    settle.on_buy(volume, price)
                else:
                    self.settlements[stock_code] = dt.Settlement(
                        self.strategy_id, stock_code, first_buy_time=trade_time,
                    )
                    self.settlements[stock_code].on_buy(volume, price)
            else:
                settle.on_buy(volume, price)
        else:
            self.settlements[stock_code] = dt.Settlement(
                self.strategy_id, stock_code, first_buy_time=trade_time,
            )
            self.settlements[stock_code].on_buy(volume, price)

        return True

    def _trade_sell(self, stock_code: str, volume: int, price: Decimal,
                    sell_time: datetime) -> bool:
        pos = self.positions.get(stock_code)
        if pos is None or pos.frozen < volume or pos.total < volume:
            return False

        pos.frozen -= volume
        pos.total -= volume
        pos.unavailable = max(0, pos.unavailable - volume)
        if pos.total == 0:
            pos.avg_price = Decimal("0")

        revenue = dt.round2(Decimal(volume) * price)
        self.available_cash = dt.round2(self.available_cash + revenue)

        # FIFO 消耗
        remaining = volume
        lot_heap = self._lots.get(stock_code)
        while remaining > 0 and lot_heap:
            top = heapq.heappop(lot_heap)
            if top.lot_size <= remaining:
                remaining -= top.lot_size
            else:
                top.lot_size -= remaining
                heapq.heappush(lot_heap, top)
                remaining = 0

        # 结算
        settle = self.settlements.get(stock_code)
        if settle is not None and not settle.is_closed:
            settle.on_sell(volume, price, sell_time)

        return True

    # ── 撤单 ─────────────────────────────────────

    def cancel_order(self, order: dt.Order, unfilled_volume: int,
                     unfilled_commission: Decimal) -> bool:
        """撤单：解冻未成交部分的资金/持仓"""
        if order.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY):
            unfrozen = dt.round2(Decimal(unfilled_volume) * order.price)
            total = dt.round2(unfrozen + unfilled_commission)
            if self.frozen_cash < total:
                return False
            self.frozen_cash = dt.round2(self.frozen_cash - total)
            self.available_cash = dt.round2(self.available_cash + total)
        elif order.order_type in (OrderType.STOCK_SELL, OrderType.CREDIT_SELL):
            pos = self.positions.get(order.stock_code)
            if pos is None or pos.frozen < unfilled_volume:
                return False
            pos.frozen -= unfilled_volume
            pos.available += unfilled_volume
        return True

    def unfreeze_excess_cash(self, amount: Decimal) -> bool:
        """解冻过度冻结的资金（下单价 vs 实际成交价差异）"""
        amount = dt.round2(amount)
        if self.frozen_cash < amount:
            return False
        self.frozen_cash = dt.round2(self.frozen_cash - amount)
        self.available_cash = dt.round2(self.available_cash + amount)
        return True

    def deduct_frozen_cash(self, amount: Decimal) -> bool:
        """从冻结资金中直接扣除（用于买入手续费结算）"""
        amount = dt.round2(amount)
        if self.frozen_cash < amount:
            return False
        self.frozen_cash = dt.round2(self.frozen_cash - amount)
        return True

    def deduct_available_cash(self, amount: Decimal) -> bool:
        """从可用资金中扣除（用于卖出手续费结算）"""
        amount = dt.round2(amount)
        if self.available_cash < amount:
            return False
        self.available_cash = dt.round2(self.available_cash - amount)
        return True

    def spread_commission_to_cost(self, stock_code: str, commission: Decimal) -> bool:
        """将买入手续费摊入持仓成本"""
        pos = self.positions.get(stock_code)
        if pos is None:
            return False
        if pos.total == 0:
            return True
        total_cost = dt.round2(pos.avg_price * Decimal(pos.total) + commission)
        pos.avg_price = dt.round2(total_cost / Decimal(pos.total))
        return True

    # ── 订单/成交管理 ─────────────────────────────

    def get_order(self, order_id: str) -> Optional[dt.Order]:
        return self.orders.get(order_id)

    def update_order(self, order_id: str, traded_volume: int,
                     traded_price: Decimal, traded_amount: Decimal,
                     status: OrderStatus) -> bool:
        order = self.orders.get(order_id)
        if order is None:
            return False
        old_vol = order.traded_volume
        old_price = order.traded_price

        order.traded_volume += traded_volume
        order.traded_amount = dt.round2(order.traded_amount + traded_amount)
        order.order_status = status

        if old_vol == 0:
            order.traded_price = dt.round2(traded_price)
        else:
            total_amt = old_price * Decimal(old_vol) + traded_price * Decimal(traded_volume)
            order.traded_price = dt.round2(total_amt / Decimal(order.traded_volume))
        return True

    def add_trade(self, trade: dt.Trade) -> None:
        self.trades.append(trade)

    def add_lot(self, stock_code: str, lot_size: int, open_time: datetime,
                open_price: Decimal) -> None:
        lot = dt.Lot(self.strategy_id, stock_code, lot_size, open_time, open_price)
        heapq.heappush(self._lots[stock_code], lot)

    def get_lots(self) -> dict:
        return dict(self._lots)

    def set_settlement(self, stock_code: str, settlement: dt.Settlement) -> None:
        self.settlements[stock_code] = settlement

    def get_settlement(self, stock_code: str) -> Optional[dt.Settlement]:
        return self.settlements.get(stock_code)

    def update_position_remark(self, stock_code: str, remark: str) -> bool:
        pos = self.positions.get(stock_code)
        if pos is None:
            return False
        pos.remark = remark
        return True

    # ── 除权除息 ─────────────────────────────────

    def apply_dividend(self, dividend: dt.Dividend, callback_time: Optional[datetime] = None) -> None:
        pos = self.positions.get(dividend.stock_code)
        if pos is None or pos.total == 0:
            return

        per10_cash = dividend.interest
        per10_bonus = dividend.Stockonus + dividend.stockGift
        per10_allot = dividend.allotNum

        if per10_cash == Decimal("0") and per10_bonus == Decimal("0") and per10_allot == Decimal("0"):
            return

        old_total = pos.total
        bonus_ratio = per10_bonus / Decimal("10")
        bonus_total = int(Decimal(old_total) * bonus_ratio)

        bonus_available = int(Decimal(pos.available) * bonus_ratio)
        bonus_frozen = int(Decimal(pos.frozen) * bonus_ratio)
        bonus_unavailable = int(Decimal(pos.unavailable) * bonus_ratio)
        bonus_sum = bonus_available + bonus_frozen + bonus_unavailable
        bonus_rem = bonus_total - bonus_sum if bonus_total > bonus_sum else 0

        pos.available += bonus_available + bonus_rem
        pos.frozen += bonus_frozen
        pos.unavailable += bonus_unavailable
        pos.total += bonus_total

        if callback_time is None:
            callback_time = datetime.now()
        dividend_time = callback_time

        cash_gross = dt.round2((per10_cash / Decimal("10")) * Decimal(old_total))
        cash_tax = Decimal("0")

        lot_heap = self._lots.get(dividend.stock_code)
        if lot_heap:
            temp_lots: list[dt.Lot] = []
            lot_bonus_sum = 0
            while lot_heap:
                lot = heapq.heappop(lot_heap)
                if cash_gross > Decimal("0") and per10_cash > Decimal("0"):
                    lot_cash = (per10_cash / Decimal("10")) * Decimal(lot.lot_size)
                    days = (dividend_time - lot.open_time).days
                    if days < 0:
                        days = 0
                    rate = _tax_rate_from_days(days)
                    cash_tax = dt.round2(cash_tax + dt.round2(lot_cash * rate))
                if bonus_ratio > Decimal("0"):
                    lb = int(Decimal(lot.lot_size) * bonus_ratio)
                    lot.lot_size += lb
                    lot_bonus_sum += lb
                temp_lots.append(lot)
            if bonus_ratio > Decimal("0") and bonus_total > lot_bonus_sum and temp_lots:
                temp_lots[0].lot_size += (bonus_total - lot_bonus_sum)
            for lot in temp_lots:
                heapq.heappush(lot_heap, lot)
        elif cash_gross > Decimal("0"):
            cash_tax = dt.round2(cash_gross * Decimal("0.20"))

        cash_net = dt.round2(cash_gross - cash_tax)
        if cash_net > Decimal("0"):
            self.available_cash = dt.round2(self.available_cash + cash_net)

        actual_allot_cost = Decimal("0")
        actual_allot_shares = 0
        if per10_allot > Decimal("0") and dividend.allotPrice > Decimal("0"):
            allot_ratio = per10_allot / Decimal("10")
            desired = int(Decimal(old_total) * allot_ratio)
            if desired > 0:
                desired_cost = dt.round2(Decimal(desired) * dividend.allotPrice)
                actual_allot_shares = desired
                if desired_cost > self.available_cash:
                    actual_allot_shares = int(self.available_cash / dividend.allotPrice)
                if actual_allot_shares > 0:
                    actual_allot_cost = dt.round2(Decimal(actual_allot_shares) * dividend.allotPrice)
                    self.available_cash = dt.round2(self.available_cash - actual_allot_cost)
                    pos.total += actual_allot_shares
                    pos.unavailable += actual_allot_shares

        cost_basis = dt.round2(pos.avg_price * Decimal(old_total))
        new_basis = dt.round2(cost_basis - cash_net + actual_allot_cost)
        if new_basis < Decimal("0"):
            new_basis = Decimal("0")
        pos.avg_price = dt.round2(new_basis / Decimal(pos.total)) if pos.total > 0 else Decimal("0")

        if actual_allot_shares > 0:
            heapq.heappush(
                self._lots[dividend.stock_code],
                dt.Lot(self.strategy_id, dividend.stock_code, actual_allot_shares,
                       dividend_time, dividend.allotPrice),
            )
