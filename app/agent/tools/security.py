"""工具安全策略 — 路径沙箱

所有工具的路径检查逻辑集中在此模块，
避免各工具各自实现导致遗漏。

Shell 命令不做黑名单过滤 — 安全完全由 Docker 容器沙箱保障
（文件系统只读、资源限制、网络隔离）。

安全原则：
  - Read:  仅允许工作区 + 额外白名单目录（如 C:/klines）
  - Write: 仅允许工作区内，额外阻止敏感路径
"""

from __future__ import annotations

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# 默认额外可读目录（工作区之外）
# ---------------------------------------------------------------------------

DEFAULT_EXTRA_READ_DIRS: list[Path] = [
    Path("C:/klines"),
]


# ---------------------------------------------------------------------------
# 路径沙箱
# ---------------------------------------------------------------------------

def map_container_path(path_str: str, work_dir: Path | None = None) -> str:
    """将沙箱容器内路径透明映射回宿主机路径。

    Docker 沙箱将工作区挂载为 /workspace，额外只读目录挂载为 /data/<name>。
    模型看到容器内路径后可能将其传给宿主机端的文件工具，这里自动转换。
    """
    s = path_str.strip().replace("\\", "/")
    wd = work_dir or Path.cwd()

    # 剥离误加的盘符前缀（如 C:/workspace/... — Windows 上模型常见的幻觉形态）
    if len(s) >= 2 and s[1] == ":" and s[0].isalpha():
        rest = s[2:]
        if rest == "/workspace" or rest.startswith(("/workspace/", "/data/")):
            s = rest

    if s in ("/workspace", "/workspace/"):
        return str(wd)
    if s.startswith("/workspace/"):
        return str(wd / s[len("/workspace/"):])

    if s.startswith("/data/"):
        rest = s[len("/data/"):]
        top, _, tail = rest.partition("/")
        for d in DEFAULT_EXTRA_READ_DIRS:
            if d.name == top:
                return str(d / tail) if tail else str(d)

    # 相对形式 data/<name>/... 同样映射（模型在容器 /workspace 下看到的相对路径）
    rel = s[2:] if s.startswith("./") else s
    if rel.startswith("data/"):
        rest = rel[len("data/"):]
        top, _, tail = rest.partition("/")
        for d in DEFAULT_EXTRA_READ_DIRS:
            if d.name == top:
                return str(d / tail) if tail else str(d)

    return path_str


def resolve_path(path_str: str, work_dir: Path | None = None) -> Path:
    """统一路径解析：展开 ~ 和相对路径，返回 resolved 绝对路径。

    容器内路径（/workspace、/data/<name>）会先映射回宿主机路径。
    """
    path_str = map_container_path(path_str, work_dir)
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = (work_dir or Path.cwd()) / p
    return p.resolve()


def is_within_dirs(path: Path, allowed_dirs: list[Path]) -> bool:
    """检查 resolved path 是否在任一允许目录内。

    使用字符串前缀匹配（resolved 路径已消除 .. 和符号链接）。
    """
    path_str = str(path).lower()
    for d in allowed_dirs:
        dir_str = str(d.resolve()).lower()
        # 路径完全等于目录，或以目录 + 分隔符开头
        if path_str == dir_str or path_str.startswith(dir_str + os.sep):
            return True
    return False


def check_read_path(
    path: Path,
    work_dir: Path,
    extra_dirs: list[Path] | None = None,
) -> str | None:
    """检查读取路径是否被允许。

    返回 None = 通过，返回 str = 错误消息。
    """
    allowed = [work_dir.resolve()]
    if extra_dirs:
        allowed.extend(d.resolve() for d in extra_dirs)

    # 设备文件
    if str(path).startswith("/dev/"):
        return "Cannot read device files."

    if not is_within_dirs(path, allowed):
        allowed_desc = ", ".join(str(d) for d in allowed)
        return (
            f"Blocked: read path `{path}` is outside allowed directories. "
            f"Allowed: {allowed_desc}"
        )
    return None


# 敏感路径（不允许写入）
SENSITIVE_PATHS = [
    ".ssh", ".aws", ".kube", ".gcp", ".env", ".gitconfig",
    ".npmrc", ".pypirc", ".netrc", "id_rsa", "authorized_keys",
    ".claude",  # Claude 配置
    ".git",     # Git 仓库元数据
]


def check_write_path(
    path: Path,
    work_dir: Path,
) -> str | None:
    """检查写入路径是否被允许（工作区内 + 非敏感路径）。

    返回 None = 通过，返回 str = 错误消息。
    """
    resolved = path.resolve()
    work_resolved = work_dir.resolve()

    # 必须在工作区内
    if not is_within_dirs(resolved, [work_resolved]):
        return (
            f"Blocked: write path `{resolved}` is outside workspace `{work_resolved}`. "
            f"Writing outside workspace is not allowed."
        )

    path_lower = str(resolved).lower()

    # 敏感路径
    for sensitive in SENSITIVE_PATHS:
        if f"{os.sep}{sensitive}" in path_lower or path_lower.endswith(f"{os.sep}{sensitive}"):
            return f"Blocked: cannot write to sensitive path containing '{sensitive}'."

    # 阻止写入系统目录
    etc_dir = f"{os.sep}etc{os.sep}"
    etc_win = "\\etc\\"
    if str(resolved).startswith("/etc/") or etc_dir in str(resolved) or etc_win in str(resolved):
        return "Blocked: cannot write to /etc/."

    return None
