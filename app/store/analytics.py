"""
Analytics query layer — dataframes and metrics for dashboard/analysis pages.

All functions accept a SQLAlchemy Session and return pandas DataFrames or
plain dicts.  No separate DB engine — reuses the Repository session.
"""
import logging
import threading
from datetime import datetime, date
from decimal import Decimal
from collections import defaultdict

import pandas as pd
from sqlalchemy import text

from . import models

logger = logging.getLogger(__name__)

# ── xtquant helpers ──────────────────────────

try:
    from xtquant import xtdata
    XTQUANT_AVAILABLE = True
except ImportError:
    XTQUANT_AVAILABLE = False

_xtdata_lock = threading.Lock()
_stock_names_cache: dict[str, str] = {}
_cache_timestamp: dict[str, datetime] = {}
CACHE_EXPIRE_SECONDS = 3600


def _normalize_code(code: str) -> str:
    if "." in code:
        return code
    if code.startswith(("60", "68")):
        return f"{code}.SH"
    if code.startswith(("00", "30")):
        return f"{code}.SZ"
    if code.startswith(("8", "9")):
        return f"{code}.BJ"
    return code


def get_stock_names(stock_codes: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    if not stock_codes:
        return result
    stock_codes = list(set(stock_codes))

    if XTQUANT_AVAILABLE:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_one(code):
            try:
                key = _normalize_code(code)
                detail = xtdata.get_instrument_detail(key)
                name = detail.get("InstrumentName", code) if detail else code
                return code, name
            except Exception:
                return code, code

        with ThreadPoolExecutor(max_workers=min(10, len(stock_codes))) as ex:
            for future in as_completed({ex.submit(_fetch_one, c): c for c in stock_codes}):
                code, name = future.result()
                result[code] = name
                _stock_names_cache[code] = name
                _cache_timestamp[code] = datetime.now()
    else:
        for code in stock_codes:
            result[code] = code

    return result


def get_realtime_prices(stock_codes: list[str]) -> dict[str, float]:
    if not XTQUANT_AVAILABLE or not stock_codes:
        return {}
    try:
        with _xtdata_lock:
            ticks = xtdata.get_full_tick(list(stock_codes))
        prices: dict[str, float] = {}
        for code in stock_codes:
            code_key = _normalize_code(code)
            tick = ticks.get(code_key) or ticks.get(code)
            if tick:
                price = tick.get("lastPrice") or tick.get("lastClose")
                if price and float(price) > 0:
                    prices[code] = float(price)
        return prices
    except Exception as e:
        logger.warning("获取实时价格失败: %s", e)
        return {}


# ── DataFrame load helpers ───────────────────

def _rows_to_df(rows, columns: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame([dict(r._mapping) for r in rows], columns=columns)


# ── Strategies ───────────────────────────────

def get_strategies_list(session) -> pd.DataFrame:
    rows = session.query(models.Strategys).all()
    if not rows:
        return pd.DataFrame()
    data = []
    for r in rows:
        data.append({
            "strategy_id": r.strategy_id,
            "name": r.name or "",
            "description": r.description or "",
            "trade_mode": r.trade_mode or 0,
            "initial_cash": float(r.initial_cash) if r.initial_cash else 0.0,
            "available_cash": float(r.available_cash) if r.available_cash else 0.0,
            "frozen_cash": float(r.frozen_cash) if r.frozen_cash else 0.0,
        })
    return pd.DataFrame(data)


# ── Orders ───────────────────────────────────

def get_orders_df(session, strategy_id: str | None = None) -> pd.DataFrame:
    q = session.query(models.Orders)
    if strategy_id:
        q = q.filter(models.Orders.strategy_id == strategy_id)
    rows = q.order_by(models.Orders.order_time.desc()).all()
    if not rows:
        return pd.DataFrame()
    data = []
    for r in rows:
        data.append({
            "client_order_id": r.client_order_id,
            "strategy_id": r.strategy_id,
            "stock_code": r.stock_code or "",
            "order_time": r.order_time,
            "order_type": r.order_type or 0,
            "order_volume": r.order_volume or 0,
            "price": float(r.price) if r.price else 0.0,
            "traded_volume": r.traded_volume or 0,
            "traded_price": float(r.traded_price) if r.traded_price else 0.0,
            "order_status": r.order_status or 0,
            "status_msg": r.status_msg or "",
            "order_remark": r.order_remark or "",
        })
    return pd.DataFrame(data)


# ── Trades ───────────────────────────────────

def get_trades_df(session, strategy_id: str | None = None) -> pd.DataFrame:
    q = session.query(models.Trades)
    if strategy_id:
        q = q.filter(models.Trades.strategy_id == strategy_id)
    rows = q.order_by(models.Trades.traded_time.desc()).all()
    if not rows:
        return pd.DataFrame()
    data = []
    for r in rows:
        data.append({
            "traded_id": r.traded_id,
            "strategy_id": r.strategy_id,
            "stock_code": r.stock_code or "",
            "order_type": r.order_type or 0,
            "traded_price": float(r.traded_price) if r.traded_price else 0.0,
            "traded_volume": r.traded_volume or 0,
            "traded_amount": float(r.traded_amount) if r.traded_amount else 0.0,
            "traded_time": r.traded_time,
        })
    return pd.DataFrame(data)


# ── Positions ────────────────────────────────

def get_positions_df(session, strategy_id: str | None = None,
                     use_realtime_price: bool = True) -> pd.DataFrame:
    today = date.today()
    sql = text("""
        SELECT p.strategy_id, p.stock_code, p.total, p.available,
               p.frozen, p.avg_price, p.remark
        FROM positions p
        JOIN (
            SELECT strategy_id, stock_code, MAX(today) AS max_today
            FROM positions WHERE today <= :today
            GROUP BY strategy_id, stock_code
        ) m ON p.strategy_id = m.strategy_id AND p.stock_code = m.stock_code
           AND p.today = m.max_today
        WHERE p.total > 0
    """)
    params = {"today": today}
    if strategy_id:
        sql = text("""
            SELECT p.strategy_id, p.stock_code, p.total, p.available,
                   p.frozen, p.avg_price, p.remark
            FROM positions p
            JOIN (
                SELECT strategy_id, stock_code, MAX(today) AS max_today
                FROM positions WHERE today <= :today AND strategy_id = :sid
                GROUP BY strategy_id, stock_code
            ) m ON p.strategy_id = m.strategy_id AND p.stock_code = m.stock_code
               AND p.today = m.max_today
            WHERE p.total > 0
        """)
        params = {"today": today, "sid": strategy_id}

    rows = session.execute(sql, params).fetchall()
    if not rows:
        return pd.DataFrame()

    data = []
    for r in rows:
        data.append({
            "strategy_id": r.strategy_id,
            "stock_code": r.stock_code,
            "total": r.total or 0,
            "available": r.available or 0,
            "frozen": r.frozen or 0,
            "avg_price": float(r.avg_price) if r.avg_price else 0.0,
            "remark": r.remark or "",
        })

    df = pd.DataFrame(data)
    if df.empty:
        return df

    if use_realtime_price and XTQUANT_AVAILABLE:
        codes = df["stock_code"].unique().tolist()
        prices = get_realtime_prices(codes)
        if prices:
            df["market_price"] = df["stock_code"].map(prices).fillna(df["avg_price"])
        else:
            df["market_price"] = df["avg_price"]
    else:
        df["market_price"] = df["avg_price"]

    df["mv"] = df["total"].astype(float) * df["market_price"].astype(float)
    df["cv"] = df["total"].astype(float) * df["avg_price"].astype(float)
    df["pnl"] = df["mv"] - df["cv"]
    df["pnl_pct"] = (df["pnl"] / df["cv"].replace(0, float('nan')) * 100).fillna(0)
    return df


# ── Daily account snapshot ───────────────────

def get_daily_account_snapshot(session, strategy_id: str | None = None,
                               start_date=None, end_date=None) -> pd.DataFrame:
    q = session.query(models.DailyAccountSnapshot)
    if strategy_id:
        q = q.filter(models.DailyAccountSnapshot.strategy_id == strategy_id)
    if start_date:
        q = q.filter(models.DailyAccountSnapshot.snapshot_date >= start_date)
    if end_date:
        q = q.filter(models.DailyAccountSnapshot.snapshot_date <= end_date)
    rows = q.order_by(models.DailyAccountSnapshot.snapshot_date.desc()).all()
    if not rows:
        return pd.DataFrame()
    data = []
    for r in rows:
        data.append({
            "strategy_id": r.strategy_id,
            "snapshot_date": r.snapshot_date,
            "total_assets": float(r.total_assets) if r.total_assets else 0.0,
            "available_cash": float(r.available_cash) if r.available_cash else 0.0,
            "frozen_cash": float(r.frozen_cash) if r.frozen_cash else 0.0,
            "position_value": float(r.position_value) if r.position_value else 0.0,
            "position_count": r.position_count or 0,
        })
    return pd.DataFrame(data)


# ── Day-T records ────────────────────────────

def get_day_t_records(session, strategy_id: str | None = None,
                      start_date=None, end_date=None) -> pd.DataFrame:
    q = session.query(models.DayTRecords)
    if strategy_id:
        q = q.filter(models.DayTRecords.strategy_id == strategy_id)
    if start_date:
        q = q.filter(models.DayTRecords.trade_date >= start_date)
    if end_date:
        q = q.filter(models.DayTRecords.trade_date <= end_date)
    rows = q.order_by(models.DayTRecords.trade_date.desc()).all()
    if not rows:
        return pd.DataFrame()
    data = []
    for r in rows:
        data.append({
            "strategy_id": r.strategy_id,
            "stock_code": r.stock_code or "",
            "trade_date": r.trade_date,
            "buy_volume": r.buy_volume or 0,
            "buy_amount": float(r.buy_amount) if r.buy_amount else 0.0,
            "avg_buy_price": float(r.avg_buy_price) if r.avg_buy_price else 0.0,
            "sell_volume": r.sell_volume or 0,
            "sell_amount": float(r.sell_amount) if r.sell_amount else 0.0,
            "avg_sell_price": float(r.avg_sell_price) if r.avg_sell_price else 0.0,
            "t_volume": r.t_volume or 0,
            "t_profit": float(r.t_profit) if r.t_profit else 0.0,
            "t_return_rate": float(r.t_return_rate) if r.t_return_rate else 0.0,
            "holding_change": r.holding_change or 0,
        })
    return pd.DataFrame(data)


# ── Settlements ──────────────────────────────

def get_settlements(session, strategy_id: str | None = None,
                    is_closed: bool | None = None) -> pd.DataFrame:
    q = session.query(models.Settlements)
    if strategy_id:
        q = q.filter(models.Settlements.strategy_id == strategy_id)
    if is_closed is not None:
        q = q.filter(models.Settlements.is_closed == (1 if is_closed else 0))
    rows = q.order_by(models.Settlements.first_buy_time.desc()).all()
    if not rows:
        return pd.DataFrame()
    data = []
    for r in rows:
        data.append({
            "strategy_id": r.strategy_id,
            "stock_code": r.stock_code or "",
            "first_buy_time": r.first_buy_time,
            "close_time": r.close_time,
            "total_buy_volume": r.total_buy_volume or 0,
            "total_buy_amount": float(r.total_buy_amount) if r.total_buy_amount else 0.0,
            "total_sell_volume": r.total_sell_volume or 0,
            "total_sell_amount": float(r.total_sell_amount) if r.total_sell_amount else 0.0,
            "avg_cost_price": float(r.avg_cost_price) if r.avg_cost_price else 0.0,
            "realized_profit": float(r.realized_profit) if r.realized_profit else 0.0,
            "profit_rate": float(r.profit_rate) if r.profit_rate else 0.0,
            "is_closed": r.is_closed or 0,
        })
    return pd.DataFrame(data)


# ── Equity curve ─────────────────────────────

def calculate_equity_curve(session, strategy_id: str) -> pd.DataFrame:
    """Prefer daily snapshots; fall back to trade-replay."""
    strategies_df = get_strategies_list(session)
    info = strategies_df[strategies_df["strategy_id"] == strategy_id]
    if info.empty:
        return pd.DataFrame()

    initial_cash = float(info.iloc[0]["initial_cash"])

    snap = get_daily_account_snapshot(session, strategy_id)
    if not snap.empty:
        snap = snap.copy()
        snap["snapshot_date"] = pd.to_datetime(snap["snapshot_date"])
        snap = snap.sort_values("snapshot_date")
        snap["equity_ratio"] = snap["total_assets"] / initial_cash
        snap["return_pct"] = (snap["equity_ratio"] - 1) * 100
        snap = snap.rename(columns={"snapshot_date": "date", "total_assets": "equity"})
        snap["strategy_id"] = strategy_id
        return snap[["strategy_id", "date", "equity", "equity_ratio", "return_pct"]]

    trades_df = get_trades_df(session, strategy_id)
    if trades_df.empty:
        return pd.DataFrame()

    trades_df["traded_time"] = pd.to_datetime(trades_df["traded_time"])
    trades_df = trades_df.sort_values("traded_time")

    positions: dict[str, int] = {}
    avg_prices: dict[str, float] = {}
    cash = initial_cash
    rows = []

    for _, t in trades_df.iterrows():
        code = t["stock_code"]
        vol = int(t["traded_volume"])
        price = float(t["traded_price"])
        amt = price * vol
        if int(t["order_type"]) == 23:  # buy
            cash -= amt
            old = positions.get(code, 0)
            new = old + vol
            avg_prices[code] = (
                (avg_prices.get(code, price) * old + price * vol) / new
                if old > 0 else price
            )
            positions[code] = new
        else:  # sell
            cash += amt
            old = positions.get(code, 0)
            new = old - vol
            if new <= 0:
                positions.pop(code, None)
                avg_prices.pop(code, None)
            else:
                positions[code] = new

        rows.append({
            "strategy_id": strategy_id,
            "date": t["traded_time"],
            "equity": cash + sum(positions.get(c, 0) * avg_prices.get(c, 0) for c in positions),
            "equity_ratio": 0,
            "return_pct": 0,
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result["equity_ratio"] = result["equity"].astype(float) / initial_cash
        result["return_pct"] = (result["equity_ratio"] - 1) * 100
    return result


def calculate_risk_metrics(equity_df: pd.DataFrame) -> dict:
    if equity_df.empty:
        return {}
    metrics = {}
    for sid in equity_df["strategy_id"].unique():
        sub = equity_df[equity_df["strategy_id"] == sid].sort_values("date").copy()
        if len(sub) < 2:
            continue
        sub["daily_return"] = sub["equity_ratio"].pct_change()
        cummax = sub["equity_ratio"].expanding().max()
        drawdown = (sub["equity_ratio"] - cummax) / cummax
        daily = sub["daily_return"].dropna()
        days = (sub["date"].max() - sub["date"].min()).days or 1

        metrics[sid] = {
            "max_drawdown": float(drawdown.min()),
            "sharpe_ratio": float(daily.mean() / daily.std() * (252 ** 0.5)) if len(daily) > 1 and daily.std() > 0 else 0,
            "annual_return": float((1 + (sub["equity_ratio"].iloc[-1] - 1)) ** (365 / days) - 1),
            "volatility": float(daily.std() * (252 ** 0.5)) if len(daily) > 1 else 0,
            "win_rate": float((daily > 0).sum() / len(daily)) if len(daily) > 0 else 0,
            "total_return": float(sub["equity_ratio"].iloc[-1] - 1),
        }
    return metrics


def calculate_trade_statistics(session, strategy_id: str | None = None) -> dict:
    trades_df = get_trades_df(session, strategy_id)
    if trades_df.empty:
        return {}

    total = len(trades_df)
    buy = int((trades_df["order_type"] == 23).sum())
    sell = int((trades_df["order_type"] == 24).sum())
    trades_df["traded_time"] = pd.to_datetime(trades_df["traded_time"])
    day_span = max((trades_df["traded_time"].max() - trades_df["traded_time"].min()).days, 1)
    avg_amount = float(trades_df["traded_amount"].mean()) if "traded_amount" in trades_df.columns else 0

    stock_stats = {}
    for code in trades_df["stock_code"].unique():
        sub = trades_df[trades_df["stock_code"] == code].sort_values("traded_time")
        pos = 0
        cost = 0.0
        profit = 0.0
        win = 0
        loss = 0
        for _, t in sub.iterrows():
            price = float(t["traded_price"])
            vol = int(t["traded_volume"])
            if int(t["order_type"]) == 23:  # buy
                cost = (cost * pos + price * vol) / (pos + vol) if pos + vol > 0 else price
                pos += vol
            else:  # sell
                if pos > 0:
                    pnl = (price - cost) * vol
                    profit += pnl
                    if pnl > 0:
                        win += 1
                    elif pnl < 0:
                        loss += 1
                pos -= vol
                if pos <= 0:
                    pos = 0
                    cost = 0.0
        total_wl = win + loss
        stock_stats[code] = {
            "total_profit": profit,
            "win_count": win,
            "loss_count": loss,
            "win_rate": win / total_wl * 100 if total_wl > 0 else 0,
            "trade_count": len(sub),
        }

    return {
        "total_trades": total,
        "buy_trades": buy,
        "sell_trades": sell,
        "trade_frequency": total / day_span,
        "avg_trade_amount": avg_amount,
        "stock_stats": stock_stats,
    }
