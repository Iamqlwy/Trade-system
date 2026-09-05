"""
量化交易系统 - 数据访问层

提供策略状态与 MySQL 之间的读写操作。
store() 方法在单次事务中持久化所有状态，保证一致性。

⚠️ Trade 表列映射（易错）：
  - strategy_id 列 ← Trade.strategy_id（基础策略ID，如 "test"）
  - client_order_id 列 ← Trade.order_id（client_order_id，如 "test_5"）
  - broker_order_id 列 ← Trade.order_id（与 client_order_id 相同，xtquant 回调无独立 broker_order_id）
  - load_todays_trades 读取时 client_order_id 列 → Trade.strategy_id（兼容旧数据）

⚠️ DayT 计算：
  - 仅统计 order_type=23（买）和 24（卖），不处理信用交易（27/28）
  - 买入量和卖出量都需 > 0 才记录做T数据
  - 做T手续费按成交比例分摊到买卖两侧
"""
import heapq
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from .. import datatypes as dt
from ..config import settings
from ..engine.strategy import Strategy
from ..engine.commission import CommissionCalculator, set_calculator
from . import models

logger = logging.getLogger(__name__)


class Repository:
    """策略状态持久化"""

    def __init__(self, db_url: str = ""):
        url = db_url or settings.db_url
        self.engine = create_engine(url, pool_size=5, max_overflow=10, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine)

    # ── 通用 ─────────────────────────────────

    def _today(self) -> date:
        return date.today()

    def _today_datetime(self) -> datetime:
        return datetime.now()

    # ── 加载（启动时恢复） ────────────────────

    def load_strategies(self, session: Session) -> dict[str, Strategy]:
        rows = session.query(models.Strategys).filter(
            models.Strategys.is_deleted == 0
        ).all()
        result = {}
        for r in rows:
            s = Strategy(
                strategy_id=r.strategy_id,
                name=r.name or "",
                description=r.description or "",
                detail=r.detail or "",
                trade_mode=r.trade_mode or 0,
                initial_cash=Decimal(str(r.initial_cash)),
                available_cash=Decimal(str(r.available_cash)),
                frozen_cash=Decimal(str(r.frozen_cash)),
            )
            result[s.strategy_id] = s
        return result

    def load_positions(self, session: Session) -> dict[str, dict[str, dt.Position]]:
        """加载每个策略的最新持仓快照（同一天内取最新）"""
        today = self._today()
        # 按 (strategy_id, stock_code) 取 today <= 今天的最近一条
        sql = text("""
            SELECT p.strategy_id, p.stock_code, p.total, p.available,
                   p.frozen, p.unavailable, p.avg_price, p.remark, p.today
            FROM positions p
            JOIN (
                SELECT strategy_id, stock_code, MAX(today) AS max_today
                FROM positions WHERE today <= :today
                GROUP BY strategy_id, stock_code
            ) m ON p.strategy_id=m.strategy_id AND p.stock_code=m.stock_code AND p.today=m.max_today
        """)
        rows = session.execute(sql, {"today": today}).fetchall()
        result: dict[str, dict[str, dt.Position]] = {}
        cross_day = False
        for r in rows:
            sid = r.strategy_id
            code = r.stock_code
            pos = dt.Position(
                stock_code=code,
                total=r.total or 0,
                available=r.available or 0,
                frozen=r.frozen or 0,
                unavailable=r.unavailable or 0,
                avg_price=Decimal(str(r.avg_price)) if r.avg_price else Decimal("0"),
                remark=r.remark or "",
            )
            if r.today and r.today != today:
                cross_day = True
                pos.available += pos.unavailable
                pos.unavailable = 0
                pos.available += pos.frozen
                pos.frozen = 0
            result.setdefault(sid, {})[code] = pos
        if cross_day:
            logger.info("跨日：已解冻全部持仓")
        return result

    def load_lots(self, session: Session) -> dict[str, dict[str, list[dt.Lot]]]:
        rows = session.query(models.Lots).filter(models.Lots.lot_size > 0).all()
        result: dict[str, dict[str, list[dt.Lot]]] = {}
        for row in rows:
            lot = dt.Lot(
                strategy_id=row.strategy_id,
                stock_code=row.stock_code,
                lot_size=row.lot_size,
                open_time=row.open_time,
                open_price=Decimal(str(row.open_price)),
            )
            if row.strategy_id not in result:
                result[row.strategy_id] = {}
            if row.stock_code not in result[row.strategy_id]:
                result[row.strategy_id][row.stock_code] = []
            heapq.heappush(result[row.strategy_id][row.stock_code], lot)
        return result

    def load_settlements(self, session: Session) -> dict[str, dict[str, dt.Settlement]]:
        today_start = datetime.combine(self._today(), datetime.min.time())
        sql = text("""
            SELECT * FROM settlements
            WHERE is_closed = 0
               OR (is_closed = 1 AND close_time >= :today_start)
            ORDER BY strategy_id, stock_code, first_buy_time
        """)
        rows = session.execute(sql, {"today_start": today_start}).fetchall()
        result: dict[str, dict[str, dt.Settlement]] = {}
        for r in rows:
            settle = dt.Settlement(
                strategy_id=r.strategy_id,
                stock_code=r.stock_code,
                first_buy_time=r.first_buy_time or self._today_datetime(),
                total_buy_volume=r.total_buy_volume or 0,
                total_buy_amount=Decimal(str(r.total_buy_amount)) if r.total_buy_amount else Decimal("0"),
                total_sell_volume=r.total_sell_volume or 0,
                total_sell_amount=Decimal(str(r.total_sell_amount)) if r.total_sell_amount else Decimal("0"),
                avg_cost_price=Decimal(str(r.avg_cost_price)) if r.avg_cost_price else Decimal("0"),
                realized_profit=Decimal(str(r.realized_profit)) if r.realized_profit else Decimal("0"),
                is_closed=bool(r.is_closed),
                close_time=r.close_time,
            )
            result.setdefault(r.strategy_id, {})[r.stock_code] = settle
        return result

    def load_todays_orders(self, session: Session) -> list[dt.Order]:
        today_start = datetime.combine(self._today(), datetime.min.time())
        rows = session.query(models.Orders).filter(
            models.Orders.order_time >= today_start
        ).all()
        orders = []
        for r in rows:
            orders.append(dt.Order(
                order_id=r.client_order_id,
                strategy_id=r.strategy_id,
                account_type=r.account_type or 0,
                account_id=r.account_id or "",
                stock_code=r.stock_code or "",
                broker_order_id=r.broker_order_id or "",
                order_sysid=r.order_sysid or "",
                order_type=dt.OrderType(r.order_type) if r.order_type else dt.OrderType.STOCK_BUY,
                price_type=dt.PriceType(r.price_type) if r.price_type else dt.PriceType.FIX_PRICE,
                price=Decimal(str(r.price)) if r.price else Decimal("0"),
                order_volume=r.order_volume or 0,
                traded_volume=r.traded_volume or 0,
                traded_price=Decimal(str(r.traded_price)) if r.traded_price else Decimal("0"),
                traded_amount=Decimal(str(r.traded_amount)) if r.traded_amount else Decimal("0"),
                commission=Decimal(str(r.commission)) if r.commission else Decimal("0"),
                order_status=dt.OrderStatus(r.order_status) if r.order_status else dt.OrderStatus.ORDER_UNREPORTED,
                status_msg=r.status_msg or "",
                order_remark=r.order_remark or "",
                created_at=r.order_time or self._today_datetime(),
            ))
        return orders

    def get_max_order_seq(self, session: Session) -> dict[str, int]:
        """获取每个策略在所有历史订单中的最大 seq 号（用于重启后恢复 _seq_counter）"""
        from sqlalchemy import text
        try:
            rows = session.execute(text(
                "SELECT strategy_id, "
                "MAX(CAST(SUBSTRING_INDEX(client_order_id, '_', -1) AS UNSIGNED)) AS max_seq "
                "FROM orders "
                "WHERE client_order_id LIKE '%\\_%' "
                "GROUP BY strategy_id"
            )).fetchall()
            result: dict[str, int] = {}
            for r in rows:
                if r[0] and r[1] is not None:
                    result[r[0]] = int(r[1])
            return result
        except Exception:
            logger.debug("SQL 聚合查询失败，回退到 Python 遍历", exc_info=True)
            rows = session.query(
                models.Orders.client_order_id,
                models.Orders.strategy_id,
            ).all()
            max_seq: dict[str, int] = {}
            for r in rows:
                oid = r.client_order_id or ""
                idx = oid.rfind("_")
                if idx > 0:
                    tail = oid[idx + 1:]
                    if tail.isdigit():
                        sid = r.strategy_id
                        seq = int(tail)
                        if seq > max_seq.get(sid, 0):
                            max_seq[sid] = seq
            return max_seq

    def load_todays_trades(self, session: Session) -> list[dt.Trade]:
        today_start = datetime.combine(self._today(), datetime.min.time())
        rows = session.query(models.Trades).filter(
            models.Trades.traded_time >= today_start
        ).all()
        trades = []
        for r in rows:
            trades.append(dt.Trade(
                traded_id=r.traded_id,
                strategy_id=r.strategy_id,
                order_id=r.client_order_id or r.broker_order_id or "",
                stock_code=r.stock_code or "",
                account_type=r.account_type or 0,
                account_id=r.account_id or "",
                order_type=r.order_type or 23,
                order_sysid=r.order_sysid or "",
                traded_price=Decimal(str(r.traded_price)) if r.traded_price else Decimal("0"),
                traded_volume=r.traded_volume or 0,
                traded_amount=Decimal(str(r.traded_amount)) if r.traded_amount else Decimal("0"),
                traded_time=r.traded_time or self._today_datetime(),
                order_remark=r.order_remark or "",
            ))
        return trades

    def load_commission_configs(self, session: Session) -> dict[str, CommissionCalculator]:
        rows = session.query(models.CommissionConfigs).all()
        configs = {}
        for r in rows:
            set_calculator(r.strategy_id, {
                "commission_rate": Decimal(str(r.commission_rate)) if r.commission_rate else Decimal("0.0003"),
                "stamp_tax_rate": Decimal(str(r.stamp_tax_rate)) if r.stamp_tax_rate else Decimal("0.0005"),
                "transfer_fee_rate": Decimal(str(r.transfer_fee_rate)) if r.transfer_fee_rate else Decimal("0.00002"),
                "min_commission": Decimal(str(r.min_commission)) if r.min_commission else Decimal("5.00"),
            })
        from ..engine.commission import _calculators
        return dict(_calculators)

    # ── 新增 ──────────────────────────────────

    def add_strategy(self, strategy: Strategy, owner_id: int | None = None) -> bool:
        """将新策略写入数据库"""
        session = self.SessionLocal()
        try:
            self._upsert(session, models.Strategys(
                strategy_id=strategy.strategy_id,
                name=strategy.name,
                description=strategy.description,
                detail=strategy.detail,
                trade_mode=strategy.trade_mode,
                initial_cash=strategy.initial_cash,
                available_cash=strategy.available_cash,
                frozen_cash=strategy.frozen_cash,
                is_deleted=0,
                owner_id=owner_id,
            ))
            session.commit()
            logger.info("策略 %s 已创建", strategy.strategy_id)
            return True
        except Exception:
            session.rollback()
            logger.exception("创建策略 %s 失败", strategy.strategy_id)
            return False
        finally:
            session.close()

    # ── 删除（逻辑删除） ──────────────────────

    def delete_strategy(self, strategy_id: str) -> bool:
        """逻辑删除策略：设置 is_deleted=1，返回是否成功"""
        session = self.SessionLocal()
        try:
            row = session.query(models.Strategys).filter_by(
                strategy_id=strategy_id, is_deleted=0
            ).first()
            if row is None:
                return False
            row.is_deleted = 1
            session.commit()
            logger.info("策略 %s 已逻辑删除", strategy_id)
            return True
        except Exception:
            session.rollback()
            logger.exception("删除策略 %s 失败", strategy_id)
            return False
        finally:
            session.close()

    # ── 保存 ─────────────────────────────────

    def store(self, strategies: dict[str, Strategy],
              sim_orders: list[dt.Order], sim_trades: list[dt.Trade],
              real_orders: list[dt.Order], real_trades: list[dt.Trade]) -> None:
        """事务性保存全部状态"""
        session = self.SessionLocal()
        try:
            self._save_strategies(session, strategies)
            self._save_positions(session, strategies)
            self._save_lots(session, strategies)
            self._save_orders_batch(session, sim_orders + real_orders)
            self._save_trades_batch(session, sim_trades + real_trades)
            self._save_settlements(session, strategies)
            self._save_daily_snapshots(session, strategies)
            self._update_day_t_records(session)
            session.commit()
            logger.info("Store: 状态已持久化")
        except Exception:
            session.rollback()
            logger.exception("Store: 持久化失败")
        finally:
            session.close()

    def _upsert(self, session: Session, instance) -> None:
        session.merge(instance)

    def _save_strategies(self, session: Session, strategies: dict[str, Strategy]) -> None:
        for s in strategies.values():
            # 先查已有记录，避免 merge 覆盖 owner_id
            existing = session.query(models.Strategys).filter_by(
                strategy_id=s.strategy_id,
            ).first()
            if existing:
                # 更新可变字段，保留 owner_id
                existing.name = s.name
                existing.description = s.description
                existing.detail = s.detail
                existing.trade_mode = s.trade_mode
                existing.initial_cash = s.initial_cash
                existing.available_cash = s.available_cash
                existing.frozen_cash = s.frozen_cash
            else:
                session.add(models.Strategys(
                    strategy_id=s.strategy_id,
                    name=s.name,
                    description=s.description,
                    detail=s.detail,
                    trade_mode=s.trade_mode,
                    initial_cash=s.initial_cash,
                    available_cash=s.available_cash,
                    frozen_cash=s.frozen_cash,
                    is_deleted=0,
                ))

    def _save_positions(self, session: Session, strategies: dict[str, Strategy]) -> None:
        today = self._today()
        for s in strategies.values():
            for code, pos in s.positions.items():
                self._upsert(session, models.Positions(
                    strategy_id=s.strategy_id,
                    stock_code=code,
                    today=today,
                    total=pos.total,
                    available=pos.available,
                    frozen=pos.frozen,
                    unavailable=pos.unavailable,
                    avg_price=pos.avg_price,
                    remark=pos.remark,
                ))

    def _save_lots(self, session: Session, strategies: dict[str, Strategy]) -> None:
        for s in strategies.values():
            for code, lot_heap in s.get_lots().items():
                temp = list(lot_heap)
                for lot in temp:
                    self._upsert(session, models.Lots(
                        strategy_id=s.strategy_id,
                        stock_code=lot.stock_code,
                        open_time=lot.open_time,
                        lot_size=lot.lot_size,
                        open_price=lot.open_price,
                    ))

    def _save_orders_batch(self, session: Session, orders: list[dt.Order]) -> None:
        for o in orders:
            client_order_id = o.order_id  # strategy_id_seq
            strategy_base = o.strategy_id
            broker_order_id = o.broker_order_id or ""
            self._upsert(session, models.Orders(
                client_order_id=client_order_id,
                strategy_id=strategy_base,
                account_type=o.account_type,
                account_id=o.account_id,
                stock_code=o.stock_code,
                broker_order_id=broker_order_id,
                order_sysid=o.order_sysid,
                order_time=o.created_at,
                order_type=int(o.order_type),
                price_type=int(o.price_type),
                price=o.price,
                order_volume=o.order_volume,
                traded_volume=o.traded_volume,
                traded_price=o.traded_price,
                traded_amount=o.traded_amount,
                commission=o.commission,
                order_status=int(o.order_status),
                status_msg=o.status_msg,
                order_remark=o.order_remark,
            ))

    def _save_trades_batch(self, session: Session, trades: list[dt.Trade]) -> None:
        for t in trades:
            self._upsert(session, models.Trades(
                traded_id=t.traded_id,
                strategy_id=t.strategy_id,
                client_order_id=t.order_id,
                broker_order_id=t.order_id,
                order_sysid=t.order_sysid,
                account_type=t.account_type,
                account_id=t.account_id,
                stock_code=t.stock_code,
                order_type=t.order_type,
                traded_time=t.traded_time,
                traded_price=t.traded_price,
                traded_volume=t.traded_volume,
                traded_amount=t.traded_amount,
                order_remark=t.order_remark,
            ))

    def _save_settlements(self, session: Session, strategies: dict[str, Strategy]) -> None:
        for s in strategies.values():
            for code, settle in s.settlements.items():
                self._upsert(session, models.Settlements(
                    strategy_id=s.strategy_id,
                    stock_code=code,
                    first_buy_time=settle.first_buy_time,
                    total_buy_volume=settle.total_buy_volume,
                    total_buy_amount=settle.total_buy_amount,
                    total_sell_volume=settle.total_sell_volume,
                    total_sell_amount=settle.total_sell_amount,
                    avg_cost_price=settle.avg_cost_price,
                    realized_profit=settle.realized_profit,
                    profit_rate=float(settle.profit_rate()),  # derived: realized_profit / total_buy_amount
                    is_closed=settle.is_closed,
                    close_time=settle.close_time,
                ))

    def _save_daily_snapshots(self, session: Session, strategies: dict[str, Strategy]) -> None:
        today = self._today()
        for s in strategies.values():
            positions = s.positions
            lots = s.get_lots()
            pos_value = Decimal("0")
            pos_cost = Decimal("0")
            pos_count = 0
            for code, pos in positions.items():
                if pos.total > 0:
                    pos_value += Decimal(pos.total) * pos.avg_price
                    pos_count += 1
                    # 使用 FIFO 批次的实际买入成本，而非当前均价
                    code_lots = lots.get(code, [])
                    total_cost = sum(
                        Decimal(lot.lot_size) * lot.open_price
                        for lot in code_lots
                    ) if code_lots else Decimal(pos.total) * pos.avg_price
                    pos_cost += total_cost

            total_assets = s.available_cash + s.frozen_cash + pos_value

            # 计算当日累计佣金（所有订单的佣金，含未成交预留）
            day_commission = sum(
                o.commission for o in s.orders.values()
            )

            self._upsert(session, models.DailyAccountSnapshot(
                strategy_id=s.strategy_id,
                snapshot_date=today,
                total_assets=total_assets,
                available_cash=s.available_cash,
                frozen_cash=s.frozen_cash,
                position_value=pos_value,
                position_cost=pos_cost,
                position_count=pos_count,
                order_count=len(s.orders),
                commission=day_commission,
            ))

    def _update_day_t_records(self, session: Session) -> None:
        """从 orders 表计算当日做T记录"""
        today = self._today()
        today_start = datetime.combine(today, datetime.min.time())
        rows = session.query(
            models.Orders.client_order_id,
            models.Orders.strategy_id,
            models.Orders.stock_code,
            models.Orders.order_type,
            models.Orders.traded_volume,
            models.Orders.traded_amount,
            models.Orders.commission,
        ).filter(
            models.Orders.order_time >= today_start,
            models.Orders.traded_volume > 0,
        ).all()

        if not rows:
            return

        from collections import defaultdict
        Stats = lambda: {"buy_vol": 0, "buy_amt": Decimal("0"), "buy_cnt": 0, "buy_comm": Decimal("0"),
                         "sell_vol": 0, "sell_amt": Decimal("0"), "sell_cnt": 0, "sell_comm": Decimal("0")}
        stats_map = defaultdict(Stats)

        for r in rows:
            sid = r.strategy_id
            code = r.stock_code
            vol = r.traded_volume or 0
            amt = Decimal(str(r.traded_amount)) if r.traded_amount else Decimal("0")
            comm = Decimal(str(r.commission)) if r.commission else Decimal("0")

            key = (sid, code)
            if r.order_type == 23:  # buy
                stats_map[key]["buy_vol"] += vol
                stats_map[key]["buy_amt"] += amt
                stats_map[key]["buy_cnt"] += 1
                stats_map[key]["buy_comm"] += comm
            elif r.order_type == 24:  # sell
                stats_map[key]["sell_vol"] += vol
                stats_map[key]["sell_amt"] += amt
                stats_map[key]["sell_cnt"] += 1
                stats_map[key]["sell_comm"] += comm

        # 删除今日已有记录
        session.query(models.DayTRecords).filter(
            models.DayTRecords.trade_date == today
        ).delete()

        for (sid, code), st in stats_map.items():
            if st["buy_vol"] == 0 or st["sell_vol"] == 0:
                continue
            avg_buy = st["buy_amt"] / Decimal(st["buy_vol"]) if st["buy_vol"] > 0 else Decimal("0")
            avg_sell = st["sell_amt"] / Decimal(st["sell_vol"]) if st["sell_vol"] > 0 else Decimal("0")
            t_vol = min(st["buy_vol"], st["sell_vol"])

            t_comm = Decimal("0")
            if st["buy_vol"] > 0:
                t_comm += st["buy_comm"] * Decimal(t_vol) / Decimal(st["buy_vol"])
            if st["sell_vol"] > 0:
                t_comm += st["sell_comm"] * Decimal(t_vol) / Decimal(st["sell_vol"])

            t_profit = Decimal(t_vol) * (avg_sell - avg_buy) - t_comm
            t_rate = float(t_profit / (Decimal(t_vol) * avg_buy) * Decimal("100")) if t_vol > 0 and avg_buy > Decimal("0") else 0.0
            holding_chg = st["buy_vol"] - st["sell_vol"]

            session.add(models.DayTRecords(
                strategy_id=sid,
                stock_code=code,
                trade_date=today,
                buy_volume=st["buy_vol"],
                buy_amount=st["buy_amt"],
                buy_count=st["buy_cnt"],
                avg_buy_price=avg_buy,
                sell_volume=st["sell_vol"],
                sell_amount=st["sell_amt"],
                sell_count=st["sell_cnt"],
                avg_sell_price=avg_sell,
                t_volume=t_vol,
                t_profit=t_profit,
                t_return_rate=t_rate,
                holding_change=holding_chg,
            ))
