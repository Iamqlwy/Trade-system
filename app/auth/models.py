"""
SQLAlchemy models for user authentication.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, DECIMAL
from sqlalchemy.orm import relationship
from datetime import datetime

from ..store.models import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(10), default="trader", comment="admin / trader / viewer")
    created_at = Column(DateTime, default=datetime.now)

    # ── 个人资料 ─────────────────────────
    nickname = Column(String(50), nullable=True, comment="昵称")
    avatar_url = Column(String(500), nullable=True, comment="头像URL")
    email = Column(String(100), nullable=True, comment="邮箱")
    phone = Column(String(20), nullable=True, comment="手机号")
    bio = Column(Text, nullable=True, comment="投资经验/个人简介")
    investment_style = Column(String(50), nullable=True,
                              comment="投资风格: 价值投资/短线交易/量化对冲/趋势跟踪/其他")
    risk_level = Column(String(20), nullable=True,
                        comment="风险偏好: conservative/moderate/aggressive")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # ── 精细化权限 ─────────────────────────
    can_use_agent = Column(Boolean, default=True, comment="是否允许使用 Agent")
    can_create_real = Column(Boolean, default=True, comment="是否允许创建实盘策略")
    max_strategies = Column(Integer, default=10, comment="最大策略数量（-1=无限制, 0=不允许创建）")
    can_use_cron = Column(Boolean, default=True, comment="是否允许使用定时任务")
    can_use_monitor = Column(Boolean, default=True, comment="是否允许使用监控任务")

    # ── Relationships ─────────────────────
    strategies = relationship("Strategys", back_populates="owner",
                              primaryjoin="User.id == Strategys.owner_id")
    agent_sessions = relationship("AgentSessions", back_populates="user_rel",
                                  primaryjoin="User.id == AgentSessions.user_id")
    strategy_users = relationship("StrategyUser", back_populates="user_rel")
    tool_permissions = relationship("UserToolPermission", back_populates="user_rel")
    cron_jobs = relationship("CronJob", back_populates="user_rel")
    cron_job_runs = relationship("CronJobRun", back_populates="user_rel")
    sent_messages = relationship("Message", foreign_keys="Message.sender_id",
                                 back_populates="sender")
    received_messages = relationship("Message", foreign_keys="Message.recipient_id",
                                     back_populates="recipient")
    group_memberships = relationship("UserGroupMember", back_populates="user")


class StrategyUser(Base):
    __tablename__ = "strategy_users"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    strategy_id = Column(String(20), ForeignKey("strategys.strategy_id", ondelete="CASCADE"), primary_key=True)
    can_trade = Column(Boolean, default=False)

    user_rel = relationship("User", back_populates="strategy_users")
    strategy_rel = relationship("Strategys", foreign_keys=[strategy_id])


class UserToolPermission(Base):
    """工具权限 — opt-out 模型：无记录=默认启用，enabled=0 表示禁用"""
    __tablename__ = "user_tool_permissions"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tool_key = Column(String(32), primary_key=True)
    enabled = Column(Boolean, default=True)

    user_rel = relationship("User", back_populates="tool_permissions")


# ── 站内信（邮箱模式）───────────────────────────────

class Message(Base):
    """站内信 — 每条消息按收件人独立存储（类似邮件）"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
                       comment="发送者（NULL=系统）")
    recipient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
                          comment="收件人")
    title = Column(String(200), nullable=False, comment="消息标题")
    content = Column(Text, nullable=False, comment="消息正文")
    is_read = Column(Boolean, default=False, comment="是否已读")
    read_at = Column(DateTime, nullable=True, comment="阅读时间")
    is_deleted = Column(Boolean, default=False, comment="收件人是否删除（软删除）")
    created_at = Column(DateTime, default=datetime.now)

    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")
    recipient = relationship("User", foreign_keys=[recipient_id], back_populates="received_messages")


# ── 用户组 ──────────────────────────────────────

class UserGroup(Base):
    __tablename__ = "user_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="组名称")
    description = Column(String(500), default="", comment="组描述")
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
                        comment="创建者")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    creator = relationship("User", foreign_keys=[created_by])
    members = relationship("UserGroupMember", back_populates="group",
                           cascade="all, delete-orphan")
    permissions = relationship("UserGroupPermission", back_populates="group", uselist=False,
                               cascade="all, delete-orphan")
    strategy_permissions = relationship("UserGroupStrategyPermission", back_populates="group",
                                        cascade="all, delete-orphan")
    tool_permissions = relationship("UserGroupToolPermission", back_populates="group",
                                    cascade="all, delete-orphan")


class UserGroupMember(Base):
    __tablename__ = "user_group_members"

    group_id = Column(Integer, ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    added_at = Column(DateTime, default=datetime.now)

    group = relationship("UserGroup", back_populates="members")
    user = relationship("User", back_populates="group_memberships")


class UserGroupPermission(Base):
    __tablename__ = "user_group_permissions"

    group_id = Column(Integer, ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True)
    can_use_agent = Column(Boolean, default=True, comment="允许使用 Agent")
    can_create_real = Column(Boolean, default=True, comment="允许创建实盘策略")
    max_strategies = Column(Integer, default=10, comment="最大策略数量（-1=无限制）")
    can_use_cron = Column(Boolean, default=True, comment="允许使用定时任务")
    can_use_monitor = Column(Boolean, default=True, comment="允许使用监控任务")

    group = relationship("UserGroup", back_populates="permissions")


class UserGroupStrategyPermission(Base):
    __tablename__ = "user_group_strategy_permissions"

    group_id = Column(Integer, ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True)
    strategy_id = Column(String(20), ForeignKey("strategys.strategy_id", ondelete="CASCADE"),
                         primary_key=True)
    can_trade = Column(Boolean, default=False)

    group = relationship("UserGroup", back_populates="strategy_permissions")


class UserGroupToolPermission(Base):
    __tablename__ = "user_group_tool_permissions"

    group_id = Column(Integer, ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True)
    tool_key = Column(String(32), primary_key=True)
    enabled = Column(Boolean, default=True)

    group = relationship("UserGroup", back_populates="tool_permissions")


# ── API Token（外部接入凭证）───────────────────────────────

class ApiToken(Base):
    """
    用户 API Token — 外部脚本/程序通过此 Token 接入平台。

    安全规则:
      - 数据库中只存 SHA-256 哈希，明文仅在创建时返回一次
      - Token 前缀 qt_ 便于日志识别和轮换
      - scope_type 控制策略访问范围，permissions 控制操作类型
      - is_active=False 可紧急吊销
    """
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
                     index=True, comment="归属用户")
    token_hash = Column(String(128), unique=True, nullable=False,
                        comment="SHA-256(原始 token)")
    name = Column(String(100), nullable=False, default="",
                  comment="用户自定义名称")

    # 策略范围
    scope_type = Column(String(20), nullable=False, default="all",
                        comment="策略范围: all / listed / owned")
    scope_strategies = Column(JSON, default=list,
                              comment="scope_type='listed' 时的策略 ID 白名单")

    # 操作范围
    permissions = Column(JSON, nullable=False, default=list,
                         comment='允许的操作: ["read","trade","modify"]')

    # 生命周期
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    expires_at = Column(DateTime, nullable=True, comment="NULL=永不过期")
    last_used_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    # 限速
    rate_limit = Column(Integer, nullable=False, default=60,
                        comment="每分钟最大请求数（0=不限）")

    # 下单确认
    require_confirm = Column(Boolean, nullable=False, default=False,
                             comment="通过此 Token 下单是否需要用户在前端确认")

    user_rel = relationship("User", foreign_keys=[user_id],
                            primaryjoin="ApiToken.user_id == User.id")


# ── 下单确认（API Token 订单审批）───────────────────────────────

class OrderConfirmation(Base):
    """
    API Token 下单确认记录。

    当 API Token 开启了 require_confirm，下单请求不会立即执行，
    而是创建此记录等待用户在前端确认/拒绝。
    """
    __tablename__ = "order_confirmations"

    id = Column(String(32), primary_key=True, comment="uuid")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True, comment="token 拥有者")
    api_token_id = Column(Integer, ForeignKey("api_tokens.id", ondelete="SET NULL"),
                          nullable=True, comment="来源 API Token")
    api_token_name = Column(String(100), default="", comment="冗余 token 名称，方便展示")

    # 订单参数快照
    strategy_id = Column(String(20), nullable=False)
    stock_code = Column(String(20), nullable=False)
    order_type = Column(Integer, nullable=False, comment="23=buy, 24=sell")
    price_type = Column(Integer, default=11)
    price = Column(DECIMAL(16, 4), nullable=False)
    order_volume = Column(Integer, nullable=False)
    order_remark = Column(Text, default="")

    # 审批状态
    status = Column(String(20), nullable=False, default="pending",
                    comment="pending / approved / rejected / expired")
    result_order_id = Column(String(31), default="",
                             comment="审批通过后生成的 order_id")
    reject_reason = Column(String(200), nullable=True, comment="拒绝原因")

    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False, comment="超时自动拒绝")
    decided_at = Column(DateTime, nullable=True, comment="用户操作时间")
