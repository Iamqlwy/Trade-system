"""Glob 文件匹配工具

来自 code_agent/tools/file/glob.py — 按 glob 模式查找文件，按修改时间排序。
"""

from __future__ import annotations

from pathlib import Path

from ..base import Tool, ToolParam


class Glob(Tool):
    """Glob 文件匹配"""

    name = "Glob"
    description = "Finds files matching a glob pattern. Returns relative paths sorted by modification time."
    parameters = [
        ToolParam("pattern", str, "The glob pattern (e.g., '**/*.py', 'src/**/*.ts')."),
    ]

    def __init__(self, work_dir: Path | None = None):
        self._work_dir = (work_dir or Path.cwd()).resolve()

    def _normalize_pattern(self, pattern: str) -> str:
        """将容器内/绝对路径形式的 pattern 转为相对于工作区的 pattern。

        模型可能传入 /workspace/**/*.py（沙箱容器路径）或宿主机绝对路径，
        Path.glob 不支持绝对 pattern，这里透明转换。
        """
        p = pattern.strip().replace("\\", "/")

        if p in ("/workspace", "/workspace/"):
            return "**/*"
        if p.startswith("/workspace/"):
            p = p[len("/workspace/"):]

        # 宿主机工作区绝对路径 → 相对 pattern
        wd = str(self._work_dir).replace("\\", "/").rstrip("/")
        if p.lower().startswith(wd.lower() + "/"):
            p = p[len(wd) + 1:]
        elif p.lower() == wd.lower():
            return "**/*"

        # 残余的绝对形式（如 /app/**/*.py）按工作区相对处理
        if len(p) > 1 and p[1] == ":":
            p = p[2:]
        return p.lstrip("/")

    async def call(self, arguments: dict) -> dict:
        pattern = arguments.get("pattern", "")
        if not pattern:
            return {"is_error": True, "message": "Pattern cannot be empty."}

        pattern = self._normalize_pattern(pattern)
        if not pattern:
            pattern = "**/*"

        try:
            work_dir = Path(self._work_dir)
            matches = sorted(
                work_dir.glob(pattern),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            paths = [str(m.relative_to(work_dir)) for m in matches if m.is_file()]
            if not paths:
                return {"is_error": False, "message": "No files matched.", "output": "(no matches)"}

            output_lines = paths[:500]
            output = "\n".join(output_lines)
            msg = f"Found {len(paths)} file(s)."
            if len(paths) > 500:
                msg += " Showing first 500."
            return {"is_error": False, "message": msg, "output": output}
        except Exception as e:
            return {"is_error": True, "message": f"Glob failed: {e}"}
