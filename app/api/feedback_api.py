"""用户反馈 API

用户提交反馈、查看自己的反馈列表和详情。
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.dependencies import require_api_token
from ..dependencies import repository
from ..store.models import Feedback

logger = logging.getLogger(__name__)

feedback_router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def _session() -> Session:
    return repository.SessionLocal()


# ── Request 模型 ──────────────────────────────────

class CreateFeedbackRequest(BaseModel):
    type: str = "other"  # bug / feature / question / other
    title: str
    content: str


# ── 用户端 ──────────────────────────────────────

@feedback_router.post("")
async def submit_feedback(req: CreateFeedbackRequest, user: dict = Depends(require_api_token)):
    """提交反馈"""
    if req.type not in ("bug", "feature", "question", "other"):
        raise HTTPException(400, "无效的反馈类型")
    if not req.title.strip():
        raise HTTPException(400, "标题不能为空")
    if not req.content.strip():
        raise HTTPException(400, "内容不能为空")

    session = _session()
    try:
        fb = Feedback(
            user_id=user["user_id"],
            type=req.type,
            title=req.title.strip()[:200],
            content=req.content.strip(),
            status="pending",
        )
        session.add(fb)
        session.commit()
        session.refresh(fb)
        logger.info("用户 %s 提交反馈 #%d: %s", user["sub"], fb.id, fb.title)
        return {"id": fb.id, "status": "ok"}
    except Exception as e:
        session.rollback()
        logger.exception("提交反馈失败")
        raise HTTPException(500, f"提交失败: {e}")
    finally:
        session.close()


@feedback_router.get("")
async def list_my_feedback(user: dict = Depends(require_api_token)):
    """列出当前用户的反馈（按时间倒序）"""
    session = _session()
    try:
        rows = (
            session.query(Feedback)
            .filter_by(user_id=user["user_id"])
            .order_by(Feedback.created_at.desc())
            .all()
        )
        return [_feedback_to_dict(r) for r in rows]
    finally:
        session.close()


@feedback_router.get("/{feedback_id}")
async def get_feedback(feedback_id: int, user: dict = Depends(require_api_token)):
    """查看反馈详情"""
    session = _session()
    try:
        fb = session.query(Feedback).filter_by(
            id=feedback_id, user_id=user["user_id"],
        ).first()
        if not fb:
            raise HTTPException(404, "反馈不存在")
        return _feedback_to_dict(fb, detail=True)
    finally:
        session.close()


# ── 辅助函数 ──────────────────────────────────────

def _feedback_to_dict(fb: Feedback, detail: bool = False) -> dict:
    """Feedback 模型转 dict"""
    d = {
        "id": fb.id,
        "type": fb.type,
        "title": fb.title,
        "status": fb.status,
        "created_at": fb.created_at.isoformat() if fb.created_at else None,
    }
    if detail:
        d["content"] = fb.content
        d["admin_reply"] = fb.admin_reply
        d["replied_at"] = fb.replied_at.isoformat() if fb.replied_at else None
    return d
