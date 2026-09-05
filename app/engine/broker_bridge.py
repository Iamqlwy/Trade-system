"""
量化交易系统 - xtquant 交易桥接

连接 RealExecutor 与 xtquant SDK：
  - 管理 XtQuantTrader 生命周期（start / connect / subscribe / stop）
  - 注册 XtQuantTraderCallback，将 xtquant 回调转为 dict 投递到 RealExecutor
  - 提供 async wrapper 给 RealExecutor 调用（order / cancel）
  - 维护 seq → internal_order_id 映射，处理异步下单回报

⚠️ xtquant 关键约定（来自官方文档 + SDK 源码实测）：
  - order_stock_async 返回 seq（请求序号），真正 order_id 通过 on_order_stock_async_response 回调
  - XtOrder.strategy_name 可用来回传内部 order_id（用于映射）
  - XtOrder.order_remark 同样会回传，但最大长度 24 字节
  - xtquant 回调在 C++ 线程中执行，不可阻塞，必须快速返回
  - CREDIT_BUY/SELL 与 STOCK_BUY/SELL 同值，靠 StockAccount.account_type 区分
"""
import asyncio
import logging
import threading
from decimal import Decimal

from ..config import settings

logger = logging.getLogger(__name__)


class BrokerBridge:
    """xtquant 交易桥接 —— 封装 XtQuantTrader 与 RealExecutor 的对接"""

    def __init__(self, real_executor):
        self.real_executor = real_executor

        # xtquant 对象（运行时初始化）
        self._xt_trader = None       # XtQuantTrader 实例
        self._account = None         # StockAccount 实例
        self._callback = None        # BrokerCallback 实例

        # 连接状态
        self._connected = False
        self._lock = threading.Lock()

        # seq → internal_order_id 映射（异步下单追踪）
        # xtquant 线程写入/读取，asyncio 线程写入，通过 GIL 保护
        self._seq_to_order_id: dict[int, str] = {}
        # broker_order_id (xtquant order_id) → internal_order_id 反向映射
        self._broker_to_internal: dict[int, str] = {}

    # ── 生命周期 ──────────────────────────────────

    def start(self) -> bool:
        """
        初始化 xtquant 交易通道。

        Returns:
            True 表示初始化成功并已连接，False 表示失败（SDK 未装/配置缺失/连接失败）
        """
        if not settings.xtaccount or not settings.xttrader_path:
            logger.warning(
                "BrokerBridge: xtaccount 或 xttrader_path 未配置，跳过实盘初始化"
            )
            return False

        try:
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount
        except ImportError:
            logger.warning("BrokerBridge: xtquant SDK 未安装，实盘功能不可用")
            return False

        try:
            # 使用 settings 中的配置
            session_id = abs(hash(settings.xtaccount)) % 10_000_000  # 由账号派生，保证稳定
            self._xt_trader = XtQuantTrader(settings.xttrader_path, session_id)

            # 注册回调
            self._callback = self._create_callback_class()
            self._xt_trader.register_callback(self._callback())

            # 启动并连接
            self._xt_trader.start()
            connect_result = self._xt_trader.connect()
            if connect_result != 0:
                logger.error(
                    "BrokerBridge: 连接 MiniQMT 失败，返回码=%s，path=%s",
                    connect_result, settings.xttrader_path,
                )
                return False

            # 创建账号对象并订阅
            self._account = StockAccount(settings.xtaccount)
            sub_result = self._xt_trader.subscribe(self._account)
            if sub_result != 0:
                logger.error(
                    "BrokerBridge: 订阅账号 %s 失败，返回码=%s",
                    settings.xtaccount, sub_result,
                )
                return False

            self._connected = True

            # 注入 async wrapper 到 RealExecutor
            self.real_executor.set_trade_func(self._async_order)
            self.real_executor.set_cancel_func(self._async_cancel)

            logger.info(
                "BrokerBridge: 实盘交易通道已建立 account=%s, session=%d, path=%s",
                settings.xtaccount, session_id, settings.xttrader_path,
            )
            return True

        except Exception:
            logger.exception("BrokerBridge: 初始化异常")
            return False

    def stop(self) -> None:
        """停止交易通道"""
        self._connected = False
        if self._xt_trader is not None:
            try:
                self._xt_trader.stop()
                logger.info("BrokerBridge: 交易通道已停止")
            except Exception:
                logger.exception("BrokerBridge: 停止异常")
            self._xt_trader = None

    @property
    def connected(self) -> bool:
        return self._connected

    # ── 下单/撤单 async wrapper ──────────────────────

    async def _async_order(
        self,
        stock_code: str,
        direction: str,
        price: Decimal,
        volume: int,
        order_id: str,
    ) -> int:
        """
        异步下单（由 RealExecutor.enqueue_order 调用）。

        Args:
            stock_code: 证券代码，如 "600000.SH"
            direction: "buy" 或 "sell"
            price: 委托价格
            volume: 委托数量（股）
            order_id: 内部订单号（strategy_id_seq 格式）

        Returns:
            seq（请求序号），>0 表示请求已发出，-1 表示失败
        """
        if not self._connected or self._xt_trader is None:
            raise RuntimeError("BrokerBridge 未连接")

        from xtquant import xtconstant

        # 映射方向到 xtquant 委托类型
        if direction == "buy":
            order_type = xtconstant.STOCK_BUY
        else:
            order_type = xtconstant.STOCK_SELL

        # 使用 strategy_name 传递内部 order_id（用于回调映射）
        # strategy_name 字段长度足够（通常 32+ 字符），且会原样回传到 XtOrder
        strategy_name = order_id
        # order_remark 最大 24 字节，截断使用
        order_remark = order_id[:24]

        try:
            # xtquant API 是同步阻塞的，丢到线程池执行
            seq = await asyncio.to_thread(
                self._xt_trader.order_stock_async,
                self._account,
                stock_code,
                order_type,
                volume,
                11,  # xtconstant.FIX_PRICE
                float(price),
                strategy_name,
                order_remark,
            )
        except Exception:
            logger.exception("BrokerBridge: order_stock_async 调用异常")
            raise

        if seq == -1:
            logger.error("BrokerBridge: 下单请求失败 seq=-1, stock=%s, order=%s", stock_code, order_id)
            raise RuntimeError(f"xtquant 下单失败: {stock_code} {direction} {volume}股@{price}")

        # 记录映射
        with self._lock:
            self._seq_to_order_id[seq] = order_id

        logger.info(
            "BrokerBridge: 下单请求已发出 seq=%d, order=%s, stock=%s, %s %d股@%s",
            seq, order_id, stock_code, direction, volume, price,
        )
        return seq

    async def _async_cancel(self, order_id: str) -> int:
        """
        异步撤单（由 RealExecutor.cancel_order 调用）。

        Args:
            order_id: 内部订单号

        Returns:
            撤单请求序号，>0 成功，-1 失败
        """
        if not self._connected or self._xt_trader is None:
            logger.warning("BrokerBridge: 未连接，撤单 %s 忽略", order_id)
            return -1

        # 查找 broker_order_id（xtquant order_id）
        broker_order_id = self._find_broker_order_id(order_id)
        if broker_order_id is None:
            logger.warning(
                "BrokerBridge: 找不到 order_id=%s 对应的券商订单号，无法撤单", order_id
            )
            return -1

        try:
            seq = await asyncio.to_thread(
                self._xt_trader.cancel_order_stock_async,
                self._account,
                broker_order_id,
            )
        except Exception:
            logger.exception("BrokerBridge: cancel_order_stock_async 调用异常")
            return -1

        if seq == -1:
            logger.error(
                "BrokerBridge: 撤单请求失败 seq=-1, order=%s, broker_id=%s",
                order_id, broker_order_id,
            )
        else:
            logger.info(
                "BrokerBridge: 撤单请求已发出 seq=%d, order=%s, broker_id=%d",
                seq, order_id, broker_order_id,
            )
        return seq

    def _find_broker_order_id(self, internal_order_id: str) -> int | None:
        """
        根据内部 order_id 查找 xtquant broker_order_id。

        查找路径：
        1. RealExecutor.orders_running 中的 order.broker_order_id
        2. _broker_to_internal 反向映射
        """
        # 优先从 RealExecutor 获取（最权威）
        order = self.real_executor.orders_running.get(internal_order_id)
        if order is not None and order.broker_order_id:
            try:
                return int(order.broker_order_id)
            except (ValueError, TypeError):
                pass

        # 从反向映射查找
        with self._lock:
            for broker_id, int_id in self._broker_to_internal.items():
                if int_id == internal_order_id:
                    return broker_id

        return None

    # ── 回调类工厂 ──────────────────────────────────

    def _create_callback_class(self):
        """
        动态创建 XtQuantTraderCallback 子类。

        使用工厂方法而非直接定义类，是为了让回调方法能访问 self（BrokerBridge）
        而不用全局变量。
        """
        bridge = self

        from xtquant.xttrader import XtQuantTraderCallback

        class BrokerCallback(XtQuantTraderCallback):
            """xtquant 回调 → RealExecutor 回调队列的桥接"""

            def on_connected(self):
                logger.info("BrokerBridge: MiniQMT 连接成功")

            def on_disconnected(self):
                logger.warning("BrokerBridge: MiniQMT 连接断开")
                bridge._connected = False

            def on_account_status(self, status):
                logger.info(
                    "BrokerBridge: 账号状态变更 account=%s, status=%s",
                    status.account_id, status.status,
                )

            def on_stock_order(self, order):
                """
                委托信息推送 → RealExecutor.on_order_callback

                XtOrder 关键字段：
                  order_id: xtquant 内部订单号（用于撤单）
                  stock_code, order_type, order_volume, price
                  traded_volume, traded_price
                  order_status, status_msg
                  strategy_name: 我们存入的内部 order_id
                  order_remark: 我们存入的内部 order_id（截断版）
                """
                # 从 strategy_name 或 order_remark 取回内部 order_id
                internal_order_id = (
                    order.strategy_name
                    or order.order_remark
                    or ""
                ).strip()

                # 记录映射：broker_order_id → internal_order_id
                if internal_order_id and order.order_id:
                    with bridge._lock:
                        bridge._broker_to_internal[order.order_id] = internal_order_id

                    # 更新 RealExecutor 中订单的 broker_order_id
                    rt_order = bridge.real_executor.orders_running.get(internal_order_id)
                    if rt_order is not None and not rt_order.broker_order_id:
                        rt_order.broker_order_id = str(order.order_id)
                        rt_order.order_sysid = str(getattr(order, "order_sysid", "") or "")

                data = {
                    "order_id": internal_order_id,
                    "broker_order_id": order.order_id,
                    "order_sysid": getattr(order, "order_sysid", "") or "",
                    "stock_code": order.stock_code,
                    "order_type": order.order_type,
                    "order_volume": order.order_volume,
                    "price": order.price,
                    "traded_volume": order.traded_volume,
                    "traded_price": order.traded_price,
                    "order_status": order.order_status,
                    "status_msg": order.status_msg or "",
                }

                try:
                    bridge.real_executor.on_order_callback(data)
                except Exception:
                    logger.exception("BrokerBridge: on_order_callback 投递异常")

            def on_stock_trade(self, trade):
                """
                成交信息推送 → RealExecutor.on_trade_callback

                XtTrade 关键字段：
                  order_id: xtquant 内部订单号（与 XtOrder.order_id 对应）
                  traded_id, traded_price, traded_volume, traded_amount
                  order_sysid, commission
                """
                # 通过 xtquant order_id 反查内部 order_id
                internal_order_id = bridge._broker_to_internal.get(trade.order_id, "")

                if not internal_order_id:
                    # 尝试从 strategy_name / order_remark 获取
                    internal_order_id = (
                        getattr(trade, "strategy_name", "")
                        or getattr(trade, "order_remark", "")
                        or ""
                    ).strip()

                if not internal_order_id:
                    logger.warning(
                        "BrokerBridge: 成交回调找不到内部 order_id, broker_order_id=%s",
                        trade.order_id,
                    )
                    return

                data = {
                    "order_id": internal_order_id,
                    "broker_order_id": trade.order_id,
                    "traded_id": trade.traded_id,
                    "traded_price": trade.traded_price,
                    "traded_volume": trade.traded_volume,
                    "traded_amount": trade.traded_amount,
                    "order_sysid": getattr(trade, "order_sysid", "") or "",
                    "commission": getattr(trade, "commission", 0) or 0,
                }

                try:
                    bridge.real_executor.on_trade_callback(data)
                except Exception:
                    logger.exception("BrokerBridge: on_trade_callback 投递异常")

            def on_stock_position(self, position):
                """持仓信息推送（文档标注目前不生效，仅记录日志）"""
                logger.debug(
                    "BrokerBridge: 持仓推送 stock=%s, vol=%d",
                    position.stock_code, position.volume,
                )

            def on_order_error(self, order_error):
                """下单失败推送 → RealExecutor.on_order_error_callback"""
                internal_order_id = ""
                # 尝试从 seq 映射找
                if hasattr(order_error, "seq") and order_error.seq:
                    internal_order_id = bridge._seq_to_order_id.pop(order_error.seq, "")
                # 尝试从 broker_order_id 反查
                if not internal_order_id and hasattr(order_error, "order_id") and order_error.order_id:
                    internal_order_id = bridge._broker_to_internal.get(order_error.order_id, "")

                data = {
                    "order_id": internal_order_id,
                    "broker_order_id": getattr(order_error, "order_id", 0),
                    "error_id": getattr(order_error, "error_id", 0),
                    "error_msg": getattr(order_error, "error_msg", "") or "",
                }
                logger.warning(
                    "BrokerBridge: 下单失败 order=%s, error=%s (%s)",
                    internal_order_id, data["error_msg"], data["error_id"],
                )

                try:
                    bridge.real_executor.on_order_error_callback(data)
                except Exception:
                    logger.exception("BrokerBridge: on_order_error_callback 投递异常")

            def on_cancel_error(self, cancel_error):
                """撤单失败推送 → RealExecutor.on_cancel_error_callback"""
                data = {
                    "order_id": getattr(cancel_error, "order_id", 0),
                    "error_id": getattr(cancel_error, "error_id", 0),
                    "error_msg": getattr(cancel_error, "error_msg", "") or "",
                }
                logger.warning(
                    "BrokerBridge: 撤单失败 broker_id=%s, error=%s (%s)",
                    data["order_id"], data["error_msg"], data["error_id"],
                )

                try:
                    bridge.real_executor.on_cancel_error_callback(data)
                except Exception:
                    logger.exception("BrokerBridge: on_cancel_error_callback 投递异常")

            def on_order_stock_async_response(self, response):
                """
                异步下单回报 → RealExecutor.on_async_order_response

                XtOrderResponse 关键字段：
                  seq: 请求序号（与 order_stock_async 返回值对应）
                  order_id: xtquant 内部订单号（用于后续撤单/查询）
                """
                seq = response.seq
                broker_order_id = response.order_id

                # 取出内部 order_id
                internal_order_id = bridge._seq_to_order_id.pop(seq, "")

                if internal_order_id and broker_order_id:
                    with bridge._lock:
                        bridge._broker_to_internal[broker_order_id] = internal_order_id

                    # 更新 broker_order_id 到 Order 对象
                    rt_order = bridge.real_executor.orders_running.get(internal_order_id)
                    if rt_order is not None and not rt_order.broker_order_id:
                        rt_order.broker_order_id = str(broker_order_id)

                data = {
                    "seq": seq,
                    "order_id": internal_order_id,
                    "broker_order_id": broker_order_id,
                }
                logger.info(
                    "BrokerBridge: 异步下单回报 seq=%d, internal=%s, broker=%d",
                    seq, internal_order_id, broker_order_id,
                )

                try:
                    bridge.real_executor.on_async_order_response(data)
                except Exception:
                    logger.exception("BrokerBridge: on_async_order_response 投递异常")

            def on_cancel_order_stock_async_response(self, response):
                """异步撤单回报（仅日志记录）"""
                logger.info(
                    "BrokerBridge: 异步撤单回报 seq=%d, result=%s",
                    getattr(response, "seq", 0),
                    getattr(response, "cancel_result", "unknown"),
                )

        return BrokerCallback
