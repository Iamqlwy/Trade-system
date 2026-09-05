"""文件 Patch 工具（简单 find/replace）

来自 simple-agent/tools/file.py: patch_tool — 简单的查找替换，仅替换第一次出现。
与 StrReplaceFile 类似但更轻量，是函数式接口。
"""

from __future__ import annotations

from pathlib import Path

from ..base import tool_error, tool_result
from ..security import resolve_path, check_write_path


def patch_tool(filepath: str, find: str, replace: str) -> str:
    """在文件中替换精确匹配的文本（仅第一次出现）"""
    if not filepath:
        return tool_error("filepath is required.")
    if not find:
        return tool_error("find text is required.")

    work_dir = Path.cwd()
    path = resolve_path(filepath, work_dir)

    err = check_write_path(path, work_dir)
    if err:
        return tool_error(err)

    if not path.exists():
        return tool_error(f"File not found: {filepath}")

    try:
        original = path.read_text(encoding="utf-8")
    except Exception as e:
        return tool_error(str(e))

    if find not in original:
        return tool_error("Find text not found in file. Ensure exact whitespace match.")

    updated = original.replace(find, replace, 1)
    try:
        path.write_text(updated, encoding="utf-8")
        return tool_result(success=True, filepath=filepath)
    except Exception as e:
        return tool_error(str(e))

