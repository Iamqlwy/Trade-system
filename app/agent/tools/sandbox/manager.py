"""
沙箱管理器 — Docker 容器是唯一沙箱后端（强制性）。

Docker 必须可用，否则系统拒绝执行命令。
"""

import logging
from .config import SandboxConfig, SandboxResult

logger = logging.getLogger(__name__)


class SandboxManager:
    """沙箱管理器（Docker only）"""

    def __init__(self, config: SandboxConfig):
        self._config = config
        self._backend = self._select_backend()
        logger.info(
            "沙箱初始化完成: backend=%s, sandboxed=%s, user=%d, session=%s",
            self._backend.name,
            self._backend.is_sandboxed,
            config.user_id,
            config.session_id[:16] if config.session_id else "",
        )

    def _select_backend(self):
        """选择沙箱后端 — Docker 是强制性的，不可降级"""
        from .docker import DockerSandbox

        if not DockerSandbox.is_available():
            raise RuntimeError(
                "Docker 不可用。Docker 沙箱是强制性的安全要求。"
                "请安装 Docker Desktop 或 Docker Engine 并确保其正在运行。"
            )

        return DockerSandbox(self._config)

    @property
    def backend_name(self) -> str:
        """当前后端名称"""
        return self._backend.name

    @property
    def is_sandboxed(self) -> bool:
        """是否真正沙箱化（Docker = True）"""
        return self._backend.is_sandboxed

    async def execute(self, command: str, timeout: int | None = None) -> SandboxResult:
        """在沙箱中执行命令"""
        timeout = timeout or self._config.timeout
        return await self._backend.execute(command, timeout)
