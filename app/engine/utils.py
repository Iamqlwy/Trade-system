"""
执行器公共工具函数

被 sim_executor 和 real_executor 共享的工具方法。
"""
from decimal import Decimal

from .. import datatypes as dt
from ..constants import OrderStatus


def calc_ratio_commission(base_commission: Decimal, numerator: int, denominator: int) -> Decimal:
    """按比例分摊手续费：base_commission * numerator / denominator"""
    if denominator == 0:
        return Decimal("0")
    ratio = Decimal(numerator) / Decimal(denominator)
    return dt.round2(base_commission * ratio)


def is_order_done(order: dt.Order) -> bool:
    """订单是否已处于终态"""
    return order.order_status in (
        OrderStatus.ORDER_SUCCEEDED,       # 56 已成
        OrderStatus.ORDER_CANCELED,        # 54 已撤
        OrderStatus.ORDER_PART_CANCEL,     # 53 部撤
        OrderStatus.ORDER_PARTSUCC_CANCEL, # 52 部成待撤（撤单已发出，等待确认）
        OrderStatus.ORDER_JUNK,            # 57 废单
    )
