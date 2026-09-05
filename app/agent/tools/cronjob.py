"""Cronjob 工具 — 创建、列出、删除、触发定时任务。

使用 app/services/cron_service.py 进行 DB 级任务管理。
"""

from __future__ import annotations

import json
import logging

from app.agent.tools.base import Tool, ToolParam

logger = logging.getLogger(__name__)


class Cronjob(Tool):
    """定时任务管理"""

    name = "cronjob"
    description = (
        "Manage scheduled (cron) tasks. Create recurring or one-shot jobs "
        "that execute prompts at specified times. "
        "Schedule formats: '*/5 * * * *' (cron), '30m' / 'every 2h' (interval), "
        "'2026-05-18T14:00' (one-shot). "
        "Actions: list, create, delete, run."
    )

    parameters = [
        ToolParam("action", str, "Action: list, create, delete, run."),
        ToolParam("name", str, "Job name.", default="", required=False),
        ToolParam("schedule", str, "Cron expression, interval, or ISO datetime.", default="", required=False),
        ToolParam("prompt", str, "Prompt to execute when triggered.", default="", required=False),
    ]

    async def call(self, arguments: dict) -> dict:
        action = arguments.get("action", "")
        name = arguments.get("name", "")
        schedule = arguments.get("schedule", "")
        prompt = arguments.get("prompt", "")

        # 获取当前 user_id
        from app.services.cron_service import _current_user_id
        user_id = _current_user_id.get()

        if action == "list":
            from app.services.cron_service import list_jobs as svc_list
            jobs = svc_list(user_id)
            return {
                "is_error": False,
                "output": json.dumps({"jobs": jobs, "count": len(jobs)}, ensure_ascii=False),
            }

        elif action == "create":
            if not name:
                return {"is_error": True, "message": "name is required for 'create'."}
            if not schedule:
                return {"is_error": True, "message": "schedule is required for 'create'."}
            if not prompt:
                return {"is_error": True, "message": "prompt is required for 'create'."}
            try:
                from app.services.cron_service import create_job as svc_create
                job = svc_create(user_id, name, schedule, prompt)
                # 广播创建事件
                await _notify("cron_job_created", job)
                return {
                    "is_error": False,
                    "output": json.dumps({"success": True, "job": job}, ensure_ascii=False),
                }
            except ValueError as e:
                return {"is_error": True, "message": str(e)}

        elif action == "delete":
            if not name:
                return {"is_error": True, "message": "name is required for 'delete'."}
            # 按名称查找 job_id
            from app.services.cron_service import list_jobs as svc_list, delete_job as svc_delete
            jobs = svc_list(user_id)
            target = next((j for j in jobs if j["name"] == name), None)
            if not target:
                return {"is_error": True, "message": f"Job not found: {name}"}
            ok = svc_delete(target["id"], user_id)
            if ok:
                await _notify("cron_job_deleted", {"job_id": target["id"]})
                return {"is_error": False, "output": json.dumps({"success": True, "message": f"Deleted job '{name}'."}, ensure_ascii=False)}
            return {"is_error": True, "message": f"Failed to delete job: {name}"}

        elif action == "run":
            if not name:
                return {"is_error": True, "message": "name is required for 'run'."}
            from app.services.cron_service import list_jobs as svc_list, execute_job as svc_exec
            jobs = svc_list(user_id)
            target = next((j for j in jobs if j["name"] == name), None)
            if not target:
                return {"is_error": True, "message": f"Job not found: {name}"}
            await _notify("cron_run_started", {"job_id": target["id"], "name": name})
            result = await svc_exec(target["id"], user_id, target["prompt"], name)
            if result.get("status") == "completed":
                await _notify("cron_run_completed", {
                    "job_id": target["id"], "run_id": result.get("run_id"),
                    "name": name, "output_summary": result.get("output_summary", ""),
                })
            else:
                await _notify("cron_run_failed", {
                    "job_id": target["id"], "run_id": result.get("run_id"),
                    "name": name, "error_message": result.get("error_message", ""),
                })
            return {"is_error": False, "output": json.dumps(result, ensure_ascii=False, default=str)}

        return {"is_error": True, "message": f"Unknown action '{action}'. Use: list, create, delete, run."}


async def _notify(event: str, data: dict) -> None:
    """通过 agent_manager 广播 cron 事件。"""
    try:
        from app.services.agent_manager import agent_manager
        from app.services.cron_service import _current_user_id
        user_id = _current_user_id.get()
        if user_id:
            await agent_manager.broadcast_cron_event(user_id, event, data)
    except Exception:
        logger.debug("Failed to broadcast cron event via agent_manager")
