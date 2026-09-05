"""Cron 服务层 — 数据库驱动的定时任务管理。

替代 app/agent/cron/jobs.py 的文件操作，提供按用户隔离的 CRUD 和调度接口。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import contextvars

from ..agent.config import get_cron_dir

logger = logging.getLogger(__name__)

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

# 中国标准时间（A 股交易时区）
_CST = timezone(timedelta(hours=8))

# 当前执行上下文的 user_id（供 agent tool 使用）
_current_user_id: contextvars.ContextVar[int] = contextvars.ContextVar("cron_user_id", default=0)

OUTPUT_DIR = get_cron_dir() / "output"


def _now() -> datetime:
    return datetime.now(_CST)


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _parse_schedule(schedule: str, now: datetime) -> tuple[Optional[datetime], Optional[datetime], str]:
    """解析调度字符串，返回 (next_run_at, first_run_at, schedule_type)。"""
    schedule = schedule.strip()

    # 一次性 ISO 时间（支持可选时区偏移，如 +08:00）
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2})?)$", schedule)
    if iso_match:
        try:
            ts = datetime.fromisoformat(iso_match.group(1))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_CST)
            return ts, ts, "oneshot"
        except ValueError:
            return None, None, "unknown"

    # 间隔: "30m", "every 2h", "5m", "1h"
    interval_match = re.match(r"^(?:every\s+)?(\d+)\s*(m|h|d)$", schedule, re.IGNORECASE)
    if interval_match:
        value = int(interval_match.group(1))
        unit = interval_match.group(2).lower()
        if unit == "m":
            delta = timedelta(minutes=value)
        elif unit == "h":
            delta = timedelta(hours=value)
        else:
            delta = timedelta(days=value)
        next_run = now + delta
        return next_run, now + delta, "interval"

    # Cron 表达式
    if HAS_CRONITER:
        try:
            cron = croniter(schedule, now)
            next_run = cron.get_next(datetime)
            return next_run, next_run, "cron"
        except (ValueError, KeyError):
            return None, None, "unknown"

    return None, None, "unknown"


def _advance_next_run(job_dict: dict[str, Any], now: Optional[datetime] = None) -> dict[str, Any]:
    """执行后更新 next_run_at 和 last_run_at。"""
    if now is None:
        now = _now()
    job_dict["last_run_at"] = now

    schedule_type = job_dict.get("schedule_type", "")
    schedule = job_dict.get("schedule", "")

    if schedule_type == "oneshot":
        job_dict["enabled"] = False
        job_dict["next_run_at"] = None
    elif schedule_type == "interval":
        m = re.match(r"^(?:every\s+)?(\d+)\s*(m|h|d)$", schedule, re.IGNORECASE)
        if m:
            value = int(m.group(1))
            unit = m.group(2).lower()
            deltas = {"m": timedelta(minutes=value), "h": timedelta(hours=value), "d": timedelta(days=value)}
            job_dict["next_run_at"] = (now + deltas.get(unit, timedelta(minutes=value)))
    elif schedule_type == "cron" and HAS_CRONITER:
        try:
            cron = croniter(schedule, now)
            job_dict["next_run_at"] = cron.get_next(datetime)
        except (ValueError, KeyError):
            pass

    return job_dict


# ---------------------------------------------------------------------------
# CRUD 操作
# ---------------------------------------------------------------------------

def list_jobs(user_id: int) -> list[dict[str, Any]]:
    """列出用户的所有定时任务。"""
    from ..dependencies import repository

    session = repository.SessionLocal()
    try:
        from ..store.models import CronJob
        rows = session.query(CronJob).filter_by(user_id=user_id).order_by(CronJob.created_at.desc()).all()
        return [_job_to_dict(r) for r in rows]
    finally:
        session.close()


def get_job(job_id: str, user_id: int) -> dict[str, Any] | None:
    """查询单个任务（校验所有权）。"""
    from ..dependencies import repository

    session = repository.SessionLocal()
    try:
        from ..store.models import CronJob
        row = session.query(CronJob).filter_by(id=job_id, user_id=user_id).first()
        return _job_to_dict(row) if row else None
    finally:
        session.close()


def create_job(user_id: int, name: str, schedule: str, prompt: str) -> dict[str, Any]:
    """创建新定时任务。"""
    now = _now()
    next_run, _, schedule_type = _parse_schedule(schedule, now)
    if next_run is None:
        raise ValueError(f"Cannot parse schedule: {schedule}")

    from ..dependencies import repository
    from ..store.models import CronJob

    job_id = uuid.uuid4().hex[:16]
    session = repository.SessionLocal()
    try:
        row = CronJob(
            id=job_id,
            user_id=user_id,
            name=name,
            schedule=schedule,
            schedule_type=schedule_type,
            prompt=prompt,
            enabled=True,
            next_run_at=next_run,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        logger.info("Cron job created: %s (user=%d, next=%s)", name, user_id, next_run)
        return _job_to_dict(row)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_job(job_id: str, user_id: int, **fields) -> dict[str, Any] | None:
    """更新任务字段（name, schedule, prompt, enabled）。"""
    from ..dependencies import repository
    from ..store.models import CronJob

    session = repository.SessionLocal()
    try:
        row = session.query(CronJob).filter_by(id=job_id, user_id=user_id).first()
        if not row:
            return None

        if "name" in fields:
            row.name = fields["name"]
        if "schedule" in fields:
            now = _now()
            next_run, _, schedule_type = _parse_schedule(fields["schedule"], now)
            if next_run is None:
                raise ValueError(f"Cannot parse schedule: {fields['schedule']}")
            row.schedule = fields["schedule"]
            row.schedule_type = schedule_type
            row.next_run_at = next_run
        if "prompt" in fields:
            row.prompt = fields["prompt"]
        if "enabled" in fields:
            row.enabled = bool(fields["enabled"])

        row.updated_at = _now()
        session.commit()
        logger.info("Cron job updated: %s", job_id)
        return _job_to_dict(row)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def delete_job(job_id: str, user_id: int) -> bool:
    """删除任务（级联删除运行记录）。"""
    from ..dependencies import repository
    from ..store.models import CronJob

    session = repository.SessionLocal()
    try:
        row = session.query(CronJob).filter_by(id=job_id, user_id=user_id).first()
        if not row:
            return False
        session.delete(row)
        session.commit()
        logger.info("Cron job deleted: %s", job_id)
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 调度查询
# ---------------------------------------------------------------------------

def get_due_jobs() -> list[dict[str, Any]]:
    """返回所有已到期的启用任务（跨用户）。"""
    from ..dependencies import repository
    from ..store.models import CronJob

    now = _now()
    session = repository.SessionLocal()
    try:
        rows = session.query(CronJob).filter(
            CronJob.enabled == True,
            CronJob.next_run_at != None,
            CronJob.next_run_at <= now,
        ).all()
        return [_job_to_dict(r) for r in rows]
    finally:
        session.close()


def mark_job_run(job_id: str, now: Optional[datetime] = None) -> None:
    """更新任务的 last_run_at 和 next_run_at 并持久化。"""
    from ..dependencies import repository
    from ..store.models import CronJob

    if now is None:
        now = _now()

    session = repository.SessionLocal()
    try:
        row = session.query(CronJob).filter_by(id=job_id).first()
        if not row:
            return
        job_dict = _job_to_dict(row)
        _advance_next_run(job_dict, now)
        row.last_run_at = job_dict.get("last_run_at")
        row.next_run_at = job_dict.get("next_run_at")
        row.enabled = job_dict.get("enabled", True)
        row.updated_at = now
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 执行记录
# ---------------------------------------------------------------------------

def create_run(job_id: str, user_id: int) -> dict[str, Any]:
    """创建一条 running 状态的执行记录。"""
    from ..dependencies import repository
    from ..store.models import CronJobRun

    run_id = uuid.uuid4().hex[:16]
    now = _now()

    session = repository.SessionLocal()
    try:
        row = CronJobRun(
            id=run_id,
            job_id=job_id,
            user_id=user_id,
            status="running",
            started_at=now,
        )
        session.add(row)
        session.commit()
        return _run_to_dict(row)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def complete_run(run_id: str, output_summary: str, output_file: str, context_file: str = "") -> dict[str, Any] | None:
    """标记执行记录为 completed（包含上下文文件路径）。"""
    from ..dependencies import repository
    from ..store.models import CronJobRun

    now = _now()
    session = repository.SessionLocal()
    try:
        row = session.query(CronJobRun).filter_by(id=run_id).first()
        if not row:
            return None
        row.status = "completed"
        row.completed_at = now
        row.output_summary = output_summary[:500]
        row.output_file = output_file
        if context_file:
            row.context_file = context_file
        session.commit()
        return _run_to_dict(row)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def fail_run(run_id: str, error_message: str) -> dict[str, Any] | None:
    """标记执行记录为 failed。"""
    from ..dependencies import repository
    from ..store.models import CronJobRun

    now = _now()
    session = repository.SessionLocal()
    try:
        row = session.query(CronJobRun).filter_by(id=run_id).first()
        if not row:
            return None
        row.status = "failed"
        row.completed_at = now
        row.error_message = error_message[:1000]
        session.commit()
        return _run_to_dict(row)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_runs(job_id: str, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """获取任务的运行历史。"""
    from ..dependencies import repository
    from ..store.models import CronJobRun

    session = repository.SessionLocal()
    try:
        rows = (
            session.query(CronJobRun)
            .filter_by(job_id=job_id, user_id=user_id)
            .order_by(CronJobRun.started_at.desc())
            .limit(limit)
            .all()
        )
        return [_run_to_dict(r) for r in rows]
    finally:
        session.close()


def get_run_output(run_id: str) -> str | None:
    """读取完整输出文件内容。"""
    from ..dependencies import repository
    from ..store.models import CronJobRun

    session = repository.SessionLocal()
    try:
        row = session.query(CronJobRun).filter_by(id=run_id).first()
        if not row or not row.output_file:
            return None
        path = Path(row.output_file)
        if not path.exists():
            return "(输出文件不存在)"
        return path.read_text(encoding="utf-8", errors="replace")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 执行入口（供调度器和 trigger API 调用）
# ---------------------------------------------------------------------------

async def execute_job(job_id: str, user_id: int, prompt: str, job_name: str) -> dict[str, Any]:
    """执行一个 cron 任务：创建 run 记录 → 运行 agent（含完整上下文） → 保存输出 → 更新记录。

    返回 {"run_id": ..., "status": ..., "output_summary": ..., "output_file": ...}
    """
    run = create_run(job_id, user_id)
    run_id = run["id"]

    try:
        from ..agent.agents.simple import SimpleAgent
        from ..agent.config import get_model_config, get_workspace_dir

        # 为每次运行创建独立的上下文目录
        context_dir = OUTPUT_DIR / job_id / "contexts"
        context_dir.mkdir(parents=True, exist_ok=True)
        context_file = context_dir / f"{run_id}.jsonl"

        # 为每次运行分配独立工作区
        workspace = get_workspace_dir(run_id)

        model_cfg = get_model_config()

        # 获取记忆服务（DB 模式）
        memory_svc = None
        if user_id > 0:
            try:
                from .memory_service import memory_service
                memory_svc = memory_service
            except Exception:
                pass

        agent = SimpleAgent(
            model=model_cfg["model"],
            base_url=model_cfg["base_url"],
            api_key=model_cfg["api_key"],
            api_mode=model_cfg["api_mode"],
            context_file=context_file,
            user_id=user_id,
            workspace=workspace,
            memory_service=memory_svc,
        )
        # 设置 user_id 以便 agent tool 使用
        _current_user_id.set(user_id)

        result = await agent.run(prompt)
        final_response = result.get("final_response", "")

        # 保存输出文件
        _ensure_output_dir()
        now = _now()
        job_output_dir = OUTPUT_DIR / job_id
        job_output_dir.mkdir(parents=True, exist_ok=True)
        ts = now.strftime("%Y%m%d_%H%M%S")
        output_file = job_output_dir / f"{run_id}_{ts}.md"
        output_file.write_text(
            f"# {job_name}\n\n"
            f"**Run at:** {now.isoformat()}\n\n"
            f"**Prompt:** {prompt[:500]}\n\n"
            f"**Result:**\n\n{final_response}",
            encoding="utf-8",
        )

        summary = final_response[:500] if final_response else "(empty)"
        complete_run(run_id, summary, str(output_file), str(context_file))

        return {
            "run_id": run_id,
            "status": "completed",
            "output_summary": summary,
            "output_file": str(output_file),
        }
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.exception("Cron job %s execution failed", job_id)
        fail_run(run_id, error_msg)
        return {
            "run_id": run_id,
            "status": "failed",
            "error_message": error_msg,
        }


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------

def _job_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "schedule": row.schedule,
        "schedule_type": row.schedule_type,
        "prompt": row.prompt,
        "enabled": row.enabled,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _run_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "user_id": row.user_id,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
       "output_summary": row.output_summary or "",
        "context_file": row.context_file or "",
       "output_file": row.output_file or "",
        "error_message": row.error_message or "",
    }
