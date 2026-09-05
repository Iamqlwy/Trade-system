"""
量化交易系统 - 实盘执行器

管理 xtquant 订单的生命周期：
  - 接收下单/撤单请求，通过 xtquant SDK 发送给券商
  - 处理券商回调（订单状态变化、成交、错误）
  - 回调通过 asyncio.Queue 桥接到事件循环

⚠️ xtquant 接口约定：
  - xtquant 回调字段名与文档一致：order_id, order_status, status_msg,
    traded_id, traded_price, traded_volume, traded_amount, order_sysid
  - xtquant XtTrade 回调无 strategy_id 字段，需通过 orders_running[order_id] 反查策略上下文
  - 下单时传入的 order_remark 映射到 xtquant 的 order_remark（最大 24 英文）
  - 手续费使用预估值（order.commission），xtquant 回调不提供逐笔费用明细
"""
import asyncio
import logging
from decimal import Decimal

from .. import datatypes as dt
from ..constants import OrderType, OrderStatus
from ..logutils.audit import log_trade_executed
from .utils import calc_ratio_commission, is_order_done

logger = logging.getLogger(__name__)


class RealExecutor:
    """实盘执行器 —— xtquant broker bridge"""

    def __init__(self, strategy_manager):
        self.strategies = strategy_manager
        self._running = False
        self._task: asyncio.Task | None = None

        # 运行中订单: order_id → Order
        self.orders_running: dict[str, dt.Order] = {}
        # 已完成订单
        self.orders_over: list[dt.Order] = []
        # 成交
        self.trades_done: list[dt.Trade] = []

        # 回调队列（从 xtquant 线程传到 asyncio 事件循环）
        self._callback_queue: asyncio.Queue[dict] = asyncio.Queue()

        # xtquant 函数引用（由 main.py 注入）
        self._order_func = None    # async callable: order_stock_async(...)
        self._cancel_func = None   # async callable: cancel_order_stock_async(...)

    def set_trade_func(self, func) -> None:
        self._order_func = func

    def set_cancel_func(self, func) -> None:
        self._cancel_func = func

    async def enqueue_order(self, order: dt.Order) -> None:
        """异步下单到券商"""
        if self._order_func is None:
            logger.error("RealExecutor: order_func 未设置，订单 %s 被丢弃", order.order_id)
            # 退回冻结资金到策略
            strategy = self.strategies.get(order.strategy_id)
            if strategy is not None:
                unfilled = order.order_volume - order.traded_volume
                unfilled_comm = dt.round2(
                    order.commission * Decimal(unfilled) / Decimal(order.order_volume)
                ) if order.order_volume > 0 else Decimal("0")
                strategy.cancel_order(order, unfilled, unfilled_comm)
                if order.order_id in strategy.orders:
                    del strategy.orders[order.order_id]
            raise RuntimeError("实盘执行器未初始化，无法下单")
        try:
            await self._order_func(
                order.stock_code,
                "buy" if order.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY) else "sell",
                Decimal(str(order.price)),
                order.order_volume,
                order.order_id,
            )
            self.orders_running[order.order_id] = order
        except Exception:
            logger.exception("RealExecutor 下单失败: %s", order.order_id)
            # 先持久化订单，确保下次启动能通过 restore_unfinished_orders 恢复对账
            # 不可直接解冻资金——broker 可能已接受订单，需对账后处理
            try:
                from ..dependencies import repository
                from ..store import models
                sess = repository.SessionLocal()
                try:
                    sess.merge(models.Orders(
                        client_order_id=order.order_id,
                        strategy_id=order.strategy_id,
                        account_type=order.account_type,
                        account_id=order.account_id,
                        stock_code=order.stock_code,
                        broker_order_id=order.broker_order_id or "",
                        order_sysid=order.order_sysid or "",
                        order_time=order.created_at,
                        order_type=int(order.order_type),
                        price_type=int(order.price_type),
                        price=order.price,
                        order_volume=order.order_volume,
                        traded_volume=order.traded_volume,
                        traded_price=order.traded_price,
                        traded_amount=order.traded_amount,
                        commission=order.commission,
                        order_status=int(order.order_status),
                        status_msg=order.status_msg or "SDK下单异常，待对账",
                        order_remark=order.order_remark,
                    ))
                    sess.commit()
                    logger.warning("已持久化失败订单 %s，等待对账恢复", order.order_id)
                except Exception:
                    sess.rollback()
                    logger.exception("持久化失败订单 %s 也失败，资金可能永久冻结", order.order_id)
                finally:
                    sess.close()
            except Exception:
                logger.exception("获取DB连接失败，无法持久化订单 %s", order.order_id)

    async def cancel_order(self, order_id: str) -> None:
        if self._cancel_func is None:
            logger.warning("RealExecutor: cancel_func 未设置，撤单 %s 被忽略", order_id)
            return
        try:
            await self._cancel_func(order_id)
        except Exception:
            logger.exception("RealExecutor 撤单失败: %s", order_id)

    # ── xtquant 回调接口 ─────────────────────────

    def on_order_callback(self, data: dict) -> None:
        """由 BrokerBridge 线程调用，投递到事件循环"""
        try:
            self._callback_queue.put_nowait({"type": "order", "data": data})
        except asyncio.QueueFull:
            logger.warning("回调队列满，丢弃 order 回调")

    def on_trade_callback(self, data: dict) -> None:
        try:
            self._callback_queue.put_nowait({"type": "trade", "data": data})
        except asyncio.QueueFull:
            logger.warning("回调队列满，丢弃 trade 回调")

    def on_order_error_callback(self, data: dict) -> None:
        """下单失败回调 → 解冻资金并更新订单状态"""
        order_id = str(data.get("order_id", ""))
        if not order_id:
            return
        order = self.orders_running.get(order_id)
        if order is None:
            return
        order.order_status = OrderStatus.ORDER_JUNK
        order.status_msg = f"下单失败: {data.get('error_msg', '')} (code={data.get('error_id', 0)})"
        strategy = self.strategies.get(order.strategy_id)
        if strategy is not None:
            unfilled = order.order_volume - order.traded_volume
            unfilled_comm = dt.round2(
                order.commission * Decimal(unfilled) / Decimal(order.order_volume)
            ) if order.order_volume > 0 else Decimal("0")
            strategy.cancel_order(order, unfilled, unfilled_comm)
        self.orders_running.pop(order_id, None)
        self.orders_over.append(order)
        logger.warning("实盘下单失败 %s: %s", order_id, data.get("error_msg", "unknown"))

    def on_cancel_error_callback(self, data: dict) -> None:
        """撤单失败回调 —— 仅记录日志，不改变订单状态"""
        logger.warning(
            "实盘撤单失败 broker_id=%s: error_id=%s msg=%s",
            data.get("order_id", 0), data.get("error_id", 0), data.get("error_msg", ""),
        )

    def on_async_order_response(self, data: dict) -> None:
        """异步下单回报 —— 记录 seq → broker_order_id 映射（仅日志，不改变状态）"""
        logger.info(
            "实盘异步下单回报 seq=%d order=%s broker_id=%s",
            data.get("seq", 0), data.get("order_id", ""), data.get("broker_order_id", 0),
        )

    # ── 生命周期 ─────────────────────────────────

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._process_callbacks())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def restore_orders(self, orders: list[dt.Order]) -> None:
        """恢复今日未完成订单"""
        for o in orders:
            self.orders_running[o.order_id] = o
        logger.info("RealExecutor: 恢复 %d 个未完成订单", len(orders))

    # ── 回调处理循环 ─────────────────────────────

    async def _process_callbacks(self) -> None:
        while self._running:
            try:
                msg = await asyncio.wait_for(self._callback_queue.get(), timeout=1.0)
                if msg["type"] == "order":
                    self._handle_order_callback(msg["data"])
                elif msg["type"] == "trade":
                    self._handle_trade_callback(msg["data"])
            except asyncio.TimeoutError:
                continue
            except Exception:
                logger.exception("处理回调异常")

    def _handle_order_callback(self, data: dict) -> None:
        order_id = str(data.get("order_id", ""))
        order = self.orders_running.get(order_id)
        if order is None:
            return

        status = data.get("order_status", int(order.order_status))
        order.order_status = OrderStatus(status) if status else order.order_status
        order.status_msg = str(data.get("status_msg", ""))

        if self._is_done(order):
            strategy = self.strategies.get(order.strategy_id)
            if strategy is not None:
                strategy.orders[order_id] = order
                if order.order_status == OrderStatus.ORDER_SUCCEEDED:
                    # 解冻下单价与成交价之间的价差
                    actual_cost = dt.round2(Decimal(order.traded_volume) * order.traded_price)
                    frozen_cost = dt.round2(Decimal(order.order_volume) * order.price)
                    if frozen_cost > actual_cost:
                        strategy.unfreeze_excess_cash(dt.round2(frozen_cost - actual_cost))
                elif order.order_status == OrderStatus.ORDER_PART_CANCEL:
                    if order.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY):
                        # 解冻价差（不含手续费，手续费由公共逻辑统一处理）
                        actual_cost = dt.round2(Decimal(order.traded_volume) * order.traded_price)
                        frozen_cost = dt.round2(Decimal(order.order_volume) * order.price)
                        if frozen_cost > actual_cost:
                            strategy.unfreeze_excess_cash(dt.round2(frozen_cost - actual_cost))
                    else:
                        # 卖出撤单：解冻未卖出的持仓
                        unfilled = order.order_volume - order.traded_volume
                        pos = strategy.positions.get(order.stock_code)
                        if pos is not None and pos.frozen >= unfilled:
                            pos.frozen -= unfilled
                            pos.available += unfilled
                # 手续费统一处理（买入从 frozen 扣 + 摊入成本，卖出从 available 扣）
                actual_comm = self._calc_actual_commission(order)
                if order.order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY):
                    if not strategy.deduct_frozen_cash(actual_comm):
                        logger.error("实盘买入手续费扣除失败 order=%s comm=%s frozen=%s",
                                     order_id, actual_comm, strategy.frozen_cash)
                    strategy.spread_commission_to_cost(order.stock_code, actual_comm)
                else:
                    if not strategy.deduct_available_cash(actual_comm):
                        logger.error("实盘卖出手续费扣除失败 order=%s comm=%s", order_id, actual_comm)

            self.orders_running.pop(order_id, None)
            self.orders_over.append(order)

    def _handle_trade_callback(self, data: dict) -> None:
        order_id = str(data.get("order_id", ""))
        order = self.orders_running.get(order_id)
        if order is None:
            # 回调可能晚于状态回调——订单已移入 orders_over，仍需处理成交
            for o in self.orders_over:
                if o.order_id == order_id:
                    order = o
                    break
        if order is None:
            return

        traded_price = Decimal(str(data.get("traded_price", 0)))
        traded_volume = int(data.get("traded_volume", 0))
        traded_amount = dt.round2(traded_price * Decimal(traded_volume))
        traded_id = str(data.get("traded_id", ""))

        strategy = self.strategies.get(order.strategy_id)
        if strategy is None:
            return

        trade = dt.Trade(
            traded_id=traded_id,
            strategy_id=order.strategy_id,
            order_id=order_id,
            stock_code=order.stock_code,
            account_type=order.account_type,
            account_id=order.account_id,
            order_type=int(order.order_type),
            order_sysid=str(data.get("order_sysid", "")),
            traded_price=traded_price,
            traded_volume=traded_volume,
            traded_amount=traded_amount,
            traded_time=dt.datetime.now(),
            order_remark=order.order_remark,
        )

        if not strategy.trade(trade):
            logger.error("实盘成交被策略拒绝: %s %s %s股",
                        order.stock_code, order_id, traded_volume)
            return
        strategy.add_trade(trade)
        if not strategy.update_order(
            order_id, traded_volume, traded_price, traded_amount,
            order.order_status,
        ):
            logger.error("实盘成交后更新订单失败: %s 未在策略订单表中", order_id)
        self.trades_done.append(trade)
        logger.info("实盘成交: %s %s股 @%s", order.stock_code, traded_volume, traded_price)
        log_trade_executed(
            trade_id=trade.traded_id,
            order_id=order_id,
            strategy_id=order.strategy_id,
            stock_code=order.stock_code,
            order_type=OrderType(order.order_type).name,
            volume=traded_volume,
            price=traded_price,
            amount=traded_amount,
            trade_mode="REAL",
        )

    @staticmethod
    def _calc_actual_commission(order: dt.Order) -> Decimal:
        """按实际成交比例计算手续费"""
        return calc_ratio_commission(order.commission, order.traded_volume, order.order_volume)

    @staticmethod
    def _is_done(order: dt.Order) -> bool:
        return is_order_done(order)


# ── 实盘资金查询 ──────────────────────────────────

def query_real_account_cash(xtaccount: str, xttrader_path: str) -> tuple[bool, float, str]:
    """
    查询实盘账户可用资金。

    Returns:
        (success, available_cash, error_message)
        - success=True: 查询成功，available_cash 为可用金额
        - success=False: 查询失败，error_message 说明原因
    """
    try:
        from xtquant.xttype import StockAccount
        from xtquant.xttrader import XtQuantTrader
    except ImportError:
        return False, 0.0, "xtquant SDK 未安装，无法验证实盘资金"

    if not xtaccount:
        return False, 0.0, "券商资金账号未配置（xtaccount）"

    if not xttrader_path:
        return False, 0.0, "交易端路径未配置（xttrader_path）"

    xt_trader = None
    try:
        # 创建交易会话
        xt_trader = XtQuantTrader(xttrader_path, 123456)
        xt_trader.start()
        xt_trader.connect()

        account = StockAccount(xtaccount)
        asset = xt_trader.query_stock_asset(account)

        if asset is None:
            return False, 0.0, f"无法查询账户 {xtaccount} 的资金信息"

        available_cash = float(asset.cash) if asset.cash else 0.0
        logger.info(
            "实盘资金查询: account=%s, 可用=%.2f, 冻结=%.2f, 总资产=%.2f",
            xtaccount, asset.cash, asset.frozen_cash, asset.total_asset,
        )
        return True, available_cash, ""
    except Exception as e:
        logger.exception("查询实盘资金失败")
        return False, 0.0, f"查询实盘资金失败: {str(e)}"
    finally:
        if xt_trader is not None:
            try:
                xt_trader.stop()
            except Exception:
                pass
