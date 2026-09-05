"""Cron 调度器 — 异步轮询到期任务并执行。

数据库驱动，支持多用户隔离和 WebSocket 实时推送。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class CronScheduler:
    """异步定时任务调度器"""

    def __init__(self, tick_interval: int = 60):
        self.tick_interval = tick_interval
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Cron scheduler started (interval=%ds)", self.tick_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Cron scheduler stopped")

    async def tick(self) -> None:
        """检查到期任务并执行，通过 WebSocket 推送事件。"""
        from app.services.cron_service import get_due_jobs, mark_job_run, execute_job

        due = get_due_jobs()

        if not due:
            return

        logger.info("Cron tick: %d due job(s)", len(due))

        for job in due:
            job_id = job["id"]
            user_id = job["user_id"]
            name = job.get("name", "unknown")
            prompt = job.get("prompt", "")

            # ── 权限检查：用户是否仍有定时任务权限 ──
            if not _user_has_cron_permission(user_id):
                logger.warning(
                    "Cron job '%s' skipped: user %d lost can_use_cron permission",
                    name, user_id,
                )
                mark_job_run(job_id)  # 推进 next_run 防止反复检查
                continue

            # 广播：任务被触发
            await _broadcast_cron_event(user_id, "cron_job_triggered", {
                "job_id": job_id,
                "name": name,
            })

            # 广播：开始执行
            await _broadcast_cron_event(user_id, "cron_run_started", {
                "job_id": job_id,
                "name": name,
            })

            # 先推进 next_run（防止 tick 重复触发）
            mark_job_run(job_id)

            logger.info("Cron job '%s' starting (user=%d)", name, user_id)
            try:
                result = await execute_job(job_id, user_id, prompt, name)

                if result.get("status") == "completed":
                    logger.info("Cron job '%s' completed: %s", name, result.get("output_file", ""))
                    await _broadcast_cron_event(user_id, "cron_run_completed", {
                        "job_id": job_id,
                        "run_id": result.get("run_id"),
                        "name": name,
                        "output_summary": result.get("output_summary", ""),
                    })
                else:
                    logger.error("Cron job '%s' failed: %s", name, result.get("error_message", ""))
                    await _broadcast_cron_event(user_id, "cron_run_failed", {
                        "job_id": job_id,
                        "run_id": result.get("run_id"),
                        "name": name,
                        "error_message": result.get("error_message", ""),
                    })
            except Exception as e:
                logger.exception("Cron job '%s' exception: %s", name, e)

    async def _loop(self) -> None:
        logger.info("Cron scheduler loop started")
        tick_count = 0
        while self._running:
            try:
                await self.tick()
                tick_count += 1
                if tick_count % 10 == 0:
                    logger.debug("Cron scheduler alive: %d ticks completed", tick_count)
            except asyncio.CancelledError:
                logger.info("Cron scheduler loop cancelled after %d ticks", tick_count)
                break
            except Exception:
                logger.exception("Cron tick error (tick #%d)", tick_count)
            await asyncio.sleep(self.tick_interval)
        logger.info("Cron scheduler loop exited after %d ticks", tick_count)


async def _broadcast_cron_event(user_id: int, event: str, data: dict) -> None:
    """向指定用户的所有 WebSocket 连接广播 cron 事件。"""
    try:
        from app.services.agent_manager import agent_manager
        await agent_manager.broadcast_cron_event(user_id, event, data)
    except Exception:
        logger.debug("Failed to broadcast cron event %s for user %d", event, user_id)


def _user_has_cron_permission(user_id: int) -> bool:
    """检查用户是否仍有定时任务权限（admin 始终通过）"""
    try:
        from app.auth.models import User
        from app.dependencies import repository
        session = repository.SessionLocal()
        try:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return False
            if user.role == "admin":
                return True
            return bool(user.can_use_cron) if user.can_use_cron is not None else True
        finally:
            session.close()
    except Exception:
        logger.exception("Failed to check cron permission for user %d", user_id)
        return True  # 查询失败时允许执行，避免误杀


# 模块级单例
_scheduler: CronScheduler | None = None


def get_scheduler() -> CronScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler


async def start_scheduler() -> CronScheduler:
    s = get_scheduler()
    if s._task and not s._task.done():
        logger.warning("Scheduler already running, skipping duplicate start")
        return s
    await s.start()
    return s


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None

