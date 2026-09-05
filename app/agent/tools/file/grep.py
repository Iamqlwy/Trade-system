"""Grep 文件内容搜索工具

合并自：
  - code_agent/tools/file/grep.py: Grep（Python re 实现）
  - simple-agent/tools/file.py: search_files_tool（ripgrep + re fallback）
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..base import Tool, ToolParam, tool_error, tool_result
from ..security import resolve_path, is_within_dirs


class Grep(Tool):
    """正则搜索文件内容"""

    name = "Grep"
    description = "Searches files for a regex pattern. Returns matching lines with file paths."
    parameters = [
        ToolParam("pattern", str, "The regex pattern to search for."),
        ToolParam("path", str, "Directory or file to search in.", default=".", required=False),
        ToolParam("glob", str, "Optional glob filter (e.g., '*.py').", default="", required=False),
        ToolParam("output_mode", str, "'content', 'files_with_matches', or 'count'.",
                  default="files_with_matches", required=False),
        ToolParam("-i", bool, "Case insensitive search.", default=False, required=False),
        ToolParam("head_limit", int, "Max results to return.", default=100, required=False),
    ]

    def __init__(self, work_dir: Path | None = None):
        self._work_dir = (work_dir or Path.cwd()).resolve()

    async def call(self, arguments: dict) -> dict:
        pattern = arguments.get("pattern", "")
        search_path = arguments.get("path", ".")
        glob_filter = arguments.get("glob", "")
        output_mode = arguments.get("output_mode", "files_with_matches")
        case_insensitive = arguments.get("-i", False)
        head_limit = arguments.get("head_limit", 100)

        if not pattern:
            return {"is_error": True, "message": "Pattern cannot be empty."}

        try:
            flags = re.IGNORECASE if case_insensitive else 0
            regex = re.compile(pattern, flags)

            base = resolve_path(search_path, self._work_dir)

            # 工作区边界检查
            if not is_within_dirs(base, [self._work_dir]):
                return {"is_error": True, "message": f"Blocked: search path `{base}` is outside workspace."}

            if base.is_file():
                files = [base]
            else:
                glob_pat = f"**/{glob_filter}" if glob_filter else "**/*"
                files = [f for f in base.glob(glob_pat) if f.is_file()]

            results: list[str] = []
            match_count = 0

            for f in files:
                if len(results) >= head_limit:
                    break
                try:
                    content = f.read_text(errors="replace")
                except (OSError, UnicodeDecodeError):
                    continue

                lines = content.split("\n")
                file_matches = []
                for i, line in enumerate(lines, 1):
                    if regex.search(line):
                        file_matches.append((i, line))
                        match_count += 1

                if file_matches:
                    rel = str(f.relative_to(self._work_dir))
                    if output_mode == "files_with_matches":
                        results.append(rel)
                    elif output_mode == "count":
                        results.append(f"{rel}: {len(file_matches)}")
                    else:
                        for line_no, line in file_matches[:head_limit - len(results)]:
                            results.append(f"{rel}:{line_no}: {line[:500]}")

            if not results:
                return {"is_error": False, "message": "No matches found.", "output": "(no matches)"}

            output = "\n".join(results[:head_limit])
            return {
                "is_error": False,
                "message": f"Found {match_count} match(es) in {len(results)} result(s).",
                "output": output,
            }
        except Exception as e:
            return {"is_error": True, "message": f"Grep failed: {e}"}


# ---------------------------------------------------------------------------
# 函数式接口（带 ripgrep 加速）
# ---------------------------------------------------------------------------

def search_files_tool(
    pattern: str,
    path_str: str | None = None,
    glob: str | None = None,
) -> str:
    """使用 ripgrep 搜索文件（Python re fallback）"""
    if not pattern:
        return tool_error("pattern is required.")

    search_dir = resolve_path(path_str, Path.cwd()) if path_str else Path.cwd()
    if not search_dir.exists():
        return tool_error(f"Directory not found: {path_str}")

    # 工作区边界检查
    work_dir = Path.cwd().resolve()
    if not is_within_dirs(search_dir, [work_dir]):
        return tool_error(f"Blocked: search path is outside workspace.")

    # 优先使用 ripgrep
    try:
        cmd = ["rg", "--line-number", "--no-heading", "--color=never"]
        if glob:
            cmd.extend(["--glob", glob])
        cmd.extend([pattern, str(search_dir)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        if not output:
            return tool_result(matches=[], count=0)
        lines = output.split("\n")[:200]
        return tool_result({
            "matches": lines,
            "count": len(lines),
            "note": f"Showing first {len(lines)} matches" if len(lines) >= 200 else None,
        })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Python re fallback
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return tool_error(f"Invalid regex: {e}")

    from fnmatch import fnmatch
    from .read import BINARY_EXTENSIONS

    matches: list[str] = []
    for root, dirs, files in __import__("os").walk(str(search_dir)):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if glob and not fnmatch(fname, glob):
                continue
            fpath = Path(root) / fname
            if fpath.suffix.lower() in BINARY_EXTENSIONS:
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
            except Exception:
                continue
            for i, line in enumerate(content.split("\n"), 1):
                if regex.search(line):
                    matches.append(f"{fpath}:{i}: {line.strip()[:200]}")
                    if len(matches) >= 200:
                        break
            if len(matches) >= 200:
                break

    return tool_result(matches=matches, count=len(matches))

