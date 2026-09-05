"""文件字符串替换工具

来自 code_agent/tools/file/replace.py — 精确字符串替换，支持单次或全部替换。
"""

from __future__ import annotations

from pathlib import Path

from ..base import Tool, ToolParam
from ..security import resolve_path, check_write_path


class StrReplaceFile(Tool):
    """精确字符串替换工具"""

    name = "StrReplaceFile"
    description = "Performs exact string replacements in a file. Supports single or multiple edits."
    parameters = [
        ToolParam("path", str, "The path to the file to edit."),
        ToolParam("old_str", str, "The old string to replace."),
        ToolParam("new_str", str, "The new string to replace with."),
        ToolParam("replace_all", bool, "Replace all occurrences.", default=False, required=False),
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
        old_str = arguments.get("old_str", "")
        new_str = arguments.get("new_str", "")
        replace_all = arguments.get("replace_all", False)

        if not path_str:
            return {"is_error": True, "message": "File path cannot be empty."}

        try:
            p = resolve_path(path_str, self._work_dir)

            # 安全检查（工作区边界 + 敏感路径）
            err = check_write_path(p, self._work_dir)
            if err:
                return {"is_error": True, "message": err}

            if not p.exists():
                return {"is_error": True, "message": f"`{path_str}` does not exist."}

            # 计划模式检查
            if self._plan_mode_checker and self._plan_mode_checker():
                plan_path = self._plan_file_getter and self._plan_file_getter()
                if plan_path and p != plan_path.resolve():
                    return {"is_error": True, "message": "Plan mode: only the plan file can be edited."}

            content = p.read_text(errors="replace")

            if replace_all:
                new_content = content.replace(old_str, new_str)
            else:
                new_content = content.replace(old_str, new_str, 1)

            if new_content == content:
                return {"is_error": True, "message": "No replacements made — old string not found."}

            p.write_text(new_content, errors="replace")
            count = content.count(old_str) if replace_all else 1
            return {"is_error": False, "message": f"File edited. {count} replacement(s) made."}
        except Exception as e:
            return {"is_error": True, "message": f"Failed to edit {path_str}: {e}"}
