"""
量化交易系统 - API 请求模型 (Pydantic)
"""
import re
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator

from ..utils.sanitize import sanitize_str, sanitize_text_field


class CreateStrategyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="策略名称")
    description: str = Field("", max_length=2000, description="策略描述（短）")
    detail: str = Field("", max_length=50000, description="策略详情（长文本）")
    trade_mode: int = Field(0, description="0=模拟, 1=实盘")
    initial_cash: Decimal = Field(
        Decimal("1000000"),
        gt=0,
        le=Decimal("1000000000"),  # 上限 10 亿
        description="初始资金",
    )

    @field_validator("trade_mode")
    @classmethod
    def validate_trade_mode(cls, v: int) -> int:
        if v not in (0, 1):
            raise ValueError("trade_mode 必须为 0（模拟）或 1（实盘）")
        return v

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str) -> str:
        return sanitize_str(v, max_length=64) or ""

    @field_validator("description")
    @classmethod
    def _sanitize_description(cls, v: str) -> str:
        return sanitize_text_field(v, max_length=2000) or ""

    @field_validator("detail")
    @classmethod
    def _sanitize_detail(cls, v: str) -> str:
        return sanitize_text_field(v, max_length=50000) or ""


class UpdateStrategyRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64, description="策略名称")
    description: str | None = Field(None, max_length=2000, description="策略描述")
    detail: str | None = Field(None, max_length=50000, description="策略详情")

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str | None) -> str | None:
        return sanitize_str(v, max_length=64) if v is not None else None

    @field_validator("description")
    @classmethod
    def _sanitize_description(cls, v: str | None) -> str | None:
        return sanitize_text_field(v, max_length=2000) if v is not None else None

    @field_validator("detail")
    @classmethod
    def _sanitize_detail(cls, v: str | None) -> str | None:
        return sanitize_text_field(v, max_length=50000) if v is not None else None


# Pydantic v2 将 _前缀 类变量视为 ModelPrivateAttr, 必须放在类外
_STOCK_CODE_RE = re.compile(r"^\d{6}(\.(SH|SZ))?$", re.IGNORECASE)


class OrderRequest(BaseModel):
    stock_code: str = Field(..., min_length=1, max_length=12, description="股票代码")
    order_type: int = Field(..., description="23=买入, 24=卖出, 27=信用买入, 28=信用卖出")
    price: Decimal = Field(
        ...,
        gt=0,
        le=Decimal("999999.99"),  # A 股价格上限
        description="委托价格",
    )
    order_volume: int = Field(
        ...,
        gt=0,
        le=1000000,  # 单笔上限 100 万股
        description="委托数量（股）",
    )
    price_type: int = Field(11, description="5=最新价, 11=限价")
    order_remark: str = Field("", max_length=200, description="订单备注")

    @field_validator("order_remark")
    @classmethod
    def _sanitize_remark(cls, v: str) -> str:
        return sanitize_str(v, max_length=200) or ""

    @field_validator("stock_code")
    @classmethod
    def validate_stock_code(cls, v: str) -> str:
        v = v.strip().upper()
        if not _STOCK_CODE_RE.match(v):
            raise ValueError(
                f"股票代码格式错误: {v}，应为 6 位数字，可选后缀 .SH/.SZ"
            )
        return v

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: int) -> int:
        if v not in (23, 24, 27, 28):
            raise ValueError("order_type 必须为 23/24/27/28")
        return v

    @field_validator("price_type")
    @classmethod
    def validate_price_type(cls, v: int) -> int:
        if v not in (5, 11):
            raise ValueError("price_type 必须为 5（最新价）或 11（限价）")
        return v


class CancelOrderRequest(BaseModel):
    pass  # order_id 在 URL 路径中


class UpdateRemarkRequest(BaseModel):
    remark: str = Field("", max_length=200, description="持仓备注")

    @field_validator("remark")
    @classmethod
    def _sanitize_remark(cls, v: str) -> str:
        return sanitize_str(v, max_length=200) or ""


# ── 站内信 ────────────────────────────────────

class SendMessageRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=10000)
    recipient_ids: list[int] = Field(default_factory=list,
                                     description="收件人ID列表，空=全部用户")

    @field_validator("title")
    @classmethod
    def _sanitize_title(cls, v: str) -> str:
        return sanitize_str(v, max_length=200) or v

    @field_validator("content")
    @classmethod
    def _sanitize_content(cls, v: str) -> str:
        return sanitize_text_field(v, max_length=10000) or v


class BatchDeleteMessagesRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, description="要删除的消息ID列表")


class MarkReadRequest(BaseModel):
    is_read: bool = Field(True, description="标记已读/未读")


# ── 用户组 ────────────────────────────────────

class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str) -> str:
        return sanitize_str(v, max_length=100) or v

    @field_validator("description")
    @classmethod
    def _sanitize_description(cls, v: str) -> str:
        return sanitize_text_field(v, max_length=500) or ""


class UpdateGroupRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str | None) -> str | None:
        return sanitize_str(v, max_length=100) if v is not None else None

    @field_validator("description")
    @classmethod
    def _sanitize_description(cls, v: str | None) -> str | None:
        return sanitize_text_field(v, max_length=500) if v is not None else None


class AddGroupMembersRequest(BaseModel):
    user_ids: list[int] = Field(..., min_length=1)


class SetGroupPermissionsRequest(BaseModel):
    can_use_agent: bool | None = None
    can_create_real: bool | None = None
    max_strategies: int | None = None
    can_use_cron: bool | None = None
    can_use_monitor: bool | None = None


class SetGroupStrategyPermissionRequest(BaseModel):
    strategy_id: str
    can_trade: bool = False


class SetGroupToolPermissionRequest(BaseModel):
    tool_key: str
    enabled: bool
