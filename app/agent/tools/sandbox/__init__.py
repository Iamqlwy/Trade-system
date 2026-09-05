"""
沙箱模块 — 为 Shell 工具提供 Docker 容器级隔离执行环境。

Docker 容器沙箱是强制性的，提供：
  - 文件系统只读隔离（根文件系统只读，仅工作区可写）
  - 资源限制（CPU、内存、进程数）
  - 网络隔离（--network=none）
  - 环境变量清洗（仅白名单变量）
  - 用户隔离（非 root 运行）

注意：Docker 必须可用，否则 Shell 工具将拒绝执行。
"""

from .config import SandboxConfig, SandboxResult
from .manager import SandboxManager

__all__ = ["SandboxConfig", "SandboxResult", "SandboxManager"]
