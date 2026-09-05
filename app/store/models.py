"""
量化交易系统 - SQLAlchemy ORM 模型

匹配 build_database.sql 中的全部表定义。
所有类型、长度、精度与 SQL DDL 保持一致。
"""
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, DECIMAL, DateTime, Date, Boolean,
    PrimaryKeyConstraint, ForeignKey, UniqueConstraint,
    Text, SmallInteger, JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Strategys(Base):
    __tablename__ = "strategys"

    strategy_id = Column(String(20), primary_key=True)
    name = Column(String(50), default="")
    description = Column(Text, default="")
    detail = Column(Text, default="")
    trade_mode = Column(SmallInteger, default=0, comment="0=模拟, 1=实盘")
    initial_cash = Column(DECIMAL(16, 4), default=0)
    available_cash = Column(DECIMAL(16, 4), default=0)
    frozen_cash = Column(DECIMAL(16, 4), default=0)
    is_deleted = Column(SmallInteger, default=0, comment="0=正常, 1=已删除")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="策略所有者")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # ── Relationships ─────────────────────
    owner = relationship("User", back_populates="strategies", foreign_keys=[owner_id])
    positions_rel = relationship("Positions", back_populates="strategy_rel",
                                 primaryjoin="Strategys.strategy_id == Positions.strategy_id")
    lots_rel = relationship("Lots", back_populates="strategy_rel",
                            primaryjoin="Strategys.strategy_id == Lots.strategy_id")
    orders_rel = relationship("Orders", back_populates="strategy_rel",
                              primaryjoin="Strategys.strategy_id == Orders.strategy_id")
    trades_rel = relationship("Trades", back_populates="strategy_rel",
                              primaryjoin="Strategys.strategy_id == Trades.strategy_id")
    settlements_rel = relationship("Settlements", back_populates="strategy_rel",
                                   primaryjoin="Strategys.strategy_id == Settlements.strategy_id")
    day_t_records_rel = relationship("DayTRecords", back_populates="strategy_rel",
                                     primaryjoin="Strategys.strategy_id == DayTRecords.strategy_id")
    commission_config_rel = relationship("CommissionConfigs", uselist=False,
                                          back_populates="strategy_rel",
                                          primaryjoin="Strategys.strategy_id == CommissionConfigs.strategy_id")


class Positions(Base):
    __tablename__ = "positions"

    strategy_id = Column(String(20), ForeignKey("strategys.strategy_id"), primary_key=True)
    stock_code = Column(String(20), primary_key=True)
    today = Column(Date, primary_key=True)
    total = Column(Integer, default=0)
    available = Column(Integer, default=0)
    frozen = Column(Integer, default=0)
    unavailable = Column(Integer, default=0)
    avg_price = Column(DECIMAL(16, 4), default=0)
    remark = Column(Text, default="")
    first_buy_time = Column(DateTime, nullable=True)
    sold_out_time = Column(DateTime, nullable=True)

    strategy_rel = relationship("Strategys", back_populates="positions_rel")


class Lots(Base):
    __tablename__ = "lots"

    strategy_id = Column(String(20), ForeignKey("strategys.strategy_id"), primary_key=True)
    stock_code = Column(String(20), primary_key=True)
    open_time = Column(DateTime, primary_key=True)
    lot_size = Column(Integer, default=0)
    open_price = Column(DECIMAL(16, 4), default=0)

    strategy_rel = relationship("Strategys", back_populates="lots_rel")


class Orders(Base):
    __tablename__ = "orders"

    client_order_id = Column(String(31), primary_key=True, comment="strategy_id_seq")
    strategy_id = Column(String(20), ForeignKey("strategys.strategy_id"), nullable=False)
    account_type = Column(Integer, default=0)
    account_id = Column(String(20), default="")
    stock_code = Column(String(20), default="")
    broker_order_id = Column(String(30), default="")
    order_sysid = Column(String(30), default="")
    order_time = Column(DateTime, default=datetime.now)
    order_type = Column(Integer, default=23)
    price_type = Column(Integer, default=11)
    price = Column(DECIMAL(16, 4), default=0)
    order_volume = Column(Integer, default=0)
    traded_volume = Column(Integer, default=0)
    traded_price = Column(DECIMAL(16, 4), default=0)
    traded_amount = Column(DECIMAL(16, 4), default=0)
    commission = Column(DECIMAL(16, 4), default=0)
    order_status = Column(Integer, default=48)
    status_msg = Column(Text, default="")
    order_remark = Column(Text, default="")

    strategy_rel = relationship("Strategys", back_populates="orders_rel")


class Trades(Base):
    __tablename__ = "trades"

    traded_id = Column(String(30), primary_key=True)
    strategy_id = Column(String(20), ForeignKey("strategys.strategy_id"), nullable=False)
    client_order_id = Column(String(31), ForeignKey("orders.client_order_id"), default="")
    broker_order_id = Column(String(30), default="")
    order_sysid = Column(String(30), default="")
    account_type = Column(Integer, default=0)
    account_id = Column(String(20), default="")
    stock_code = Column(String(20), default="")
    order_type = Column(Integer, default=23)
    traded_time = Column(DateTime, default=datetime.now)
    traded_price = Column(DECIMAL(16, 4), default=0)
    traded_volume = Column(Integer, default=0)
    traded_amount = Column(DECIMAL(16, 4), default=0)
    order_remark = Column(Text, default="")

    strategy_rel = relationship("Strategys", back_populates="trades_rel")


class DailyAccountSnapshot(Base):
    __tablename__ = "daily_account_snapshot"

    strategy_id = Column(String(20), primary_key=True)
    snapshot_date = Column(Date, primary_key=True)
    total_assets = Column(DECIMAL(16, 4), default=0)
    available_cash = Column(DECIMAL(16, 4), default=0)
    frozen_cash = Column(DECIMAL(16, 4), default=0)
    position_value = Column(DECIMAL(16, 4), default=0)
    position_cost = Column(DECIMAL(16, 4), default=0)
    position_count = Column(Integer, default=0)
    order_count = Column(Integer, default=0)
    commission = Column(DECIMAL(16, 4), default=0)


class DayTRecords(Base):
    __tablename__ = "day_T_records"

    strategy_id = Column(String(20), ForeignKey("strategys.strategy_id"), primary_key=True)
    stock_code = Column(String(20), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    buy_volume = Column(Integer, default=0)
    buy_amount = Column(DECIMAL(16, 4), default=0)
    buy_count = Column(Integer, default=0)
    avg_buy_price = Column(DECIMAL(16, 4), default=0)
    sell_volume = Column(Integer, default=0)
    sell_amount = Column(DECIMAL(16, 4), default=0)
    sell_count = Column(Integer, default=0)
    avg_sell_price = Column(DECIMAL(16, 4), default=0)
    t_volume = Column(Integer, default=0)
    t_profit = Column(DECIMAL(16, 4), default=0)
    t_return_rate = Column(DECIMAL(10, 4), default=0)
    holding_change = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    strategy_rel = relationship("Strategys", back_populates="day_t_records_rel",
                                primaryjoin="Strategys.strategy_id == DayTRecords.strategy_id")


class Settlements(Base):
    __tablename__ = "settlements"

    strategy_id = Column(String(20), ForeignKey("strategys.strategy_id"), primary_key=True)
    stock_code = Column(String(20), primary_key=True)
    first_buy_time = Column(DateTime, primary_key=True)
    total_buy_volume = Column(Integer, default=0)
    total_buy_amount = Column(DECIMAL(16, 4), default=0)
    total_sell_volume = Column(Integer, default=0)
    total_sell_amount = Column(DECIMAL(16, 4), default=0)
    avg_cost_price = Column(DECIMAL(16, 4), default=0)
    realized_profit = Column(DECIMAL(16, 4), default=0)
    profit_rate = Column(DECIMAL(10, 4), default=0)
    is_closed = Column(Boolean, default=False)
    close_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    strategy_rel = relationship("Strategys", back_populates="settlements_rel")


class CommissionConfigs(Base):
    __tablename__ = "commission_configs"

    strategy_id = Column(String(20), ForeignKey("strategys.strategy_id"), primary_key=True)
    commission_rate = Column(DECIMAL(10, 8), default=0.000300)
    stamp_tax_rate = Column(DECIMAL(10, 8), default=0.000500)
    transfer_fee_rate = Column(DECIMAL(10, 8), default=0.000020)
    min_commission = Column(DECIMAL(10, 4), default=5.00)

    strategy_rel = relationship("Strategys", back_populates="commission_config_rel",
                                primaryjoin="Strategys.strategy_id == CommissionConfigs.strategy_id")


# ── Agent 会话 ──────────────────────────────────

class AgentSessions(Base):
    """Agent 会话记录 — 按用户隔离"""
    __tablename__ = "agent_sessions"

    id = Column(String(32), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), default="")
    summary = Column(Text, default="")
    agent_type = Column(String(20), default="simple", comment="simple/researcher")
    message_count = Column(Integer, default=0)
    user_message_count = Column(Integer, default=0, comment="用户消息数量")
    total_context_chars = Column(Integer, default=0, comment="会话上下文总字符数")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user_rel = relationship("User", back_populates="agent_sessions",
                            primaryjoin="AgentSessions.user_id == User.id")# ── Cron 定时任务 ──────────────────────────────────

class CronJob(Base):
    """定时任务定义 — 按用户隔离"""
    __tablename__ = "cron_jobs"

    id = Column(String(32), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    schedule = Column(String(100), nullable=False)
    schedule_type = Column(String(20), nullable=False, default="interval", comment="cron/interval/oneshot")
    prompt = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user_rel = relationship("User", back_populates="cron_jobs",
                            primaryjoin="CronJob.user_id == User.id")
    runs_rel = relationship("CronJobRun", back_populates="job_rel",
                            primaryjoin="CronJob.id == CronJobRun.job_id",
                            cascade="all, delete-orphan")


class CronJobRun(Base):
    """Timer job execution record"""
    __tablename__ = "cron_job_runs"

    id = Column(String(32), primary_key=True)
    job_id = Column(String(32), ForeignKey("cron_jobs.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    context_file = Column(String(500), nullable=True, comment="full conversation context .jsonl file path")
    status = Column(String(20), nullable=False, default="pending", comment="pending/running/completed/failed")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    output_summary = Column(Text, nullable=True, comment="first 500 characters summary")
    output_file = Column(String(500), nullable=True, comment="full output .md file path")
    error_message = Column(Text, nullable=True)

    job_rel = relationship("CronJob", back_populates="runs_rel",
                           primaryjoin="CronJobRun.job_id == CronJob.id")
    user_rel = relationship("User",
                            primaryjoin="CronJobRun.user_id == User.id")


# ── 监控元数据 ──────────────────────────────────

class MonitorRecord(Base):
    """监控配置 — 全部元数据存 DB，脚本保留在 agent 工作区"""
    __tablename__ = "monitor_records"

    monitor_id = Column(String(20), primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
                      comment="创建者用户ID")
    session_id = Column(String(64), nullable=False, default="",
                        comment="agent 工作区 session_id（定位脚本位置）")
    monitor_name = Column(String(100), nullable=False, default="")
    description = Column(Text, default="")
    stock_codes = Column(JSON, default=list, comment="直接指定的股票代码列表")
    strategy_ids = Column(JSON, default=list, comment="策略ID列表（动态获取持仓）")
    interval = Column(String(10), nullable=False, default="30s")
    trigger_mode = Column(String(20), nullable=False, default="periodic",
                          comment="periodic/manual")
    enabled = Column(Boolean, nullable=False, default=True)
    cooldown_seconds = Column(Integer, nullable=False, default=300)
    script_metadata = Column(JSON, nullable=False, default=dict,
                             comment="AI生成的脚本元数据: {name, description, version, has_stock_param, parameters}")
    params = Column(JSON, nullable=False, default=dict,
                    comment="用户配置的参数值: {param_name: value}")
    script_path = Column(String(200), nullable=False, default="check.py",
                         comment="工作区内脚本相对路径")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    owner_rel = relationship("User", primaryjoin="MonitorRecord.owner_id == User.id")


# ── 监控触发记录 ──────────────────────────────

class MonitorAlertLog(Base):
    __tablename__ = "monitor_alert_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    monitor_id = Column(String(20), nullable=False, index=True, comment="监控ID")
    monitor_name = Column(String(100), nullable=False, default="", comment="监控名称")
    stock_code = Column(String(20), nullable=False, index=True, comment="股票代码")
    message = Column(Text, default="", comment="触发消息")
    data = Column(JSON, nullable=True, comment="监控脚本返回的附加数据")
    triggered_at = Column(DateTime, nullable=False, index=True, comment="触发时间")


# ── 用户反馈 ─────────────────────────────────────

class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    type = Column(String(20), default="other", comment="类型: bug/feature/question/other")
    title = Column(String(200), nullable=False, comment="标题")
    content = Column(Text, nullable=False, comment="详细内容")
    status = Column(String(20), default="pending", comment="状态: pending/in_progress/resolved/closed")
    admin_reply = Column(Text, nullable=True, comment="管理员回复")
    replied_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="回复人ID")
    replied_at = Column(DateTime, nullable=True, comment="回复时间")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user_rel = relationship(
        "User", foreign_keys=[user_id],
        primaryjoin="Feedback.user_id == User.id",
    )
    replier_rel = relationship(
        "User", foreign_keys=[replied_by],
        primaryjoin="Feedback.replied_by == User.id",
    )


# ── 自选股 ─────────────────────────────────────

class WatchlistGroup(Base):
    __tablename__ = "watchlist_groups"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    stocks = relationship(
        "WatchlistStock",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="WatchlistStock.added_at",
    )
    owner_rel = relationship("User", foreign_keys=[user_id])


class WatchlistStock(Base):
    __tablename__ = "watchlist_stocks"
    __table_args__ = (
        UniqueConstraint("group_id", "ts_code", name="uq_group_stock"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("watchlist_groups.id", ondelete="CASCADE"), nullable=False)
    ts_code = Column(String(20), nullable=False)
    symbol = Column(String(10), nullable=False)
    name = Column(String(50), nullable=False)
    added_at = Column(DateTime, default=datetime.now)

    group = relationship("WatchlistGroup", back_populates="stocks")
