"""Cron REST API — 定时任务管理端点"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..auth.dependencies import require_cron_access
from ..utils.sanitize import sanitize_str, sanitize_text_field

logger = logging.getLogger(__name__)

cron_router = APIRouter(prefix="/api/cron", tags=["cron"])


class CreateJobRequest(BaseModel):
    name: str = Field(..., max_length=100)
    schedule: str = Field(..., max_length=200)
    prompt: str = Field(..., max_length=50000)

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str) -> str:
        return sanitize_str(v, max_length=100) or v

    @field_validator("schedule")
    @classmethod
    def _sanitize_schedule(cls, v: str) -> str:
        return sanitize_str(v, max_length=200) or v

    @field_validator("prompt")
    @classmethod
    def _sanitize_prompt(cls, v: str) -> str:
        return sanitize_text_field(v, max_length=50000) or v


class UpdateJobRequest(BaseModel):
    name: str | None = Field(None, max_length=100)
    schedule: str | None = Field(None, max_length=200)
    prompt: str | None = Field(None, max_length=50000)
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str | None) -> str | None:
        return sanitize_str(v, max_length=100) if v is not None else None

    @field_validator("schedule")
    @classmethod
    def _sanitize_schedule(cls, v: str | None) -> str | None:
        return sanitize_str(v, max_length=200) if v is not None else None

    @field_validator("prompt")
    @classmethod
    def _sanitize_prompt(cls, v: str | None) -> str | None:
        return sanitize_text_field(v, max_length=50000) if v is not None else None


# ── 任务 CRUD ────────────────────────────────────

@cron_router.get("/jobs")
async def api_list_jobs(user: dict = Depends(require_cron_access)):
    from ..agent.cron import list_jobs
    return {"jobs": list_jobs(user["user_id"])}


@cron_router.post("/jobs")
async def api_create_job(body: CreateJobRequest, user: dict = Depends(require_cron_access)):
    from ..agent.cron import create_job
    from ..services.agent_manager import agent_manager

    try:
        job = create_job(user["user_id"], body.name, body.schedule, body.prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 广播创建事件
    await agent_manager.broadcast_cron_event(user["user_id"], "cron_job_created", job)
    return {"ok": True, "job": job}


@cron_router.put("/jobs/{job_id}")
async def api_update_job(job_id: str, body: UpdateJobRequest, user: dict = Depends(require_cron_access)):
    from ..agent.cron import update_job
    from ..services.agent_manager import agent_manager

    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.schedule is not None:
        fields["schedule"] = body.schedule
    if body.prompt is not None:
        fields["prompt"] = body.prompt
    if body.enabled is not None:
        fields["enabled"] = body.enabled

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        job = update_job(job_id, user["user_id"], **fields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    await agent_manager.broadcast_cron_event(user["user_id"], "cron_job_updated", job)
    return {"ok": True, "job": job}


@cron_router.delete("/jobs/{job_id}")
async def api_delete_job(job_id: str, user: dict = Depends(require_cron_access)):
    from ..agent.cron import delete_job
    from ..services.agent_manager import agent_manager

    ok = delete_job(job_id, user["user_id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")

    await agent_manager.broadcast_cron_event(user["user_id"], "cron_job_deleted", {"job_id": job_id})
    return {"ok": True}


# ── 执行操作 ────────────────────────────────────

@cron_router.post("/jobs/{job_id}/run")
async def api_trigger_job(job_id: str, user: dict = Depends(require_cron_access)):
    try:
        from ..agent.cron import get_job, execute_job
        from ..services.agent_manager import agent_manager

        job = get_job(job_id, user["user_id"])
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        # 广播触发和开始事件
        await agent_manager.broadcast_cron_event(user["user_id"], "cron_job_triggered", {
            "job_id": job_id, "name": job["name"],
        })
        await agent_manager.broadcast_cron_event(user["user_id"], "cron_run_started", {
            "job_id": job_id, "name": job["name"],
        })

        result = await execute_job(job_id, user["user_id"], job["prompt"], job["name"])

        if result.get("status") == "completed":
            await agent_manager.broadcast_cron_event(user["user_id"], "cron_run_completed", {
                "job_id": job_id, "run_id": result.get("run_id"),
                "name": job["name"], "output_summary": result.get("output_summary", ""),
            })
        else:
            await agent_manager.broadcast_cron_event(user["user_id"], "cron_run_failed", {
                "job_id": job_id, "run_id": result.get("run_id"),
                "name": job["name"], "error_message": result.get("error_message", ""),
            })

        return {"ok": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Cron trigger failed for job %s: %s", job_id, e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── 历史记录 ────────────────────────────────────

@cron_router.get("/jobs/{job_id}/runs")
async def api_list_runs(job_id: str, user: dict = Depends(require_cron_access)):
    from ..agent.cron import list_runs
    # 先校验所有权
    from ..agent.cron import get_job
    job = get_job(job_id, user["user_id"])
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"runs": list_runs(job_id, user["user_id"])}


@cron_router.get("/runs/{run_id}/output")
async def api_get_run_output(run_id: str, user: dict = Depends(require_cron_access)):
    # 校验所有权：确保 run 属于当前用户
    from ..dependencies import repository
    from ..store.models import CronJobRun

    session = repository.SessionLocal()
    try:
        row = session.query(CronJobRun).filter_by(id=run_id, user_id=user["user_id"]).first()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
    finally:
        session.close()

    from ..agent.cron import get_run_output
    output = get_run_output(run_id)
    if output is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"output": output}


@cron_router.get("/runs/{run_id}/context")
async def api_get_run_context(run_id: str, user: dict = Depends(require_cron_access)):
    """返回某次运行的完整对话上下文（JSONL 解析为消息数组）。"""
    import json
    from pathlib import Path

    from ..services.cron_service import get_run_output as _get_run_output

    # 先从 run 记录获取 context_file 路径
    from ..dependencies import repository
    from ..store.models import CronJobRun

    session = repository.SessionLocal()
    try:
        row = session.query(CronJobRun).filter_by(id=run_id, user_id=user["user_id"]).first()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        context_path = row.context_file
    finally:
        session.close()

    if not context_path:
        raise HTTPException(status_code=404, detail="No context recorded for this run")

    p = Path(context_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Context file not found on disk")

    # 解析 JSONL，处理 _compact 记录
    messages: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        # _compact 记录展开为压缩后的消息（保留完整上下文）
        if msg.get("role") == "_compact" and "compressed_messages" in msg:
            compacted = msg["compressed_messages"]
            # 插入一个标记消息说明压缩发生
            messages.append({
                "role": "_compact",
                "content": f"上下文已压缩 — {msg.get('compressed_count', '?')} 轮被总结",
                "compact_range": True,
            })
            for cm in compacted:
                if cm.get("role") not in ("system",):
                    messages.append(cm)
        elif msg.get("role") == "_usage":
            continue  # 跳过用量统计记录
        elif msg.get("role") == "_system_prompt":
            continue  # 跳过系统提示（前端不需要显示）
        else:
            messages.append(msg)

    return {"messages": messages}


# ── 从 cron 运行创建 agent 会话 ─────────────────

@cron_router.post("/runs/{run_id}/session")
async def api_create_session_from_run(run_id: str, user: dict = Depends(require_cron_access)):
    """从 cron 运行上下文创建一个 Agent 会话，以便用 Agent 框架展示和继续对话。"""
    import json
    from pathlib import Path

    from ..dependencies import repository
    from ..store.models import CronJobRun, CronJob
    from ..services.agent_manager import agent_manager
    from ..agent.config import get_agent_home

    session = repository.SessionLocal()
    try:
        row = session.query(CronJobRun).filter_by(id=run_id, user_id=user["user_id"]).first()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        context_path = row.context_file
        job_id = row.job_id
    finally:
        session.close()

    if not context_path:
        raise HTTPException(status_code=404, detail="No context recorded for this run")

    p = Path(context_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Context file not found on disk")

    # 获取 job 名称
    session2 = repository.SessionLocal()
    try:
        job_row = session2.query(CronJob).filter_by(id=job_id).first()
        job_name = job_row.name if job_row else "unknown"
    finally:
        session2.close()

    # 读取并展开 JSONL 上下文
    raw_messages: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = msg.get("role", "")
        if role in ("_system_prompt", "_usage"):
            continue
        if role == "_compact" and "compressed_messages" in msg:
            raw_messages.append({
                "role": "_compact",
                "content": f"上下文已压缩 — {msg.get('compressed_count', '?')} 轮被总结",
                "compact_range": True,
            })
            for cm in msg["compressed_messages"]:
                if cm.get("role") not in ("system",):
                    raw_messages.append(cm)
        else:
            raw_messages.append(msg)

    # 创建 Agent 会话（直接标记为 cron 类型，不出现在对话列表中）
    new_session_id = agent_manager.create_session(user_id=user["user_id"], agent_type="cron")

    # 写入 context.jsonl
    session_dir = get_agent_home() / "sessions" / new_session_id
    context_file = session_dir / "context.jsonl"
    with open(context_file, "w", encoding="utf-8") as f:
        for msg in raw_messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    # 计算运行次数（该任务到此行为止的完成次数）
    run_count = 1
    try:
        from ..store.models import CronJobRun
        session3 = repository.SessionLocal()
        try:
            run_count = session3.query(CronJobRun).filter(
                CronJobRun.job_id == job_id,
                CronJobRun.user_id == user["user_id"],
            ).count()
        finally:
            session3.close()
    except Exception:
        pass

    # 会话标题：任务名 第N次 时间
    from datetime import datetime
    now_str = datetime.now().strftime("%m-%d %H:%M")
    title = f"{job_name} 第{run_count}次 {now_str}"
    agent_manager._save_title_to_file(new_session_id, title)

    # 写入 agent_type 到 meta.json（供 FS 回退路径识别 cron 会话）
    import json as _json
    meta_file = session_dir / "meta.json"
    try:
        meta = {}
        if meta_file.exists():
            with open(meta_file, encoding="utf-8") as f:
                meta = _json.load(f)
        meta["agent_type"] = "cron"
        with open(meta_file, "w", encoding="utf-8") as f:
            _json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # 更新 DB：标题和消息数（agent_type 已在创建时设为 'cron'）
    try:
        from ..store.models import AgentSessions
        session4 = repository.SessionLocal()
        try:
            session4.query(AgentSessions).filter_by(id=new_session_id).update({
                "title": title,
                "message_count": len(raw_messages),
            })
            session4.commit()
        finally:
            session4.close()
    except Exception as e:
        logger.warning("Failed to update cron session in DB: %s", e)

    return {"session_id": new_session_id, "title": title}
