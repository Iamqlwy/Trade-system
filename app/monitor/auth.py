"""监控上传 — Agent Token 认证

Agent 使用 session_id 作为 Bearer token 调用上传接口。
通过 AgentManager._session_users 反查 user_id。
"""

from __future__ import annotations

from fastapi import HTTPException, Request


async def verify_agent_token(request: Request) -> dict:
    """
    FastAPI 依赖：从 Authorization header 提取 session_id，反查 user_id。

    返回: {"user_id": int, "session_id": str}
    失败: HTTP 401
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")

    session_id = auth[7:].strip()
    if not session_id:
        raise HTTPException(401, "Empty token")

    from ..services.agent_manager import agent_manager

    user_id = agent_manager._session_users.get(session_id)
    if not user_id:
        # 内存中没有映射，尝试从 DB 恢复（session 可能因重启丢失）
        user_id = _lookup_session_in_db(session_id)
        if not user_id:
            raise HTTPException(401, "Invalid agent token")
        # 恢复到内存
        agent_manager._session_users[session_id] = user_id

    return {"user_id": user_id, "session_id": session_id}


def _lookup_session_in_db(session_id: str) -> int | None:
    """从 DB 查找 session 对应的 user_id（服务重启后恢复用）"""
    try:
        from ..dependencies import repository
        from ..store.models import AgentSessions

        session = repository.SessionLocal()
        try:
            row = session.query(AgentSessions.user_id).filter(
                AgentSessions.id == session_id,
            ).first()
            return row[0] if row else None
        finally:
            session.close()
    except Exception:
        return None
