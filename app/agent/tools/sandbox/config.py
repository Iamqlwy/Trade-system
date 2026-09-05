"""
沙箱配置和数据结构。
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SandboxConfig:
    """沙箱配置"""
    work_dir: Path                              # 用户工作区（挂载到容器 /workspace）
    user_id: int = 0                            # 用户 ID（用于日志/审计）
    session_id: str = ""                        # 会话 ID

    # Docker 配置
    docker_image: str = "quant-sandbox:latest"        # 沙箱镜像（预装 Python 3.13 + 量化库）

    # 资源限制
    max_memory_mb: int = 512                    # 内存上限（MB）
    max_cpus: float = 1.0                       # CPU 核心数
    max_pids: int = 128                          # 进程数上限
    timeout: int = 300                          # 默认超时（秒）

    # 网络：只允许访问后端 API，而非完全隔离
    # 当 backend_url 非空时，容器可通过 host.docker.internal 访问宿主机后端
    # 当 backend_url 为空时，完全无网络（--network=none）
    backend_url: str = ""                       # 后端 API 地址，如 http://host.docker.internal:8000

    # 文件系统
    extra_read_dirs: list[Path] = field(default_factory=list)  # 额外只读挂载

    # 环境变量（传递给容器的白名单）
    safe_env_vars: dict[str, str] = field(default_factory=lambda: {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "OPENBLAS_NUM_THREADS": "1",    # 限制 numpy/OpenBLAS 线程数
        "OMP_NUM_THREADS": "1",         # 限制 OpenMP 线程数
        "MPLCONFIGDIR": "/tmp/matplotlib",  # matplotlib 配置目录（/tmp 可写）
    })


@dataclass
class SandboxResult:
    """沙箱执行结果"""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    sandbox_backend: str    # "docker" | "fallback"

