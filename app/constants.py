"""
量化交易系统 - 枚举常量定义

⚠️ 枚举值对应 xtquant 协议，非自定义值，请勿修改：
  - OrderType: 23=买入, 24=卖出（xtquant 固定编码）
    信用交易与股票交易共用同一套委托类型（23/24），通过 StockAccount.account_type 区分
  - OrderStatus: 48-57 为 xtquant 委托状态码
  - PriceType: 5=最新价, 11=限价（xtquant 报价类型）
"""
from enum import IntEnum


class OrderType(IntEnum):
    """
    订单类型 (xtquant 协议)

    ⚠️ 信用交易（CREDIT_BUY/SELL）与股票交易（STOCK_BUY/SELL）在 xtquant 中
    共用相同的委托类型值（23/24），区别在于 StockAccount 的 account_type 参数。
    CREDIT_BUY / CREDIT_SELL 作为 STOCK_BUY / STOCK_SELL 的别名存在，
    业务代码中保留这两个名称用于语义区分，但它们的值与 STOCK_XXX 相同。
    """
    STOCK_BUY = 23
    STOCK_SELL = 24
    CREDIT_BUY = 23    # 别名 → STOCK_BUY，靠 account_type 区分信用/普通
    CREDIT_SELL = 24   # 别名 → STOCK_SELL

    @classmethod
    def _missing_(cls, value: object) -> "OrderType | None":
        """向后兼容：将旧版自定义值 27/28 映射到 xtquant 标准值 23/24"""
        if not isinstance(value, int):
            return None
        _legacy: dict[int, OrderType] = {27: cls.STOCK_BUY, 28: cls.STOCK_SELL}
        return _legacy.get(value)


class OrderStatus(IntEnum):
    """订单状态 (xtquant 协议)"""
    ORDER_UNREPORTED = 48        # 未报
    ORDER_WAIT_REPORTING = 49    # 待报
    ORDER_REPORTED = 50          # 已报
    ORDER_REPORTED_CANCEL = 51   # 已报待撤（xtquant 原始名称 ORDER_REPORTED_CANCEL）
    ORDER_PARTSUCC_CANCEL = 52   # 部撤待撤
    ORDER_PART_CANCEL = 53       # 部撤
    ORDER_CANCELED = 54          # 已撤
    ORDER_PART_SUCC = 55         # 部成
    ORDER_SUCCEEDED = 56         # 已成
    ORDER_JUNK = 57              # 废单


class PriceType(IntEnum):
    """报价类型 (xtquant 协议)"""
    LATEST_PRICE = 5        # 最新价
    FIX_PRICE = 11          # 限价


class RequestType(IntEnum):
    """内部请求类型"""
    TEST = 0
    ORDER_REQUEST = 1
    CANCEL_ORDER_REQUEST = 2
    SHUTDOWN = 3
    UPDATE_POSITION_REMARK = 4


class ResponseType(IntEnum):
    """内部响应类型"""
    TEST_RESPONSE = 0
    ORDER_RESPONSE = 1
    TRADE_RESPONSE = 2


# A 股每手股数（沪深主板 100 股/手）
SHARES_PER_LOT = 100
