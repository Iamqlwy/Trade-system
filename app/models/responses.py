"""
量化交易系统 - API 响应模型 (Pydantic)
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    strategies: int = 0
    version: str = "2.0.0"


class StrategySummary(BaseModel):
    strategy_id: str
    name: str
    description: str = ""
    detail: str = ""
    trade_mode: int = 0
    initial_cash: Decimal = Decimal("0")
    available_cash: Decimal = Decimal("0")
    frozen_cash: Decimal = Decimal("0")
    position_count: int = 0
    order_count_today: int = 0
    trade_count_today: int = 0


class PositionResponse(BaseModel):
    stock_code: str
    stock_name: str = ""
    total: int = 0
    available: int = 0
    frozen: int = 0
    unavailable: int = 0
    avg_price: Decimal = Decimal("0")
    remark: str = ""


class OrderResponse(BaseModel):
    order_id: str
    strategy_id: str
    stock_code: str
    stock_name: str = ""
    order_type: int
    price_type: int
    price: Decimal
    order_volume: int
    traded_volume: int = 0
    traded_price: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    status: int
    status_msg: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    order_remark: str = ""


class PlaceOrderResponse(BaseModel):
    success: bool
    order_id: str = ""
    message: str = ""
    available_cash: Decimal = Decimal("0")
    frozen_cash: Decimal = Decimal("0")


class CancelOrderResponse(BaseModel):
    success: bool
    order_id: str
    unfilled_volume: int = 0
    message: str = ""


class TradeResponse(BaseModel):
    traded_id: str
    strategy_id: str
    order_id: str
    stock_code: str
    stock_name: str = ""
    order_type: int
    traded_price: Decimal
    traded_volume: int
    traded_amount: Decimal
    traded_time: datetime
    order_remark: str = ""


class CreateStrategyResponse(BaseModel):
    success: bool
    strategy_id: str = ""
    message: str = ""


class DeleteStrategyResponse(BaseModel):
    success: bool
    strategy_id: str = ""
    message: str = ""


class StrategyUserResponse(BaseModel):
    """策略关联的用户"""
    user_id: int
    username: str
    role: str
    can_trade: bool
    is_owner: bool = False


class StrategyOverviewResponse(BaseModel):
    """策略综合概览：基本信息 + 关联用户 + 持仓"""
    strategy_id: str
    name: str
    description: str = ""
    trade_mode: int = 0
    initial_cash: Decimal = Decimal("0")
    available_cash: Decimal = Decimal("0")
    frozen_cash: Decimal = Decimal("0")
    total_assets: Decimal = Decimal("0")
    users: list[StrategyUserResponse] = []
    positions: list[PositionResponse] = []


# ── 站内信 ────────────────────────────────────

class MessageSummary(BaseModel):
    id: int
    title: str
    sender_name: str = ""
    is_read: bool = False
    created_at: str


class MessageDetail(BaseModel):
    id: int
    title: str
    content: str
    sender_name: str = ""
    is_read: bool = False
    read_at: str | None = None
    created_at: str


class UnreadCountResponse(BaseModel):
    count: int


class SentMessageResponse(BaseModel):
    id: int
    title: str
    content: str
    recipient_count: int = 0
    read_count: int = 0
    created_at: str


# ── 用户组 ────────────────────────────────────

class GroupResponse(BaseModel):
    id: int
    name: str
    description: str = ""
    member_count: int = 0
    created_at: str = ""


class GroupMemberItem(BaseModel):
    user_id: int
    username: str
    role: str


class GroupPermissionItem(BaseModel):
    can_use_agent: bool = True
    can_create_real: bool = True
    max_strategies: int = 10
    can_use_cron: bool = True
    can_use_monitor: bool = True


class GroupStrategyPermissionItem(BaseModel):
    strategy_id: str
    strategy_name: str = ""
    can_trade: bool = False


class GroupToolPermissionItem(BaseModel):
    tool_key: str
    enabled: bool = True


class GroupDetailResponse(BaseModel):
    id: int
    name: str
    description: str = ""
    members: list[GroupMemberItem] = []
    permissions: GroupPermissionItem | None = None
    strategy_permissions: list[GroupStrategyPermissionItem] = []
    tool_permissions: list[GroupToolPermissionItem] = []
