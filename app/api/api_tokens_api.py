"""
API Token 管理端点

用户通过 Token 接入平台，进行策略查看和交易操作。
Token 创建时返回明文一次，之后只能看到元数据。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from ..auth.dependencies import require_api_token
from ..auth.models import ApiToken
from ..auth.security import generate_api_token, hash_api_token
from ..dependencies import repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/api-tokens", tags=["api-tokens"])


def _session():
    return repository.SessionLocal()


# ── 请求/响应模型 ─────────────────────────────────

VALID_SCOPE_TYPES = {"all", "listed"}


class CreateApiTokenRequest(BaseModel):
    name: str = ""
    scope_type: str = "all"
    scope_strategies: list[str] = []
    expires_days: Optional[int] = None
    rate_limit: int = 60
    require_confirm: bool = False

    @field_validator("scope_type")
    @classmethod
    def validate_scope_type(cls, v: str) -> str:
        if v not in VALID_SCOPE_TYPES:
            raise ValueError(f"scope_type 必须为 {VALID_SCOPE_TYPES} 之一")
        return v

    @field_validator("rate_limit")
    @classmethod
    def validate_rate_limit(cls, v: int) -> int:
        if v < 0:
            raise ValueError("rate_limit 不能为负数")
        return v


class ApiTokenResponse(BaseModel):
    id: int
    name: str
    scope_type: str
    scope_strategies: list[str]
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool
    rate_limit: int
    require_confirm: bool
    created_at: datetime


class ApiTokenCreatedResponse(ApiTokenResponse):
    """创建时返回，包含一次性明文 token"""
    token: str


class UpdateApiTokenRequest(BaseModel):
    name: Optional[str] = None
    scope_type: Optional[str] = None
    scope_strategies: Optional[list[str]] = None
    rate_limit: Optional[int] = None
    is_active: Optional[bool] = None
    require_confirm: Optional[bool] = None

    @field_validator("scope_type")
    @classmethod
    def validate_scope_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_SCOPE_TYPES:
            raise ValueError(f"scope_type 必须为 {VALID_SCOPE_TYPES} 之一")
        return v


# ── 端点 ─────────────────────────────────────────

@router.post("", response_model=ApiTokenCreatedResponse, status_code=201)
async def create_api_token(
    req: CreateApiTokenRequest,
    _user: dict = Depends(require_api_token),
):
    """
    创建 API Token。

    ⚠️ token 明文仅在创建时返回一次，之后无法再查看。
    请妥善保存。API Token 仅限操作自己创建的策略。
    """
    if req.scope_type == "listed" and not req.scope_strategies:
        raise HTTPException(400, "选择「指定策略」时必须选择至少一个策略")

    raw_token = generate_api_token()
    token_hash = hash_api_token(raw_token)

    expires_at = None
    if req.expires_days is not None:
        if req.expires_days <= 0:
            raise HTTPException(400, "expires_days 必须为正整数")
        expires_at = datetime.now(timezone.utc) + timedelta(days=req.expires_days)

    # 权限固定为 read + trade（查看持仓 + 交易）
    permissions = ["read", "trade"]

    session = _session()
    try:
        api_token = ApiToken(
            user_id=_user["user_id"],
            token_hash=token_hash,
            name=req.name,
            scope_type=req.scope_type,
            scope_strategies=req.scope_strategies,
            permissions=permissions,
            expires_at=expires_at,
            rate_limit=req.rate_limit,
            require_confirm=req.require_confirm,
        )
        session.add(api_token)
        session.commit()
        session.refresh(api_token)

        logger.info(
            "创建 API Token: id=%d user=%s name=%s",
            api_token.id, _user["sub"], req.name,
        )

        return ApiTokenCreatedResponse(
            id=api_token.id,
            token=raw_token,
            name=api_token.name,
            scope_type=api_token.scope_type,
            scope_strategies=api_token.scope_strategies or [],
            expires_at=api_token.expires_at,
            last_used_at=api_token.last_used_at,
            is_active=api_token.is_active,
            rate_limit=api_token.rate_limit,
            require_confirm=api_token.require_confirm,
            created_at=api_token.created_at,
        )
    except Exception:
        session.rollback()
        logger.exception("创建 API Token 失败")
        raise HTTPException(500, "创建失败")
    finally:
        session.close()


@router.get("", response_model=list[ApiTokenResponse])
async def list_api_tokens(_user: dict = Depends(require_api_token)):
    """列出当前用户的全部 API Token（不返回明文）。"""
    session = _session()
    try:
        tokens = session.query(ApiToken).filter_by(
            user_id=_user["user_id"],
        ).order_by(ApiToken.created_at.desc()).all()

        return [
            ApiTokenResponse(
                id=t.id,
                name=t.name,
                scope_type=t.scope_type,
                scope_strategies=t.scope_strategies or [],
                expires_at=t.expires_at,
                last_used_at=t.last_used_at,
                is_active=t.is_active,
                rate_limit=t.rate_limit,
                require_confirm=t.require_confirm,
                created_at=t.created_at,
            )
            for t in tokens
        ]
    finally:
        session.close()


@router.put("/{token_id}", response_model=ApiTokenResponse)
async def update_api_token(
    token_id: int,
    req: UpdateApiTokenRequest,
    _user: dict = Depends(require_api_token),
):
    """更新 API Token 的 scope / rate_limit / is_active。"""
    session = _session()
    try:
        api_token = session.query(ApiToken).filter_by(
            id=token_id, user_id=_user["user_id"],
        ).first()
        if not api_token:
            raise HTTPException(404, "Token 不存在")

        if req.name is not None:
            api_token.name = req.name
        if req.scope_type is not None:
            api_token.scope_type = req.scope_type
        if req.scope_strategies is not None:
            api_token.scope_strategies = req.scope_strategies
        if req.rate_limit is not None:
            if req.rate_limit < 0:
                raise HTTPException(400, "rate_limit 不能为负数")
            api_token.rate_limit = req.rate_limit
        if req.is_active is not None:
            api_token.is_active = req.is_active
        if req.require_confirm is not None:
            api_token.require_confirm = req.require_confirm

        session.commit()
        session.refresh(api_token)

        logger.info(
            "更新 API Token: id=%d user=%s",
            token_id, _user["sub"],
        )

        return ApiTokenResponse(
            id=api_token.id,
            name=api_token.name,
            scope_type=api_token.scope_type,
            scope_strategies=api_token.scope_strategies or [],
            expires_at=api_token.expires_at,
            last_used_at=api_token.last_used_at,
            is_active=api_token.is_active,
            rate_limit=api_token.rate_limit,
            require_confirm=api_token.require_confirm,
            created_at=api_token.created_at,
        )
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("更新 API Token 失败")
        raise HTTPException(500, "更新失败")
    finally:
        session.close()


@router.delete("/{token_id}")
async def delete_api_token(
    token_id: int,
    _user: dict = Depends(require_api_token),
):
    """撤销/删除 API Token。"""
    session = _session()
    try:
        api_token = session.query(ApiToken).filter_by(
            id=token_id, user_id=_user["user_id"],
        ).first()
        if not api_token:
            raise HTTPException(404, "Token 不存在")

        session.delete(api_token)
        session.commit()

        logger.info(
            "删除 API Token: id=%d user=%s",
            token_id, _user["sub"],
        )

        return {"success": True, "message": "Token 已删除"}
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("删除 API Token 失败")
        raise HTTPException(500, "删除失败")
    finally:
        session.close()
