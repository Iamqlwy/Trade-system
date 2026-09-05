"""
下单确认 API — 审批/拒绝 API Token 发起的下单请求。
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.dependencies import require_api_token
from ..auth.models import OrderConfirmation
from ..dependencies import repository
from ..models.requests import OrderRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/order-confirmations", tags=["order-confirmations"])

# 确认请求有效期（秒）
CONFIRM_TTL_SECONDS = 300  # 5 分钟


def _session():
    return repository.SessionLocal()


# ── 响应模型 ─────────────────────────────────

class ConfirmationResponse(BaseModel):
    id: str
    api_token_name: str
    strategy_id: str
    stock_code: str
    order_type: int
    price_type: int
    price: Decimal
    order_volume: int
    order_remark: str = ""
    status: str
    result_order_id: str = ""
    reject_reason: str = ""
    created_at: datetime
    expires_at: datetime


class ApproveResponse(BaseModel):
    success: bool
    order_id: str = ""
    message: str = ""


class RejectRequest(BaseModel):
    reject_reason: str = ""


# ── 端点 ─────────────────────────────────────

@router.get("", response_model=list[ConfirmationResponse])
async def list_confirmations(
    status: str | None = None,
    _user: dict = Depends(require_api_token),
):
    """
    查询确认记录。
    - status 为空（默认）：只查 pending
    - status="all"：查全部
    - status="rejected"/"approved"/"expired"：按状态筛选
    """
    session = _session()
    try:
        q = session.query(OrderConfirmation).filter(
            OrderConfirmation.user_id == _user["user_id"],
        )
        if status is None:
            q = q.filter(OrderConfirmation.status == "pending")
        elif status != "all":
            q = q.filter(OrderConfirmation.status == status)

        rows = q.order_by(OrderConfirmation.created_at.desc()).all()

        return [
            ConfirmationResponse(
                id=r.id,
                api_token_name=r.api_token_name,
                strategy_id=r.strategy_id,
                stock_code=r.stock_code,
                order_type=r.order_type,
                price_type=r.price_type,
                price=r.price,
                order_volume=r.order_volume,
                order_remark=r.order_remark or "",
                status=r.status,
                result_order_id=r.result_order_id or "",
                reject_reason=r.reject_reason or "",
                created_at=r.created_at,
                expires_at=r.expires_at,
            )
            for r in rows
        ]
    finally:
        session.close()


@router.post("/{confirmation_id}/approve", response_model=ApproveResponse)
async def approve_confirmation(
    confirmation_id: str,
    _user: dict = Depends(require_api_token),
):
    """确认并执行下单。"""
    session = _session()
    try:
        conf = session.query(OrderConfirmation).filter_by(
            id=confirmation_id, user_id=_user["user_id"],
        ).first()
        if not conf:
            raise HTTPException(404, "确认记录不存在")
        if conf.status != "pending":
            raise HTTPException(400, f"该请求已处理（{conf.status}）")

        # 检查是否过期
        now = datetime.now(timezone.utc)
        exp = conf.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            conf.status = "expired"
            conf.decided_at = now
            session.commit()
            raise HTTPException(400, "该请求已过期")

        # 构造 OrderRequest
        req = OrderRequest(
            stock_code=conf.stock_code,
            order_type=conf.order_type,
            price=conf.price,
            order_volume=conf.order_volume,
            price_type=conf.price_type,
            order_remark=conf.order_remark or "",
        )

        # 执行下单
        order_id = await _execute_place_order(conf.strategy_id, req, _user)
        if not order_id:
            raise HTTPException(500, "下单执行失败")

        conf.status = "approved"
        conf.result_order_id = order_id
        conf.decided_at = now
        session.commit()

        logger.info(
            "确认下单: confirmation=%s → order=%s user=%s",
            confirmation_id, order_id, _user["sub"],
        )

        # 通知前端结果
        from ..services.notification_hub import notification_hub
        await notification_hub.notify_user(_user["user_id"], {
            "type": "order_confirm_result",
            "data": {
                "confirmation_id": confirmation_id,
                "action": "approved",
                "order_id": order_id,
            },
        })

        return ApproveResponse(
            success=True,
            order_id=order_id,
            message="订单已执行",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("确认下单失败")
        raise HTTPException(500, "确认下单失败")
    finally:
        session.close()


@router.post("/{confirmation_id}/reject", response_model=ApproveResponse)
async def reject_confirmation(
    confirmation_id: str,
    req: RejectRequest,
    _user: dict = Depends(require_api_token),
):
    """拒绝下单请求。"""
    session = _session()
    try:
        conf = session.query(OrderConfirmation).filter_by(
            id=confirmation_id, user_id=_user["user_id"],
        ).first()
        if not conf:
            raise HTTPException(404, "确认记录不存在")
        if conf.status != "pending":
            raise HTTPException(400, f"该请求已处理（{conf.status}）")

        conf.status = "rejected"
        conf.reject_reason = req.reject_reason or None
        conf.decided_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(
            "拒绝下单: confirmation=%s user=%s reason=%s",
            confirmation_id, _user["sub"], req.reject_reason,
        )

        # 审计日志
        from ..logutils.audit import log_order_rejected
        log_order_rejected(
            confirmation_id=confirmation_id,
            strategy_id=conf.strategy_id,
            stock_code=conf.stock_code,
            order_type=str(conf.order_type),
            price=conf.price,
            volume=conf.order_volume,
            reject_reason=req.reject_reason or "",
            api_token_name=conf.api_token_name or "",
        )

        # 通知前端结果
        from ..services.notification_hub import notification_hub
        await notification_hub.notify_user(_user["user_id"], {
            "type": "order_confirm_result",
            "data": {
                "confirmation_id": confirmation_id,
                "action": "rejected",
                "reject_reason": req.reject_reason or "",
            },
        })

        return ApproveResponse(
            success=True,
            message="已拒绝",
        )
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("拒绝下单失败")
        raise HTTPException(500, "操作失败")
    finally:
        session.close()


# ── 下单执行（提取自 router.place_order）────────────

async def _execute_place_order(strategy_id: str, req: OrderRequest, user: dict) -> str:
    """
    执行下单核心逻辑。返回 order_id，失败返回空字符串。
    从 router.place_order 提取，供 approve 端点复用。
    """
    from ..api.router import _do_place_order
    return await _do_place_order(strategy_id, req, user)
