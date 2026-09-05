# xtquant 数据字典笔记（委托 / 成交）

来源：<http://dict.thinktrader.net/>

## 委托 XtOrder

| 属性 | 类型 | 注释 |
|------|------|------|
| account_type | int | 账号类型，参见数据字典 |
| account_id | str | 资金账号 |
| stock_code | str | 证券代码，例如 "600000.SH" |
| order_id | int | 订单编号 |
| order_sysid | str | 柜台合同编号 |
| order_time | int | 报单时间 |
| order_type | int | 委托类型，参见数据字典 |
| order_volume | int | 委托数量 |
| price_type | int | 报价类型；返回值为柜台返回类型，与下单传入的 price_type 枚举值不同、功能一致 |
| price | float | 委托价格 |
| traded_volume | int | 成交数量 |
| traded_price | float | 成交均价 |
| order_status | int | 委托状态，参见数据字典 |
| status_msg | str | 委托状态描述，如废单原因 |
| strategy_name | str | 策略名称 |
| order_remark | str | 委托备注，最大 24 个英文字符 |
| direction | int | 多空方向，股票不适用 |
| offset_flag | int | 交易操作：区分股票买卖、期货开平仓、期权买卖等 |

## 成交 XtTrade

| 属性 | 类型 | 注释 |
|------|------|------|
| account_type | int | 账号类型，参见数据字典 |
| account_id | str | 资金账号 |
| stock_code | str | 证券代码 |
| order_type | int | 委托类型，参见数据字典 |
| traded_id | str | 成交编号 |
| traded_time | int | 成交时间 |
| traded_price | float | 成交均价 |
| traded_volume | int | 成交数量 |
