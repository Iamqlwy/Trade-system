"""文件读取工具

合并自：
  - code_agent/tools/file/read.py: ReadFile（行号、限制、workspace 检查）
  - simple-agent/tools/file.py: read_file_tool（二进制检测、字符截断）
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

from ..base import Tool, ToolParam, tool_error, tool_result
from ..security import resolve_path, check_read_path


MAX_LINES = 1000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 100 << 10  # 100KB

logger = logging.getLogger(__name__)

# 二进制扩展名（不含图片，图片单独处理）
BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".pdf",
    ".pyc", ".pyo", ".class", ".o", ".obj", ".lib", ".a", ".db",
    ".sqlite", ".sqlite3", ".wasm",
}

# 图片扩展名 — 自动上传 OSS 并返回 URL
IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
}


def _is_binary(filepath: str | Path) -> bool:
    return Path(filepath).suffix.lower() in BINARY_EXTENSIONS


def _is_image(filepath: str | Path) -> bool:
    return Path(filepath).suffix.lower() in IMAGE_EXTENSIONS


class ReadFile(Tool):
    """文件读取工具 — 支持正向读取和尾部读取"""

    name = "ReadFile"
    description = (
        f"Reads a file from the local filesystem.\n\n"
        f"Max {MAX_LINES} lines, {MAX_LINE_LENGTH} chars per line, {MAX_BYTES} bytes total.\n"
        "Use line_offset and n_lines for large files. Negative offset reads from end."
    )
    parameters = [
        ToolParam("path", str, "The path to the file to read."),
        ToolParam("line_offset", int, "Line number to start from (1-based). Negative reads from end.", default=1, required=False),
        ToolParam("n_lines", int, f"Number of lines to read (max {MAX_LINES}).", default=MAX_LINES, required=False),
    ]

    def __init__(self, work_dir: Path | None = None, extra_read_dirs: list[Path] | None = None):
        self._work_dir = (work_dir or Path.cwd()).resolve()
        self._extra_read_dirs = [d.resolve() for d in (extra_read_dirs or [])]

    async def call(self, arguments: dict) -> dict:
        path_str = arguments.get("path", "")
        line_offset = arguments.get("line_offset", 1)
        n_lines = min(arguments.get("n_lines", MAX_LINES), MAX_LINES)

        if not path_str:
            return {"is_error": True, "message": "File path cannot be empty."}

        try:
            p = resolve_path(path_str, self._work_dir)

            # 路径沙箱检查
            err = check_read_path(p, self._work_dir, self._extra_read_dirs)
            if err:
                return {"is_error": True, "message": err}

            if not p.exists():
                return {"is_error": True, "message": f"`{path_str}` does not exist."}
            if not p.is_file():
                return {"is_error": True, "message": f"`{path_str}` is not a file."}

            # 图片文件 — 上传 OSS 并返回 URL，让 LLM 能"看到"图片
            if _is_image(p):
                return await self._read_image(p, path_str)

            if _is_binary(p):
                return {"is_error": True, "message": f"Cannot read binary file: {path_str}"}

            if line_offset < 0:
                return await self._read_tail(p, abs(line_offset), n_lines)
            else:
                return await self._read_forward(p, line_offset, n_lines)
        except Exception as e:
            return {"is_error": True, "message": f"Failed to read {path_str}: {e}"}

    async def _read_image(self, p: Path, path_str: str) -> dict:
        """处理图片文件：上传到 OSS，返回公网 URL 供 LLM 查看。"""
        file_size = p.stat().st_size
        try:
            from ...utils.oss import ensure_public_url, _is_oss_available
            if not _is_oss_available():
                return {
                    "is_error": False,
                    "message": f"Image file: {path_str} ({file_size} bytes). OSS not configured, cannot display image.",
                    "output": f"[Image file: {path_str} — OSS not configured]",
                }
            url = ensure_public_url(str(p))
            return {
                "is_error": False,
                "message": f"Image file: {path_str} ({file_size} bytes). Uploaded to OSS successfully.",
                "output": "",
                "images": [{"url": url, "filename": p.name}],
            }
        except Exception as e:
            logger.warning("Failed to upload image to OSS: %s", e)
            return {
                "is_error": False,
                "message": f"Image file: {path_str} ({file_size} bytes). OSS upload failed: {e}",
                "output": f"[Image file: {path_str} — upload failed: {e}]",
            }

    async def _read_forward(self, p: Path, start: int, n_lines: int) -> dict:
        lines: list[str] = []
        total_lines = 0
        n_bytes = 0
        truncated = False

        with open(p, errors="replace") as f:
            for i, line in enumerate(f, 1):
                total_lines = i
                if i < start:
                    continue
                if len(lines) >= n_lines:
                    break
                line = line[:MAX_LINE_LENGTH]
                lines.append(line)
                n_bytes += len(line.encode())
                if n_bytes >= MAX_BYTES:
                    truncated = True
                    break

        output = "".join(f"{start + j:6d}\t{line}" for j, line in enumerate(lines))
        msg = f"{len(lines)} lines read (total: {total_lines})."
        if truncated:
            msg += " Truncated due to size limit."
        return {"is_error": False, "message": msg, "output": output}

    async def _read_tail(self, p: Path, n: int, n_lines: int) -> dict:
        buf: deque[tuple[int, str]] = deque(maxlen=n)
        total_lines = 0
        with open(p, errors="replace") as f:
            for i, line in enumerate(f, 1):
                total_lines = i
                buf.append((i, line[:MAX_LINE_LENGTH]))

        entries = list(buf)[:n_lines]
        output = "".join(f"{num:6d}\t{line}" for num, line in entries)
        return {"is_error": False, "message": f"{len(entries)} lines read (total: {total_lines}).", "output": output}


# ---------------------------------------------------------------------------
# 函数式接口
# ---------------------------------------------------------------------------

def read_file_tool(filepath: str, offset: int = 0, limit: int = 2000) -> str:
    """同步文件读取（简单接口）"""
    if not filepath:
        return tool_error("filepath is required.")

    path = resolve_path(filepath)
    if not path.exists():
        return tool_error(f"File not found: {filepath}")
    if not path.is_file():
        return tool_error(f"Not a file: {filepath}")

    # 图片文件 — 上传 OSS
    if _is_image(path):
        try:
            from ...utils.oss import ensure_public_url, _is_oss_available
            if not _is_oss_available():
                return tool_result({
                    "content": f"[Image file: {filepath} — OSS not configured]",
                    "total_lines": 0,
                    "lines_shown": 0,
                })
            url = ensure_public_url(str(path))
            return tool_result({
                "content": f"Image uploaded to OSS: {url}",
                "images": [{"url": url, "filename": path.name}],
                "total_lines": 0,
                "lines_shown": 0,
            })
        except Exception as e:
            return tool_result({
                "content": f"[Image file: {filepath} — upload failed: {e}]",
                "total_lines": 0,
                "lines_shown": 0,
            })

    if _is_binary(path):
        return tool_error(f"Cannot read binary file: {filepath}")

    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        return tool_error(f"Cannot read as text (possible binary): {filepath}")
    except Exception as e:
        return tool_error(str(e))

    max_chars = 100_000
    result_lines = lines[offset:offset + limit] if limit > 0 else lines[offset:]
    output = "".join(result_lines)

    if len(output) > max_chars:
        output = output[:max_chars] + "\n... [truncated at 100K characters]"

    return tool_result({
        "content": output,
        "total_lines": len(lines),
        "lines_shown": len(result_lines),
    })

