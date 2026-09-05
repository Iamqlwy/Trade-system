"""
站内信 API（邮箱模式）

管理员可向全体或指定用户发送消息；用户收件箱支持查看、已读/未读标记、软删除。
"""
import logging

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth.models import User, Message
from ..auth.dependencies import require_api_token
from ..dependencies import repository
from ..models.requests import SendMessageRequest, BatchDeleteMessagesRequest, MarkReadRequest
from ..permissions.dependencies import require_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/messages", tags=["messages"])


def _session() -> Session:
    return repository.SessionLocal()


# ── 发送消息 ──────────────────────────────────────

@router.post("/")
async def send_message(
    req: SendMessageRequest,
    admin: dict = Depends(require_admin_user),
):
    """管理员发送站内信（recipient_ids 为空则发给全部用户）"""
    session = _session()
    try:
        if req.recipient_ids:
            # 指定用户群发
            users = session.query(User).filter(User.id.in_(req.recipient_ids)).all()
            if not users:
                raise HTTPException(400, "未找到任何有效收件人")
        else:
            # 全部用户
            users = session.query(User).all()

        now = datetime.now()
        messages = []
        for u in users:
            messages.append(Message(
                sender_id=admin["user_id"],
                recipient_id=u.id,
                title=req.title,
                content=req.content,
                created_at=now,
            ))

        session.add_all(messages)
        session.commit()

        logger.info(
            "管理员 %s 发送消息: title=%r 收件人数=%d",
            admin["sub"], req.title, len(messages),
        )
        return {"success": True, "message": f"已发送给 {len(messages)} 位用户"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("发送消息失败")
        raise HTTPException(400, f"发送失败: {e}")
    finally:
        session.close()


# ── 收件箱 ──────────────────────────────────────

@router.get("/")
async def list_inbox(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query("all", pattern="^(all|unread|read)$"),
    user: dict = Depends(require_api_token),
):
    """收件箱列表（分页）"""
    session = _session()
    try:
        q = session.query(Message).filter(
            Message.recipient_id == user["user_id"],
            Message.is_deleted == False,
        )
        if status == "unread":
            q = q.filter(Message.is_read == False)
        elif status == "read":
            q = q.filter(Message.is_read == True)

        total = q.count()
        rows = q.order_by(Message.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        # 批量查询发件人用户名
        sender_ids = {r.sender_id for r in rows if r.sender_id}
        user_map: dict[int, str] = {}
        if sender_ids:
            senders = session.query(User).filter(User.id.in_(sender_ids)).all()
            user_map = {u.id: u.username for u in senders}

        items = []
        for r in rows:
            items.append({
                "id": r.id,
                "title": r.title,
                "content": r.content,
                "sender_name": user_map.get(r.sender_id, "系统"),
                "is_read": r.is_read,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    finally:
        session.close()


@router.get("/unread-count")
async def unread_count(user: dict = Depends(require_api_token)):
    """获取当前用户未读消息数"""
    session = _session()
    try:
        count = session.query(func.count(Message.id)).filter(
            Message.recipient_id == user["user_id"],
            Message.is_read == False,
            Message.is_deleted == False,
        ).scalar() or 0
        return {"count": count}
    finally:
        session.close()


# ── 已发送（发件箱）──────────────────────────────

@router.get("/sent")
async def list_sent(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: dict = Depends(require_admin_user),
):
    """管理员查看已发送消息列表（按批次聚合）"""
    session = _session()
    try:
        # 按 title + content + created_at 聚合（同一批群发共享相同的时间和内容）
        from sqlalchemy import text
        rows = session.execute(text("""
            SELECT
                MIN(m.id) AS id,
                m.title,
                m.content,
                m.created_at,
                COUNT(*) AS recipient_count,
                SUM(CASE WHEN m.is_read = 1 THEN 1 ELSE 0 END) AS read_count
            FROM messages m
            WHERE m.sender_id = :sender_id
            GROUP BY m.title, m.content, m.created_at
            ORDER BY m.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {
            "sender_id": admin["user_id"],
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }).fetchall()

        total_row = session.execute(text("""
            SELECT COUNT(DISTINCT CONCAT(m.title, m.content, CAST(m.created_at AS CHAR)))
            FROM messages m
            WHERE m.sender_id = :sender_id
        """), {"sender_id": admin["user_id"]}).scalar()

        items = []
        for r in rows:
            items.append({
                "id": r.id,
                "title": r.title,
                "content": r.content,
                "recipient_count": r.recipient_count,
                "read_count": r.read_count,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            })

        return {
            "items": items,
            "total": total_row or 0,
            "page": page,
            "page_size": page_size,
        }
    finally:
        session.close()


# ── 消息详情 ──────────────────────────────────────

@router.get("/{message_id}")
async def get_message_detail(
    message_id: int,
    user: dict = Depends(require_api_token),
):
    """查看消息详情（自动标记已读）"""
    session = _session()
    try:
        msg = session.query(Message).filter(
            Message.id == message_id,
            Message.recipient_id == user["user_id"],
            Message.is_deleted == False,
        ).first()

        if not msg:
            raise HTTPException(404, "消息不存在或无权访问")

        # 自动标记已读
        if not msg.is_read:
            msg.is_read = True
            msg.read_at = datetime.now()
            session.commit()

        sender_name = "系统"
        if msg.sender_id:
            s = session.query(User).filter_by(id=msg.sender_id).first()
            if s:
                sender_name = s.username

        return {
            "id": msg.id,
            "title": msg.title,
            "content": msg.content,
            "sender_name": sender_name,
            "is_read": msg.is_read,
            "read_at": msg.read_at.isoformat() if msg.read_at else None,
            "created_at": msg.created_at.isoformat() if msg.created_at else "",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取消息详情失败")
        raise HTTPException(500, f"获取消息失败: {e}")
    finally:
        session.close()


# ── 标记已读/未读 ────────────────────────────────

@router.put("/{message_id}/read")
async def mark_read(
    message_id: int,
    req: MarkReadRequest,
    user: dict = Depends(require_api_token),
):
    """标记单条消息已读/未读"""
    session = _session()
    try:
        msg = session.query(Message).filter(
            Message.id == message_id,
            Message.recipient_id == user["user_id"],
            Message.is_deleted == False,
        ).first()

        if not msg:
            raise HTTPException(404, "消息不存在或无权访问")

        msg.is_read = req.is_read
        msg.read_at = datetime.now() if req.is_read else None
        session.commit()
        return {"success": True, "is_read": req.is_read}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"操作失败: {e}")
    finally:
        session.close()


# ── 删除（软删除）─────────────────────────────────

@router.delete("/{message_id}")
async def delete_message(
    message_id: int,
    user: dict = Depends(require_api_token),
):
    """软删除单条消息"""
    session = _session()
    try:
        msg = session.query(Message).filter(
            Message.id == message_id,
            Message.recipient_id == user["user_id"],
            Message.is_deleted == False,
        ).first()

        if not msg:
            raise HTTPException(404, "消息不存在或无权访问")

        msg.is_deleted = True
        session.commit()
        return {"success": True, "message": "消息已删除"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"删除失败: {e}")
    finally:
        session.close()


@router.post("/batch-delete")
async def batch_delete(
    req: BatchDeleteMessagesRequest,
    user: dict = Depends(require_api_token),
):
    """批量软删除消息"""
    session = _session()
    try:
        rows = session.query(Message).filter(
            Message.id.in_(req.ids),
            Message.recipient_id == user["user_id"],
            Message.is_deleted == False,
        ).all()

        for r in rows:
            r.is_deleted = True
        session.commit()
        return {"success": True, "deleted": len(rows)}
    except Exception as e:
        session.rollback()
        raise HTTPException(400, f"批量删除失败: {e}")
    finally:
        session.close()
