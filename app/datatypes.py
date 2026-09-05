"""
量化交易系统 - 基础数据类型

使用 Decimal 处理所有金额，round2 四舍五入到分（2位小数）。
使用 datetime 处理时间。

⚠️ Trade.strategy_id 和 Trade.order_id 语义：
  - strategy_id: 基础策略ID（如 "test"），非 client_order_id
  - order_id: client_order_id（如 "test_5"），用于回链到 Order
  - sim_executor 和 real_executor 都按此约定赋值，_save_trades_batch 据此拆分入库

⚠️ Settlement.on_sell 使用 self.avg_cost_price（结算均价）计算成本基础，
  而非 position.avg_price（持仓均价）。后者会被 apply_dividend 调低（除权），
  若用持仓均价计算会导致已实现收益重复计算分红金额。
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Optional

from .constants import OrderType, OrderStatus, PriceType


def round2(value: Decimal) -> Decimal:
    """四舍五入到两位小数（精确到分）"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class Tick:
    """实时行情快照"""
    stock_code: str = ""
    last_price: Decimal = Decimal("0")
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    volume: int = 0
    ask_price: list[Decimal] = field(default_factory=lambda: [Decimal("0")] * 5)
    bid_price: list[Decimal] = field(default_factory=lambda: [Decimal("0")] * 5)
    ask_volume: list[int] = field(default_factory=lambda: [0] * 5)
    bid_volume: list[int] = field(default_factory=lambda: [0] * 5)
    timestamp: int = 0


@dataclass
class Lot:
    """FIFO 批次 —— 用于成本基础和除权除息计算"""
    strategy_id: str
    stock_code: str
    lot_size: int
    open_time: datetime
    open_price: Decimal

    def __lt__(self, other: "Lot") -> bool:
        """FIFO: 先进先出，按 open_time 排序（更早的在前）"""
        return self.open_time < other.open_time


@dataclass
class Position:
    """单只股票的持仓"""
    stock_code: str = ""
    total: int = 0          # 总持仓股数
    available: int = 0      # 可卖股数
    frozen: int = 0         # 冻结股数（挂单卖出）
    unavailable: int = 0    # 不可用股数（T+1 等）
    avg_price: Decimal = Decimal("0")  # 持仓均价
    remark: str = ""


@dataclass
class Order:
    """订单"""
    order_id: str = ""              # strategy_id_seq
    strategy_id: str = ""
    stock_code: str = ""
    account_type: int = 0
    account_id: str = ""
    order_type: OrderType = OrderType.STOCK_BUY
    price_type: PriceType = PriceType.FIX_PRICE
    price: Decimal = Decimal("0")
    order_volume: int = 0
    traded_volume: int = 0
    traded_price: Decimal = Decimal("0")      # 加权成交均价
    traded_amount: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    order_status: OrderStatus = OrderStatus.ORDER_UNREPORTED
    status_msg: str = ""
    order_sysid: str = ""           # 券商系统订单ID
    broker_order_id: str = ""       # 券商订单号
    order_remark: str = ""          # 订单备注（写入 Trade）
    seq: int = 0                    # 策略内自增序号
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Trade:
    """成交记录"""
    traded_id: str = ""
    strategy_id: str = ""           # 基础策略ID（如 "test"）
    order_id: str = ""              # client_order_id（如 "test_5"，用于回链 Order）
    stock_code: str = ""
    account_type: int = 0
    account_id: str = ""
    order_type: int = 23            # 23=buy, 24=sell
    order_sysid: str = ""
    traded_price: Decimal = Decimal("0")
    traded_volume: int = 0
    traded_amount: Decimal = Decimal("0")
    traded_time: datetime = field(default_factory=datetime.now)
    order_remark: str = ""
    seq: int = 0


@dataclass
class Settlement:
    """单只股票一个持仓周期的结算收益"""
    strategy_id: str = ""
    stock_code: str = ""
    first_buy_time: datetime = field(default_factory=datetime.now)
    total_buy_volume: int = 0
    total_buy_amount: Decimal = Decimal("0")
    total_sell_volume: int = 0
    total_sell_amount: Decimal = Decimal("0")
    avg_cost_price: Decimal = Decimal("0")
    realized_profit: Decimal = Decimal("0")
    is_closed: bool = False
    close_time: Optional[datetime] = None

    def on_buy(self, volume: int, price: Decimal) -> None:
        """记录买入"""
        amount = round2(Decimal(volume) * price)
        self.total_buy_volume += volume
        self.total_buy_amount = round2(self.total_buy_amount + amount)
        if self.total_buy_volume > 0:
            self.avg_cost_price = round2(self.total_buy_amount / Decimal(self.total_buy_volume))

    def on_sell(self, volume: int, price: Decimal, sell_time: datetime) -> None:
        """
        记录卖出。使用结算均价（avg_cost_price）计算成本基础，
        该值不受除权除息调整影响，避免与 apply_dividend 的 cash credit 重复计算。
        """
        amount = round2(Decimal(volume) * price)
        self.total_sell_volume += volume
        self.total_sell_amount = round2(self.total_sell_amount + amount)

        buy_cost = round2(self.avg_cost_price * Decimal(volume))
        self.realized_profit = round2(self.realized_profit + amount - buy_cost)

        if self.total_buy_volume <= self.total_sell_volume:
            self.is_closed = True
            self.close_time = sell_time

    def profit_rate(self) -> Decimal:
        """已清仓的收益率"""
        if self.total_buy_amount == Decimal("0"):
            return Decimal("0")
        return round2(self.realized_profit / self.total_buy_amount)


@dataclass
class Dividend:
    """除权除息信息"""
    stock_code: str = ""
    time: int = 0               # 除权日期 (YYYYMMDD)
    interest: Decimal = Decimal("0")    # 每股现金红利
    Stockonus: Decimal = Decimal("0")   # 每股送股
    stockGift: Decimal = Decimal("0")   # 每股转增
    allotNum: Decimal = Decimal("0")    # 每股配股
    allotPrice: Decimal = Decimal("0")  # 配股价
