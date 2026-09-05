"""Shell 工具 — 在 Docker 沙箱容器中异步执行 shell 命令。

安全由 Docker 容器沙箱保障（文件系统只读、资源限制、网络隔离、环境变量隔离），
不再做命令黑名单过滤 — 沙箱内执行任何命令都是安全的。

功能：
  - Docker 容器隔离执行（每命令一个容器）
  - 超时保护 (默认 60s, 最大 5min)
  - stdout + stderr 合并输出
  - Docker 不可用时拒绝执行（无降级）
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.agent.tools.base import Tool, ToolParam
from app.agent.tools.security import DEFAULT_EXTRA_READ_DIRS

logger = logging.getLogger(__name__)

MAX_TIMEOUT = 5 * 60  # 5 minutes


class Shell(Tool):
    name = "Shell"
    description = (
        "Executes a shell command inside a sandboxed Docker container. "
        "Returns stdout + stderr output and exit code. "
        f"Timeout: {MAX_TIMEOUT}s max. "
        "Use for any CLI operation."
    )

    def __init__(
        self,
        work_dir: Path | None = None,
        user_id: int = 0,
        session_id: str = "",
    ):
        self._work_dir = work_dir or Path.cwd()
        self._user_id = user_id
        self._session_id = session_id

        # 初始化沙箱管理器（强制 Docker，无 fallback）
        from .sandbox import SandboxManager, SandboxConfig
        from ...config import settings

        self._sandbox = SandboxManager(SandboxConfig(
            work_dir=self._work_dir.resolve(),
            user_id=user_id,
            session_id=session_id,
            docker_image=settings.shell_sandbox_image,
            max_memory_mb=settings.shell_sandbox_max_memory_mb,
            max_cpus=settings.shell_sandbox_max_cpus,
            max_pids=settings.shell_sandbox_max_pids,
            # 网络策略：只允许通过 host.docker.internal 访问宿主机后端
            # 沙箱内可用 BACKEND_URL 环境变量访问后端 API
            backend_url=f"http://host.docker.internal:{settings.api_port}",
            extra_read_dirs=list(DEFAULT_EXTRA_READ_DIRS),
        ))

    parameters = [
        ToolParam("command", str, "The command to execute."),
        ToolParam("timeout", int, f"Timeout in seconds (max {MAX_TIMEOUT}s).", default=60, required=False),
        ToolParam("description", str, "Short description of what the command does.", default="", required=False),
    ]

    async def call(self, arguments: dict) -> dict:
        command = arguments.get("command", "")
        timeout = min(arguments.get("timeout", 60), MAX_TIMEOUT)

        if not command:
            return {"is_error": True, "message": "Command cannot be empty."}

        # Docker 沙箱执行 — 安全由容器隔离保障
        try:
            result = await self._sandbox.execute(command, timeout)

            if result.timed_out:
                return {"is_error": True, "message": f"Command timed out after {timeout}s."}

            output = result.stdout
            if result.stderr.strip():
                output += "\n[stderr]\n" + result.stderr

            backend_tag = f" [{result.sandbox_backend}]"

            if result.exit_code == 0:
                return {
                    "is_error": False,
                    "message": f"Command succeeded (exit code 0).{backend_tag}",
                    "output": output,
                }
            else:
                return {
                    "is_error": True,
                    "message": f"Command failed (exit code {result.exit_code}).{backend_tag}",
                    "output": output,
                }

        except Exception as e:
            exc_type = type(e).__name__
            exc_msg = str(e) or repr(e)
            logger.exception("Shell 沙箱执行失败: command=%s", command[:100])
            return {"is_error": True, "message": f"Sandbox execution failed: [{exc_type}] {exc_msg}"}
