"""Cron 任务存储与管理。

移植自 code/simple-agent/cron/jobs.py，适配 Web 版 agent。
任务存储: ~/.unified-agent/cron/jobs.json
输出保存: ~/.unified-agent/cron/output/<name>/<timestamp>.md
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from ..config import get_cron_dir

logger = logging.getLogger(__name__)

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

CRON_DIR = get_cron_dir()
JOBS_FILE = CRON_DIR / "jobs.json"
OUTPUT_DIR = CRON_DIR / "output"


def _now() -> datetime:
    return datetime.now().astimezone()


def _ensure_dirs() -> None:
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_jobs() -> list[dict[str, Any]]:
    if not JOBS_FILE.exists():
        return []
    try:
        return json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def list_jobs() -> list[dict[str, Any]]:
    return load_jobs()


def save_jobs(jobs: list[dict[str, Any]]) -> None:
    _ensure_dirs()
    fd, tmp = tempfile.mkstemp(dir=str(CRON_DIR), suffix=".tmp", prefix=".jobs_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(JOBS_FILE))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _parse_schedule(schedule: str, now: datetime) -> tuple[Optional[datetime], Optional[datetime], str]:
    """解析调度字符串，返回 (next_run_at, first_run_at, schedule_type)。

    schedule_type: "cron" | "interval" | "oneshot"
    """
    schedule = schedule.strip()

    # 一次性 ISO 时间: "2026-05-18T14:00"
    iso_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)$', schedule)
    if iso_match:
        try:
            ts = datetime.fromisoformat(iso_match.group(1))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=now.tzinfo)
            return ts, ts, "oneshot"
        except ValueError:
            return None, None, "unknown"

    # 间隔: "30m", "every 2h", "5m", "1h"
    interval_match = re.match(r'^(?:every\s+)?(\d+)\s*(m|h|d)$', schedule, re.IGNORECASE)
    if interval_match:
        value = int(interval_match.group(1))
        unit = interval_match.group(2).lower()
        if unit == 'm':
            delta = timedelta(minutes=value)
        elif unit == 'h':
            delta = timedelta(hours=value)
        else:
            delta = timedelta(days=value)
        next_run = now + delta
        return next_run, now + delta, "interval"

    # Cron 表达式: "*/5 * * * *"
    if HAS_CRONITER:
        try:
            cron = croniter(schedule, now)
            next_run = cron.get_next(datetime)
            return next_run, next_run, "cron"
        except (ValueError, KeyError):
            return None, None, "unknown"

    return None, None, "unknown"


def create_job(
    name: str,
    schedule: str,
    prompt: str,
    deliver: str = "local",
) -> dict[str, Any]:
    """创建新定时任务"""
    now = _now()
    next_run, first_run, schedule_type = _parse_schedule(schedule, now)
    if next_run is None:
        raise ValueError(f"Cannot parse schedule: {schedule}")

    jobs = load_jobs()
    for j in jobs:
        if j.get("name") == name:
            raise ValueError(f"Job '{name}' already exists. Delete it first.")

    job = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "schedule": schedule,
        "schedule_type": schedule_type,
        "prompt": prompt,
        "deliver": deliver,
        "created_at": now.isoformat(),
        "next_run_at": next_run.isoformat(),
        "last_run_at": None,
        "enabled": True,
    }
    jobs.append(job)
    save_jobs(jobs)
    logger.info("Cron job created: %s (next run: %s)", name, next_run)
    return job


def delete_job(name: str) -> bool:
    jobs = load_jobs()
    before = len(jobs)
    jobs = [j for j in jobs if j.get("name") != name]
    if len(jobs) == before:
        return False
    save_jobs(jobs)
    return True


def get_due_jobs(now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """返回已到期的任务"""
    if now is None:
        now = _now()
    jobs = load_jobs()
    due = []
    for job in jobs:
        if not job.get("enabled", True):
            continue
        next_str = job.get("next_run_at")
        if not next_str:
            continue
        try:
            next_run = datetime.fromisoformat(next_str)
        except (ValueError, TypeError):
            continue
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=now.tzinfo)
        if next_run <= now:
            due.append(job)
    return due


def advance_next_run(job: dict[str, Any], now: Optional[datetime] = None) -> dict[str, Any]:
    """执行后更新 next_run_at"""
    if now is None:
        now = _now()
    job["last_run_at"] = now.isoformat()

    schedule_type = job.get("schedule_type", "")
    schedule = job.get("schedule", "")

    if schedule_type == "oneshot":
        job["enabled"] = False
        job["next_run_at"] = None
    elif schedule_type == "interval":
        m = re.match(r'^(?:every\s+)?(\d+)\s*(m|h|d)$', schedule, re.IGNORECASE)
        if m:
            value = int(m.group(1))
            unit = m.group(2).lower()
            deltas = {"m": timedelta(minutes=value), "h": timedelta(hours=value), "d": timedelta(days=value)}
            job["next_run_at"] = (now + deltas.get(unit, timedelta(minutes=value))).isoformat()
    elif schedule_type == "cron" and HAS_CRONITER:
        try:
            cron = croniter(schedule, now)
            job["next_run_at"] = cron.get_next(datetime).isoformat()
        except (ValueError, KeyError):
            pass

    return job


def mark_job_run(name: str, now: Optional[datetime] = None) -> None:
    """标记任务已执行并持久化"""
    jobs = load_jobs()
    for job in jobs:
        if job.get("name") == name:
            advance_next_run(job, now)
            break
    save_jobs(jobs)


def save_job_output(name: str, result_text: str, run_at: Optional[datetime] = None) -> str:
    """保存任务输出到磁盘，返回文件路径"""
    if run_at is None:
        run_at = _now()
    _ensure_dirs()
    output_dir = OUTPUT_DIR / name
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = run_at.strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"{ts}.md"
    output_file.write_text(
        f"# {name}\n\n**Run at:** {run_at.isoformat()}\n\n"
        f"**Result:**\n\n{result_text}",
        encoding="utf-8",
    )
    return str(output_file)


async def run_job_now(name: str, job: dict[str, Any] | None = None) -> dict[str, Any]:
    """立即执行任务。使用 SimpleAgent（异步）。

    先标记任务已运行（更新 next_run_at），再执行 prompt，
    防止下一个 tick 周期重复触发同一 job。

    Args:
        name: 任务名称
        job: 可选，调用方已加载的 job 对象，避免重复读文件导致的竞争。
    """
    # 如果调用方没有传入 job，从文件加载
    if job is None:
        jobs = load_jobs()
        for j in jobs:
            if j.get("name") == name:
                job = j
                break
    if not job:
        logger.warning("Job '%s' not found in jobs file, skipping", name)
        return {"job": name, "result": "", "output_file": "", "skipped": True}

    now = _now()

    # 先标记为已运行，推进 next_run_at，避免并发重复执行
    mark_job_run(name, now)

    from ..agents.simple import SimpleAgent
    from ..config import get_model_config

    model_cfg = get_model_config()
    agent = SimpleAgent(
        model=model_cfg["model"],
        base_url=model_cfg["base_url"],
        api_key=model_cfg["api_key"],
        api_mode=model_cfg["api_mode"],
    )
    result = await agent.run(job.get("prompt", ""))

    output_file = save_job_output(name, result.get("final_response", ""), now)

    return {
        "job": name,
        "result": result.get("final_response", ""),
        "output_file": output_file,
    }
