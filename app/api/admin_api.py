"""
Admin statistics API — 系统统计信息（仅管理员）

提供系统级统计数据供 AdminDashboardView 使用。
"""

import logging
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from ..dependencies import repository, get_strategies
from ..permissions.dependencies import require_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class OnlineUserItem(BaseModel):
    user_id: int
    username: str
    role: str
    connected_since: datetime


class AdminStatsResponse(BaseModel):
    total_users: int
    total_strategies: int
    sim_strategies: int
    live_strategies: int
    total_orders: int
    total_orders_today: int
    total_trades: int
    total_trades_today: int
    pending_feedback_count: int
    total_monitors: int
    total_cron_jobs: int
    unique_online_count: int
    online_users: list[OnlineUserItem]
    total_assets: float = 0.0
    total_market_value: float = 0.0


class OnlineUsersResponse(BaseModel):
    unique_online_count: int
    online_users: list[OnlineUserItem]


class TrendsResponse(BaseModel):
    """历史趋势数据（按天统计）"""
    # 监控维度
    monitor_alerts: list[dict]           # [{date, count}]
    cron_jobs: list[dict]                # [{date, total, success, failed}]

    # 交易维度（拆分模拟/实盘）
    orders: list[dict]                   # [{date, sim, live}]
    trades: list[dict]                   # [{date, sim_count, live_count, sim_amount, live_amount}]
    assets: list[dict]                   # [{date, sim_total, live_total, sim_market, live_market}]

    # Agent 维度
    agent_sessions: list[dict]           # [{date, new_sessions, user_messages, context_chars}]

    # 用户 & 策略维度
    user_registrations: list[dict]       # [{date, new_users}]
    strategy_creations: list[dict]       # [{date, sim, live}]

    # 反馈维度
    feedbacks: list[dict]                # [{date, total, pending, resolved}]


def _db_session():
    return repository.SessionLocal()


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(user: dict = Depends(require_admin_user)):
    """获取系统统计信息（仅管理员）"""
    session = _db_session()
    try:
        today = date.today()

        total_users = session.execute(
            text("SELECT COUNT(*) FROM users")
        ).scalar() or 0

        total_strategies = session.execute(
            text("SELECT COUNT(*) FROM strategys WHERE is_deleted = 0")
        ).scalar() or 0

        sim_strategies = session.execute(
            text("SELECT COUNT(*) FROM strategys WHERE is_deleted = 0 AND trade_mode = 0")
        ).scalar() or 0

        live_strategies = session.execute(
            text("SELECT COUNT(*) FROM strategys WHERE is_deleted = 0 AND trade_mode = 1")
        ).scalar() or 0

        total_orders = session.execute(
            text("SELECT COUNT(*) FROM orders")
        ).scalar() or 0

        total_orders_today = session.execute(
            text("SELECT COUNT(*) FROM orders WHERE DATE(order_time) = :today"),
            {"today": today},
        ).scalar() or 0

        total_trades = session.execute(
            text("SELECT COUNT(*) FROM trades")
        ).scalar() or 0

        total_trades_today = session.execute(
            text("SELECT COUNT(*) FROM trades WHERE DATE(traded_time) = :today"),
            {"today": today},
        ).scalar() or 0

        pending_feedback_count = session.execute(
            text("SELECT COUNT(*) FROM feedbacks WHERE status = 'pending'")
        ).scalar() or 0

        total_monitors = session.execute(
            text("SELECT COUNT(*) FROM monitor_records")
        ).scalar() or 0

        total_cron_jobs = session.execute(
            text("SELECT COUNT(*) FROM cron_jobs")
        ).scalar() or 0

    except Exception:
        logger.exception("查询统计数据失败")
        total_users = total_strategies = sim_strategies = live_strategies = 0
        total_orders = total_orders_today = total_trades = total_trades_today = 0
        pending_feedback_count = total_monitors = total_cron_jobs = 0
    finally:
        session.close()

    # 在线用户（从 ConnectionRegistry）
    from ..services.connection_registry import connection_registry
    online_users_raw = connection_registry.get_online_users()
    unique_online_count = connection_registry.unique_online_count
    online_users = [OnlineUserItem(**u) for u in online_users_raw]

    # 策略资产聚合（从内存）
    strategies = get_strategies()
    total_assets = Decimal("0")
    total_market_value = Decimal("0")
    for s in strategies.values():
        total_assets += s.available_cash + s.frozen_cash
        for p in s.positions.values():
            if p.total > 0:
                total_market_value += Decimal(p.total) * p.avg_price
    total_assets += total_market_value

    return AdminStatsResponse(
        total_users=total_users,
        total_strategies=total_strategies,
        sim_strategies=sim_strategies,
        live_strategies=live_strategies,
        total_orders=total_orders,
        total_orders_today=total_orders_today,
        total_trades=total_trades,
        total_trades_today=total_trades_today,
        pending_feedback_count=pending_feedback_count,
        total_monitors=total_monitors,
        total_cron_jobs=total_cron_jobs,
        unique_online_count=unique_online_count,
        online_users=online_users,
        total_assets=float(total_assets),
        total_market_value=float(total_market_value),
    )


@router.get("/online-users", response_model=OnlineUsersResponse)
def get_online_users(user: dict = Depends(require_admin_user)):
    """获取在线用户列表（轻量级，适合轮询）"""
    from ..services.connection_registry import connection_registry
    users = connection_registry.get_online_users()
    return OnlineUsersResponse(
        unique_online_count=connection_registry.unique_online_count,
        online_users=[OnlineUserItem(**u) for u in users],
    )


@router.get("/trends", response_model=TrendsResponse)
def get_admin_trends(
    start_date: str,
    end_date: str,
    user: dict = Depends(require_admin_user),
):
    """获取历史趋势数据（仅管理员）

    交易相关数据已按 trade_mode 拆分为模拟/实盘。
    """
    session = _db_session()
    params = {"start": start_date, "end": end_date}
    try:
        # 1. 监控告警趋势
        monitor_rows = session.execute(text("""
            SELECT DATE(triggered_at) as date, COUNT(*) as count
            FROM monitor_alert_logs
            WHERE DATE(triggered_at) BETWEEN :start AND :end
            GROUP BY DATE(triggered_at) ORDER BY date
        """), params).fetchall()

        # 2. 定时任务趋势
        cron_rows = session.execute(text("""
            SELECT DATE(started_at) as date,
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as success,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM cron_job_runs
            WHERE DATE(started_at) BETWEEN :start AND :end
            GROUP BY DATE(started_at) ORDER BY date
        """), params).fetchall()

        # 3. 订单趋势（拆分模拟/实盘）
        order_rows = session.execute(text("""
            SELECT DATE(o.order_time) as date,
                   SUM(CASE WHEN s.trade_mode = 0 THEN 1 ELSE 0 END) as sim,
                   SUM(CASE WHEN s.trade_mode = 1 THEN 1 ELSE 0 END) as live
            FROM orders o
            JOIN strategys s ON o.strategy_id = s.strategy_id
            WHERE DATE(o.order_time) BETWEEN :start AND :end
            GROUP BY DATE(o.order_time) ORDER BY date
        """), params).fetchall()

        # 4. 成交趋势（拆分模拟/实盘）
        trade_rows = session.execute(text("""
            SELECT DATE(t.traded_time) as date,
                   SUM(CASE WHEN s.trade_mode = 0 THEN 1 ELSE 0 END) as sim_count,
                   SUM(CASE WHEN s.trade_mode = 1 THEN 1 ELSE 0 END) as live_count,
                   COALESCE(SUM(CASE WHEN s.trade_mode = 0 THEN t.traded_amount ELSE 0 END), 0) as sim_amount,
                   COALESCE(SUM(CASE WHEN s.trade_mode = 1 THEN t.traded_amount ELSE 0 END), 0) as live_amount
            FROM trades t
            JOIN strategys s ON t.strategy_id = s.strategy_id
            WHERE DATE(t.traded_time) BETWEEN :start AND :end
            GROUP BY DATE(t.traded_time) ORDER BY date
        """), params).fetchall()

        # 5. 资产趋势（拆分模拟/实盘）
        asset_rows = session.execute(text("""
            SELECT DATE(d.snapshot_date) as date,
                   SUM(CASE WHEN s.trade_mode = 0 THEN d.total_assets ELSE 0 END) as sim_total,
                   SUM(CASE WHEN s.trade_mode = 1 THEN d.total_assets ELSE 0 END) as live_total,
                   SUM(CASE WHEN s.trade_mode = 0 THEN d.position_value ELSE 0 END) as sim_market,
                   SUM(CASE WHEN s.trade_mode = 1 THEN d.position_value ELSE 0 END) as live_market
            FROM daily_account_snapshot d
            JOIN strategys s ON d.strategy_id = s.strategy_id
            WHERE DATE(d.snapshot_date) BETWEEN :start AND :end
            GROUP BY DATE(d.snapshot_date) ORDER BY date
        """), params).fetchall()

        # 6. Agent 会话趋势（新增多维度）
        agent_rows = session.execute(text("""
            SELECT DATE(created_at) as date,
                   COUNT(*) as new_sessions,
                   COALESCE(SUM(user_message_count), 0) as user_messages,
                   COALESCE(SUM(total_context_chars), 0) as context_chars
            FROM agent_sessions
            WHERE DATE(created_at) BETWEEN :start AND :end
            GROUP BY DATE(created_at) ORDER BY date
        """), params).fetchall()

        # 7. 用户注册趋势
        user_rows = session.execute(text("""
            SELECT DATE(created_at) as date, COUNT(*) as new_users
            FROM users
            WHERE DATE(created_at) BETWEEN :start AND :end
            GROUP BY DATE(created_at) ORDER BY date
        """), params).fetchall()

        # 8. 策略创建趋势（拆分模拟/实盘）
        strategy_rows = session.execute(text("""
            SELECT DATE(created_at) as date,
                   SUM(CASE WHEN trade_mode = 0 THEN 1 ELSE 0 END) as sim,
                   SUM(CASE WHEN trade_mode = 1 THEN 1 ELSE 0 END) as live
            FROM strategys
            WHERE DATE(created_at) BETWEEN :start AND :end AND is_deleted = 0
            GROUP BY DATE(created_at) ORDER BY date
        """), params).fetchall()

        # 9. 反馈趋势
        fb_rows = session.execute(text("""
            SELECT DATE(created_at) as date,
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                   SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) as resolved
            FROM feedbacks
            WHERE DATE(created_at) BETWEEN :start AND :end
            GROUP BY DATE(created_at) ORDER BY date
        """), params).fetchall()

        def _d(v):
            return str(v) if v else ""

        return TrendsResponse(
            monitor_alerts=[{"date": _d(r.date), "count": int(r.count)} for r in monitor_rows],
            cron_jobs=[{"date": _d(r.date), "total": int(r.total), "success": int(r.success or 0), "failed": int(r.failed or 0)} for r in cron_rows],
            orders=[{"date": _d(r.date), "sim": int(r.sim or 0), "live": int(r.live or 0)} for r in order_rows],
            trades=[{"date": _d(r.date), "sim_count": int(r.sim_count or 0), "live_count": int(r.live_count or 0), "sim_amount": float(r.sim_amount or 0), "live_amount": float(r.live_amount or 0)} for r in trade_rows],
            assets=[{"date": _d(r.date), "sim_total": float(r.sim_total or 0), "live_total": float(r.live_total or 0), "sim_market": float(r.sim_market or 0), "live_market": float(r.live_market or 0)} for r in asset_rows],
            agent_sessions=[{"date": _d(r.date), "new_sessions": int(r.new_sessions or 0), "user_messages": int(r.user_messages or 0), "context_chars": int(r.context_chars or 0)} for r in agent_rows],
            user_registrations=[{"date": _d(r.date), "new_users": int(r.new_users)} for r in user_rows],
            strategy_creations=[{"date": _d(r.date), "sim": int(r.sim or 0), "live": int(r.live or 0)} for r in strategy_rows],
            feedbacks=[{"date": _d(r.date), "total": int(r.total), "pending": int(r.pending or 0), "resolved": int(r.resolved or 0)} for r in fb_rows],
        )
    except Exception:
        logger.exception("查询趋势数据失败")
        return TrendsResponse(
            monitor_alerts=[], cron_jobs=[], orders=[], trades=[],
            assets=[], agent_sessions=[], user_registrations=[],
            strategy_creations=[], feedbacks=[],
        )
    finally:
        session.close()
