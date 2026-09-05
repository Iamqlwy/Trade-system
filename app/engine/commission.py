"""
量化交易系统 - 手续费计算器

A股标准费率（可通过数据库 commission_configs 表覆盖）：
  默认佣金率: 0.0003 (万三)
  最低佣金: 5.00 元
  印花税: 0.0005 (仅卖出)
  过户费: 0.00002 (万0.2)
"""
import logging
from decimal import Decimal
from typing import Optional

from .. import datatypes as dt

logger = logging.getLogger(__name__)

DEFAULT_COMMISSION_RATE = Decimal("0.0003")
DEFAULT_MIN_COMMISSION = Decimal("5.00")
DEFAULT_STAMP_TAX_RATE = Decimal("0.0005")
DEFAULT_TRANSFER_FEE_RATE = Decimal("0.00002")


class CommissionCalculator:
    def __init__(
        self,
        commission_rate: Decimal = DEFAULT_COMMISSION_RATE,
        stamp_tax_rate: Decimal = DEFAULT_STAMP_TAX_RATE,
        transfer_fee_rate: Decimal = DEFAULT_TRANSFER_FEE_RATE,
        min_commission: Decimal = DEFAULT_MIN_COMMISSION,
    ):
        self.commission_rate = commission_rate
        self.stamp_tax_rate = stamp_tax_rate
        self.transfer_fee_rate = transfer_fee_rate
        self.min_commission = min_commission

    def buy_commission(self, amount: Decimal) -> Decimal:
        """买入总费用 = 佣金(≥最低) + 过户费"""
        commission = amount * self.commission_rate
        transfer_fee = amount * self.transfer_fee_rate
        commission = max(commission, self.min_commission)
        return dt.round2(commission + transfer_fee)

    def sell_commission(self, amount: Decimal) -> Decimal:
        """卖出总费用 = 佣金(≥最低) + 印花税 + 过户费"""
        commission = amount * self.commission_rate
        stamp_tax = amount * self.stamp_tax_rate
        transfer_fee = amount * self.transfer_fee_rate
        commission = max(commission, self.min_commission)
        return dt.round2(commission + stamp_tax + transfer_fee)

    def calculate(self, amount: Decimal, is_buy: bool) -> Decimal:
        return self.buy_commission(amount) if is_buy else self.sell_commission(amount)

    def buy_commission_only(self, amount: Decimal) -> Decimal:
        """仅佣金部分（不含过户费）"""
        return max(dt.round2(amount * self.commission_rate), self.min_commission)

    def sell_commission_only(self, amount: Decimal) -> Decimal:
        """仅佣金部分（卖出，不含印花税和过户费）"""
        return max(dt.round2(amount * self.commission_rate), self.min_commission)


# 全局注册表: strategy_id → CommissionCalculator
_calculators: dict[str, CommissionCalculator] = {}


def get_calculator(strategy_id: str) -> CommissionCalculator:
    return _calculators.get(strategy_id, CommissionCalculator())


def set_calculator(strategy_id: str, cfg: dict) -> None:
    _calculators[strategy_id] = CommissionCalculator(
        commission_rate=Decimal(str(cfg.get("commission_rate", DEFAULT_COMMISSION_RATE))),
        stamp_tax_rate=Decimal(str(cfg.get("stamp_tax_rate", DEFAULT_STAMP_TAX_RATE))),
        transfer_fee_rate=Decimal(str(cfg.get("transfer_fee_rate", DEFAULT_TRANSFER_FEE_RATE))),
        min_commission=Decimal(str(cfg.get("min_commission", DEFAULT_MIN_COMMISSION))),
    )
