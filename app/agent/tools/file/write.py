"""文件写入工具

合并自：
  - code_agent/tools/file/write.py: WriteFile（计划模式支持）
  - simple-agent/tools/file.py: write_file_tool（敏感路径保护、符号链接检查）
"""

from __future__ import annotations

from pathlib import Path

from ..base import Tool, ToolParam, tool_error, tool_result
from ..security import resolve_path, check_write_path as _check_write_path_sec


class WriteFile(Tool):
    """文件写入工具 — 支持覆盖和追加模式"""

    name = "WriteFile"
    description = "Writes a file to the local filesystem. Creates parent directories if needed."
    parameters = [
        ToolParam("path", str, "The path to write to."),
        ToolParam("content", str, "The content to write."),
        ToolParam("mode", str, "Write mode: 'overwrite' or 'append'.", default="overwrite", required=False),
    ]

    def __init__(self, work_dir: Path | None = None):
        self._work_dir = (work_dir or Path.cwd()).resolve()
        self._plan_mode_checker = None
        self._plan_file_getter = None

    def bind_plan_mode(self, checker, path_getter):
        self._plan_mode_checker = checker
        self._plan_file_getter = path_getter

    async def call(self, arguments: dict) -> dict:
        path_str = arguments.get("path", "")
        content = arguments.get("content", "")
        mode = arguments.get("mode", "overwrite")

        if not path_str:
            return {"is_error": True, "message": "File path cannot be empty."}

        try:
            p = resolve_path(path_str, self._work_dir)

            # 安全检查（工作区边界 + 敏感路径）
            err = _check_write_path_sec(p, self._work_dir)
            if err:
                return {"is_error": True, "message": err}

            # 计划模式检查
            if self._plan_mode_checker and self._plan_mode_checker():
                plan_path = self._plan_file_getter and self._plan_file_getter()
                if plan_path and p != plan_path.resolve():
                    return {"is_error": True, "message": "Plan mode: only the plan file can be written."}

            # 阻止覆盖非普通文件
            if p.exists() and not p.is_file():
                return {"is_error": True, "message": f"Cannot overwrite non-regular file: {path_str}"}

            # 符号链接检查
            if p.is_symlink():
                resolved = p.resolve()
                if not str(resolved).startswith(str(Path.cwd())):
                    return {"is_error": True, "message": "Blocked: symlink points outside working directory."}

            p.parent.mkdir(parents=True, exist_ok=True)

            old_text = ""
            if mode == "append" and p.exists():
                old_text = p.read_text(errors="replace")

            if mode == "overwrite":
                p.write_text(content, errors="replace")
            else:
                p.write_text(old_text + content, errors="replace")

            size = p.stat().st_size
            action = "overwritten" if mode == "overwrite" else "appended to"
            return {"is_error": False, "message": f"File {action}. Size: {size} bytes."}
        except Exception as e:
            return {"is_error": True, "message": f"Failed to write {path_str}: {e}"}


# ---------------------------------------------------------------------------
# 函数式接口
# ---------------------------------------------------------------------------

def write_file_tool(filepath: str, content: str) -> str:
    """同步文件写入"""
    if not filepath:
        return tool_error("filepath is required.")

    work_dir = Path.cwd()
    path = resolve_path(filepath, work_dir)

    err = _check_write_path_sec(path, work_dir)
    if err:
        return tool_error(err)
    if path.exists() and not path.is_file():
        return tool_error(f"Cannot overwrite non-regular file: {filepath}")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return tool_result(success=True, filepath=filepath,
                          bytes_written=len(content.encode("utf-8")))
    except Exception as e:
        return tool_error(str(e))

