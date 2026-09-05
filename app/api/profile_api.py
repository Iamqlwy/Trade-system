"""
个人中心 API — 查看/更新个人资料、修改密码、投资统计。
"""
import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth.models import User
from ..auth.security import hash_password, verify_password
from ..auth.dependencies import require_api_token
from ..dependencies import repository
from ..store.models import Strategys, Settlements, Trades
from ..permissions.service import get_accessible_strategy_ids
from ..utils.sanitize import sanitize_str, sanitize_text_field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _session() -> Session:
    return repository.SessionLocal()


# ── Pydantic 模型 ──────────────────────────────────

class UserProfileResponse(BaseModel):
    id: int
    username: str
    nickname: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    phone: str | None = None
    bio: str | None = None
    investment_style: str | None = None
    risk_level: str | None = None
    role: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    phone: str | None = None
    bio: str | None = None
    investment_style: str | None = None
    risk_level: str | None = None

    @field_validator("nickname")
    @classmethod
    def _check_nickname(cls, v: str | None) -> str | None:
        if v is not None:
            v = sanitize_str(v, max_length=50)
            if v is not None and len(v) > 50:
                raise ValueError("昵称最多 50 个字符")
        return v

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
        if v is not None:
            v = sanitize_str(v, max_length=100)
            if v is not None and len(v) > 100:
                raise ValueError("邮箱最多 100 个字符")
        return v

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str | None) -> str | None:
        if v is not None:
            v = sanitize_str(v, max_length=20)
            if v is not None and len(v) > 20:
                raise ValueError("手机号最多 20 个字符")
        return v

    @field_validator("bio")
    @classmethod
    def _check_bio(cls, v: str | None) -> str | None:
        if v is not None:
            v = sanitize_text_field(v, max_length=2000)
            if v is not None and len(v) > 2000:
                raise ValueError("个人简介最多 2000 个字符")
        return v


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少 8 个字符")
        if len(v) > 128:
            raise ValueError("密码最多 128 个字符")
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("密码必须包含至少一个字母")
        if not re.search(r"[0-9]", v):
            raise ValueError("密码必须包含至少一个数字")
        return v


class PasswordChangeResponse(BaseModel):
    success: bool
    message: str


class BestItem(BaseModel):
    name: str
    value: float


class InvestmentStatsResponse(BaseModel):
    best_strategy: BestItem | None = None
    worst_stock: BestItem | None = None
    best_stock: BestItem | None = None
    total_trades: int = 0
    total_strategies: int = 0
    total_realized_pnl: float = 0.0
    account_age_days: int = 0


def _user_to_response(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "avatar_url": u.avatar_url,
        "email": u.email,
        "phone": u.phone,
        "bio": u.bio,
        "investment_style": u.investment_style,
        "risk_level": u.risk_level,
        "role": u.role,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }


# ── GET /api/profile/me ─────────────────────────────

@router.get("/me", response_model=UserProfileResponse)
async def get_profile(user: dict = Depends(require_api_token)):
    session = _session()
    try:
        db_user = session.query(User).filter_by(id=user["user_id"]).first()
        if not db_user:
            raise HTTPException(404, "用户不存在")
        return _user_to_response(db_user)
    finally:
        session.close()


# ── PUT /api/profile/me ─────────────────────────────

@router.put("/me", response_model=UserProfileResponse)
async def update_profile(req: UserProfileUpdate, user: dict = Depends(require_api_token)):
    session = _session()
    try:
        db_user = session.query(User).filter_by(id=user["user_id"]).first()
        if not db_user:
            raise HTTPException(404, "用户不存在")

        update_data = req.model_dump(exclude_unset=True)

        # 验证 investment_style
        valid_styles = {"价值投资", "短线交易", "量化对冲", "趋势跟踪", "其他"}
        if "investment_style" in update_data and update_data["investment_style"] is not None:
            if update_data["investment_style"] not in valid_styles:
                raise HTTPException(400, f"无效投资风格: {update_data['investment_style']}")

        # 验证 risk_level
        valid_risks = {"conservative", "moderate", "aggressive"}
        if "risk_level" in update_data and update_data["risk_level"] is not None:
            if update_data["risk_level"] not in valid_risks:
                raise HTTPException(400, f"无效风险偏好: {update_data['risk_level']}")

        # 验证 email 格式
        if "email" in update_data and update_data["email"] is not None and update_data["email"]:
            if "@" not in update_data["email"]:
                raise HTTPException(400, "邮箱格式无效")

        # 验证 phone 格式（简单验证：数字为主）
        if "phone" in update_data and update_data["phone"] is not None and update_data["phone"]:
            import re
            if not re.match(r'^[\d\-+() ]{5,20}$', update_data["phone"]):
                raise HTTPException(400, "手机号格式无效")

        for key, value in update_data.items():
            setattr(db_user, key, value)

        db_user.updated_at = datetime.now()
        session.commit()

        logger.info("用户 %s 更新个人资料: %s", db_user.username, list(update_data.keys()))
        return _user_to_response(db_user)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("更新个人资料失败")
        raise HTTPException(500, f"更新失败: {e}")
    finally:
        session.close()


# ── POST /api/profile/change-password ───────────────

@router.post("/change-password", response_model=PasswordChangeResponse)
async def change_password(req: PasswordChangeRequest, user: dict = Depends(require_api_token)):
    session = _session()
    try:
        db_user = session.query(User).filter_by(id=user["user_id"]).first()
        if not db_user:
            raise HTTPException(404, "用户不存在")

        if not verify_password(req.old_password, db_user.password_hash):
            raise HTTPException(400, "旧密码错误")

        db_user.password_hash = hash_password(req.new_password)
        db_user.updated_at = datetime.now()
        session.commit()

        logger.info("用户 %s 修改密码成功", db_user.username)
        return PasswordChangeResponse(success=True, message="密码修改成功")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("修改密码失败")
        raise HTTPException(500, f"修改失败: {e}")
    finally:
        session.close()


# ── GET /api/profile/stats ──────────────────────────

@router.get("/stats", response_model=InvestmentStatsResponse)
async def get_investment_stats(user: dict = Depends(require_api_token)):
    """
    获取用户的投资统计：
    - 最佳策略（已实现盈亏最高）
    - 涨幅最好股票
    - 亏损最大股票
    - 总成交笔数、总策略数、总已实现盈亏、账户年龄
    """
    session = _session()
    try:
        user_id = user["user_id"]
        db_user = session.query(User).filter_by(id=user_id).first()
        if not db_user:
            raise HTTPException(404, "用户不存在")

        # 获取用户可访问的策略 ID 集合
        accessible_ids = get_accessible_strategy_ids(session, user)

        # 构建策略过滤条件
        if accessible_ids is None:
            # admin：查所有策略
            strategy_filter = Strategys.is_deleted == 0
        else:
            strategy_filter = Strategys.strategy_id.in_(accessible_ids)

        # 获取可访问策略列表
        accessible_strategies = session.query(Strategys.strategy_id, Strategys.name).filter(
            strategy_filter
        ).all()
        accessible_sids = [s.strategy_id for s in accessible_strategies]
        sid_name_map = {s.strategy_id: (s.name or s.strategy_id) for s in accessible_strategies}

        result = InvestmentStatsResponse()

        if not accessible_sids:
            # 无可访问策略，返回空数据
            result.account_age_days = (datetime.now() - db_user.created_at).days if db_user.created_at else 0
            return result

        # ── 总策略数 ──
        result.total_strategies = len(accessible_sids)

        # ── 最佳策略（按已实现盈亏排序）──
        best_strategy_row = session.query(
            Settlements.strategy_id,
            func.sum(Settlements.realized_profit).label("total_profit"),
        ).filter(
            Settlements.strategy_id.in_(accessible_sids),
        ).group_by(Settlements.strategy_id).order_by(
            func.sum(Settlements.realized_profit).desc()
        ).first()

        if best_strategy_row and best_strategy_row.total_profit is not None:
            result.best_strategy = BestItem(
                name=sid_name_map.get(best_strategy_row.strategy_id, best_strategy_row.strategy_id),
                value=float(best_strategy_row.total_profit),
            )

        # ── 总已实现盈亏 ──
        total_pnl_row = session.query(
            func.coalesce(func.sum(Settlements.realized_profit), 0),
        ).filter(
            Settlements.strategy_id.in_(accessible_sids),
        ).scalar()
        result.total_realized_pnl = float(total_pnl_row) if total_pnl_row else 0.0

        # ── 涨幅最好股票 ──
        best_stock_row = session.query(
            Settlements.stock_code,
            func.sum(Settlements.realized_profit).label("total_profit"),
        ).filter(
            Settlements.strategy_id.in_(accessible_sids),
            Settlements.realized_profit > 0,
        ).group_by(Settlements.stock_code).order_by(
            func.sum(Settlements.realized_profit).desc()
        ).first()

        if best_stock_row and best_stock_row.total_profit is not None:
            result.best_stock = BestItem(
                name=best_stock_row.stock_code,
                value=float(best_stock_row.total_profit),
            )

        # ── 亏损最大股票 ──
        worst_stock_row = session.query(
            Settlements.stock_code,
            func.sum(Settlements.realized_profit).label("total_loss"),
        ).filter(
            Settlements.strategy_id.in_(accessible_sids),
            Settlements.realized_profit < 0,
        ).group_by(Settlements.stock_code).order_by(
            func.sum(Settlements.realized_profit).asc()
        ).first()

        if worst_stock_row and worst_stock_row.total_loss is not None:
            result.worst_stock = BestItem(
                name=worst_stock_row.stock_code,
                value=float(worst_stock_row.total_loss),
            )

        # ── 总成交笔数 ──
        total_trades_count = session.query(func.count(Trades.traded_id)).filter(
            Trades.strategy_id.in_(accessible_sids),
        ).scalar()
        result.total_trades = total_trades_count or 0

        # ── 账户年龄 ──
        result.account_age_days = (datetime.now() - db_user.created_at).days if db_user.created_at else 0

        return result
    finally:
        session.close()
