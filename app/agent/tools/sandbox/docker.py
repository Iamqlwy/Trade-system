"""
Docker 容器沙箱 — 使用 Docker 容器提供 OS 级隔离。

每个命令在独立容器中执行，提供：
- 文件系统隔离（根文件系统只读，仅工作区可写）
- 资源限制（内存、CPU、进程数）
- 网络隔离（自定义内部网络，只允许访问宿主机后端，阻止外部互联网）
- 环境变量隔离（仅白名单变量）
- 用户隔离（非 root 运行）

兼容性：使用 subprocess.run + asyncio.to_thread，兼容 Windows SelectorEventLoop。
"""

import asyncio
import logging
import subprocess
from pathlib import Path

from .config import SandboxConfig, SandboxResult

logger = logging.getLogger(__name__)

# 沙箱专用 Docker 网络：允许访问宿主机，但不路由到外部互联网
_SANDBOX_NETWORK = "quant-sandbox-net"


class DockerSandbox:
    """Docker 容器沙箱"""

    name = "docker"
    is_sandboxed = True

    def __init__(self, config: SandboxConfig):
        self._config = config
        # 确保工作区目录存在
        self._config.work_dir.mkdir(parents=True, exist_ok=True)
        # 确保沙箱网络存在（仅在需要网络时）
        if config.backend_url:
            self._ensure_network()

    @staticmethod
    def is_available() -> bool:
        """检测 Docker 是否可用"""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False

    @staticmethod
    def _ensure_network() -> None:
        """确保沙箱专用 Docker 网络存在

        Windows Docker Desktop 下，自定义桥接网络默认不具备外网路由能力（VM 隔离），
        容器仅能通过 host.docker.internal 访问宿主机，无法访问外部互联网。
        """
        try:
            result = subprocess.run(
                ["docker", "network", "ls", "--filter", f"name=^{_SANDBOX_NETWORK}$",
                 "--format", "{{.Name}}"],
                capture_output=True, timeout=5,
            )
            if _SANDBOX_NETWORK not in result.stdout.decode():
                subprocess.run(
                    ["docker", "network", "create", _SANDBOX_NETWORK],
                    capture_output=True, timeout=10,
                )
                logger.info("创建沙箱网络: %s", _SANDBOX_NETWORK)
        except Exception:
            logger.debug("创建沙箱网络失败，将使用默认网络", exc_info=True)

    async def execute(self, command: str, timeout: int) -> SandboxResult:
        """在 Docker 容器中执行命令

        使用 subprocess.run + asyncio.to_thread，兼容 Windows SelectorEventLoop。
        """
        docker_cmd = self._build_docker_command(command)

        logger.debug(
            "Docker 沙箱执行: user=%d, session=%s, cmd=%s",
            self._config.user_id,
            self._config.session_id[:16] if self._config.session_id else "",
            command[:100],
        )

        def _run_docker() -> tuple[int, bytes, bytes]:
            """在线程池中同步执行 docker 命令"""
            try:
                result = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    timeout=timeout + 10,  # 给 Docker 10s 额外时间
                )
                return result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                return -1, b"", b"Command timed out"
            except FileNotFoundError:
                raise RuntimeError("Docker 未安装或未运行")

        try:
            exit_code, stdout, stderr = await asyncio.to_thread(_run_docker)

            # 超时处理
            if exit_code == -1 and b"timed out" in stderr.lower():
                await self._cleanup_containers()
                return SandboxResult(
                    stdout="",
                    stderr="Command timed out",
                    exit_code=-1,
                    timed_out=True,
                    sandbox_backend="docker",
                )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Docker 自身失败（如镜像不存在、路径挂载失败等）
            if exit_code == 125 or exit_code == 126:
                raise RuntimeError(
                    f"Docker 启动失败 (exit={exit_code}): {stderr_str.strip() or '未知错误'}"
                )

            return SandboxResult(
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                timed_out=False,
                sandbox_backend="docker",
            )

        except RuntimeError:
            raise
        except Exception as e:
            logger.exception("Docker 沙箱执行失败")
            raise RuntimeError(f"Docker 执行异常: {type(e).__name__}: {e}")

    def _build_docker_command(self, command: str) -> list[str]:
        """构建 docker run 命令"""
        work_dir = self._config.work_dir

        docker_cmd = [
            "docker", "run",
            "--rm",                             # 执行完自动删除
            "--init",                           # 使用 init 进程（正确处理信号）

            # 资源限制
            f"--memory={self._config.max_memory_mb}m",
            f"--cpus={self._config.max_cpus}",
            f"--pids-limit={self._config.max_pids}",

            # 安全选项
            "--security-opt=no-new-privileges", # 禁止提权
            "--read-only",                      # 根文件系统只读
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=100m",
            "--tmpfs", "/var/tmp:rw,noexec,nosuid,size=50m",

            # 用户（非 root）
            "--user=1000:1000",

            # 工作目录
            "--workdir=/workspace",

            # 挂载工作区（可写）
            "-v", f"{work_dir}:/workspace:rw",
        ]

        # 网络配置：
        # - backend_url 为空 → 完全无网络（--network=none）
        # - backend_url 非空 → 使用沙箱专用网络 + host.docker.internal 访问宿主机后端
        if self._config.backend_url:
            docker_cmd.extend([
                f"--network={_SANDBOX_NETWORK}",
                "--add-host", "host.docker.internal:host-gateway",
            ])
        else:
            docker_cmd.append("--network=none")

        # 额外只读挂载
        for extra_dir in self._config.extra_read_dirs:
            if extra_dir.exists():
                # 挂载到简洁路径：C:/klines → /data/klines
                dir_name = extra_dir.name  # "klines"
                container_path = f"/data/{dir_name}"
                docker_cmd.extend(["-v", f"{extra_dir}:{container_path}:ro"])

        # 环境变量（白名单）
        for key, value in self._config.safe_env_vars.items():
            docker_cmd.extend(["-e", f"{key}={value}"])

        # 添加用户/会话标识（用于日志追踪）
        docker_cmd.extend(["-e", f"USER_ID={self._config.user_id}"])
        docker_cmd.extend(["-e", f"SESSION_ID={self._config.session_id}"])

        # 后端 API 地址（供沙箱内 curl/脚本访问后端）
        if self._config.backend_url:
            docker_cmd.extend(["-e", f"BACKEND_URL={self._config.backend_url}"])

        # 镜像
        docker_cmd.append(self._config.docker_image)

        # 执行的命令
        docker_cmd.extend(["bash", "-c", command])

        return docker_cmd

    def _to_container_path(self, path: Path) -> str:
        """将宿主机路径转换为容器内路径"""
        # 例如：C:/klines → /mnt/host/c/klines
        path_str = str(path).replace("\\", "/")

        # Windows 路径转换
        if len(path_str) >= 2 and path_str[1] == ":":
            drive = path_str[0].lower()
            rest = path_str[2:].lstrip("/")
            return f"/mnt/host/{drive}/{rest}"

        # Unix 路径直接使用
        return path_str

    async def _cleanup_containers(self):
        """清理可能残留的沙箱容器"""
        def _cleanup():
            try:
                result = subprocess.run(
                    ["docker", "ps", "-a", "-q",
                     "--filter", f"label=sandbox_session={self._config.session_id}"],
                    capture_output=True,
                    timeout=10,
                )
                if result.stdout.strip():
                    container_ids = result.stdout.decode().strip().split("\n")
                    for cid in container_ids:
                        if cid:
                            subprocess.run(
                                ["docker", "rm", "-f", cid],
                                capture_output=True,
                                timeout=10,
                            )
            except Exception:
                pass

        await asyncio.to_thread(_cleanup)

    @staticmethod
    async def pull_image(image: str) -> bool:
        """预拉取镜像（减少首次执行延迟）"""
        def _pull() -> bool:
            try:
                result = subprocess.run(
                    ["docker", "pull", image],
                    capture_output=True,
                    timeout=300,
                )
                return result.returncode == 0
            except Exception:
                return False

        return await asyncio.to_thread(_pull)
