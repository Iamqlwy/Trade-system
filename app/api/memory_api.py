"""记忆系统 REST API

用户画像 CRUD + 交互记忆 CRUD。
所有端点需要 Bearer token 认证，user_id 从 token 中提取。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from ..auth.dependencies import require_api_token
from ..utils.sanitize import sanitize_str, sanitize_text_field

logger = logging.getLogger(__name__)

memory_api_router = APIRouter(prefix="/api/memory", tags=["memory"])

# 记忆分类白名单
_VALID_CATEGORIES = {"交易习惯", "风险偏好", "关注板块", "关注个股", "其他", "general"}

# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class ProfileUpdateRequest(BaseModel):
    trading_style: Optional[str] = Field(None, max_length=200)
    risk_level: Optional[str] = Field(None, max_length=50)
    focus_sectors: Optional[list[str]] = None
    focus_stocks: Optional[list[str]] = None
    capital_range: Optional[str] = Field(None, max_length=200)
    indicators: Optional[list[str]] = None

    @field_validator("trading_style")
    @classmethod
    def _sanitize_trading_style(cls, v: str | None) -> str | None:
        return sanitize_str(v, max_length=200) if v is not None else None

    @field_validator("risk_level")
    @classmethod
    def _sanitize_risk_level(cls, v: str | None) -> str | None:
        return sanitize_str(v, max_length=50) if v is not None else None

    @field_validator("focus_sectors")
    @classmethod
    def _validate_focus_sectors(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if len(v) > 10:
            raise ValueError("关注板块最多 10 项")
        return [sanitize_str(item, max_length=100) or item for item in v]

    @field_validator("focus_stocks")
    @classmethod
    def _validate_focus_stocks(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("关注个股最多 20 项")
        return [sanitize_str(item, max_length=20) or item for item in v]

    @field_validator("capital_range")
    @classmethod
    def _sanitize_capital_range(cls, v: str | None) -> str | None:
        return sanitize_str(v, max_length=200) if v is not None else None

    @field_validator("indicators")
    @classmethod
    def _validate_indicators(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("指标最多 20 项")
        return [sanitize_str(item, max_length=100) or item for item in v]


class MemoryCreateRequest(BaseModel):
    category: str = Field(..., max_length=50)
    content: str = Field(..., max_length=5000)

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: str) -> str:
        v = sanitize_str(v, max_length=50) or v
        if v not in _VALID_CATEGORIES:
            raise ValueError(f"无效分类: {v}，可选值: {', '.join(sorted(_VALID_CATEGORIES))}")
        return v

    @field_validator("content")
    @classmethod
    def _sanitize_content(cls, v: str) -> str:
        return sanitize_text_field(v, max_length=5000) or v


# ---------------------------------------------------------------------------
# 画像端点
# ---------------------------------------------------------------------------

@memory_api_router.get("/profile")
async def get_profile(user: dict = Depends(require_api_token)):
    """获取当前用户的交易画像"""
    from ..services.memory_service import memory_service

    profile = memory_service.get_profile(user["user_id"])
    return profile


@memory_api_router.put("/profile")
async def update_profile(
    body: ProfileUpdateRequest,
    user: dict = Depends(require_api_token),
):
    """更新当前用户的交易画像（部分更新）"""
    from ..services.memory_service import memory_service

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="没有可更新的字段")

    profile = memory_service.update_profile(user["user_id"], updates)
    return profile


# ---------------------------------------------------------------------------
# 记忆端点
# ---------------------------------------------------------------------------

@memory_api_router.get("/memories")
async def list_memories(
    category: Optional[str] = Query(None, description="按分类过滤"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_api_token),
):
    """获取当前用户的记忆列表"""
    from ..services.memory_service import memory_service

    memories = memory_service.get_memories(user["user_id"], category=category, limit=limit)
    return {"memories": memories}


@memory_api_router.post("/memories")
async def add_memory(
    body: MemoryCreateRequest,
    user: dict = Depends(require_api_token),
):
    """手动添加一条记忆"""
    from ..services.memory_service import memory_service

    try:
        result = memory_service.add_memory(
            user_id=user["user_id"],
            category=body.category,
            content=body.content,
            source="manual",
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@memory_api_router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: int,
    user: dict = Depends(require_api_token),
):
    """删除一条记忆"""
    from ..services.memory_service import memory_service

    ok = memory_service.remove_memory(user["user_id"], memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在或无权删除")
    return {"success": True}
