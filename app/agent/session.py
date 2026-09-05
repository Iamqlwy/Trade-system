"""统一会话管理

合并自：
  - code_agent/session.py: 异步 Session + Context 管理
  - simple-agent/session.py: 同步 Session + agent_register

目录布局：
    ~/.unified-agent/sessions/{session_id}/
        context.jsonl         # 对话历史
        state.json            # 状态（plan mode 等）
        agent_register.jsonl  # 子 agent 记录
    ~/.unified-agent/workspace/{session_id}/
        ...                   # 代码工作区
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.agent.config import get_agent_home, get_sessions_dir


# ---------------------------------------------------------------------------
# 会话目录管理
# ---------------------------------------------------------------------------

def _get_sessions_root() -> Path:
    return get_sessions_dir()


def _get_workspace_root() -> Path:
    p = get_agent_home() / "workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Session 数据类
# ---------------------------------------------------------------------------

@dataclass
class Session:
    """统一会话对象

    管理一个会话的目录结构，包括对话历史、状态、子 agent 记录。
    """

    id: str
    work_dir: Path
    context_file: Path
    title: str = ""

    # 可选文件
    _register_file: Path = field(default=None, repr=False)  # type: ignore
    _workspace: Path = field(default=None, repr=False)  # type: ignore

    def __post_init__(self):
        session_dir = self.context_file.parent
        session_dir.mkdir(parents=True, exist_ok=True)
        if self._register_file is None:
            self._register_file = session_dir / "agent_register.jsonl"
        if self._workspace is None:
            ws_root = _get_workspace_root()
            self._workspace = ws_root / self.id
            self._workspace.mkdir(parents=True, exist_ok=True)

    @property
    def dir(self) -> Path:
        return self.context_file.parent

    @property
    def register_file(self) -> Path:
        return self._register_file

    @property
    def workspace(self) -> Path:
        return self._workspace

    # ---- 状态文件 ----

    def _state_file(self) -> Path:
        return self.dir / "state.json"

    def load_plan_mode(self) -> bool:
        sf = self._state_file()
        if sf.exists():
            try:
                data = json.loads(sf.read_text())
                return data.get("plan_mode", False)
            except (json.JSONDecodeError, OSError):
                pass
        return False

    def load_plan_session_id(self) -> str | None:
        sf = self._state_file()
        if sf.exists():
            try:
                data = json.loads(sf.read_text())
                return data.get("plan_session_id")
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def save_plan_state(self, plan_mode: bool, plan_session_id: str | None) -> None:
        sf = self._state_file()
        data: dict = {}
        if sf.exists():
            try:
                data = json.loads(sf.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        data["plan_mode"] = plan_mode
        if plan_session_id:
            data["plan_session_id"] = plan_session_id
        sf.write_text(json.dumps(data))

    # ---- agent_register.jsonl ----

    def append_agent_register(self, entry: dict) -> None:
        with open(self._register_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_agent_register(self) -> list[dict]:
        entries: list[dict] = []
        if self._register_file.exists():
            with open(self._register_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    # ---- CRUD ----

    async def refresh(self) -> None:
        self.title = self.id[:8]

    async def delete(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    @staticmethod
    async def create(work_dir: Path | str, session_id: str | None = None) -> Session:
        """创建新会话"""
        work_dir = Path(work_dir).resolve()
        if session_id is None:
            session_id = "ag_" + uuid.uuid4().hex[:16]

        sessions_dir = _get_sessions_root()
        session_dir = sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        context_file = session_dir / "context.jsonl"
        context_file.touch()

        session = Session(
            id=session_id,
            work_dir=work_dir,
            context_file=context_file,
        )
        _save_last_session(work_dir, session_id)
        await session.refresh()
        return session

    @staticmethod
    async def find(work_dir: Path | str, session_id: str) -> Session | None:
        """查找已有会话"""
        work_dir = Path(work_dir).resolve()
        sessions_dir = _get_sessions_root()
        session_dir = sessions_dir / session_id
        context_file = session_dir / "context.jsonl"
        if not context_file.exists():
            return None
        return Session(id=session_id, work_dir=work_dir, context_file=context_file)

    @staticmethod
    async def list_all(work_dir: Path | str) -> list[dict]:
        """列出所有会话（按最后修改时间倒序）"""
        sessions_dir = _get_sessions_root()
        result: list[dict] = []
        for d in sessions_dir.iterdir():
            if not d.is_dir():
                continue
            context_file = d / "context.jsonl"
            if not context_file.exists():
                continue
            msg_count = 0
            summary = "(empty)"
            try:
                with open(context_file, encoding="utf-8") as f:
                    for line in f:
                        try:
                            msg = json.loads(line)
                            role = msg.get("role", "")
                            if role not in ("_system_prompt", "_usage"):
                                msg_count += 1
                            if role == "user" and summary == "(empty)":
                                summary = str(msg.get("content", ""))[:80]
                        except json.JSONDecodeError:
                            pass
            except OSError:
                pass
            result.append({
                "id": d.name,
                "title": d.name[:8],
                "summary": summary.replace("\n", " "),
                "messages": msg_count,
                "mtime": context_file.stat().st_mtime,
            })
        result.sort(key=lambda x: x["mtime"], reverse=True)
        return result

    @staticmethod
    async def continue_(work_dir: Path | str) -> Session | None:
        """恢复上一个会话"""
        work_dir = Path(work_dir).resolve()
        last_id = _load_last_session(work_dir)
        if last_id is None:
            return None
        return await Session.find(work_dir, last_id)


# ---------------------------------------------------------------------------
# 最后会话记录
# ---------------------------------------------------------------------------

def _last_session_file() -> Path:
    f = get_agent_home() / "last_session.json"
    return f


def _save_last_session(work_dir: Path, session_id: str) -> None:
    data: dict = {}
    f = _last_session_file()
    if f.exists():
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    data[str(work_dir)] = session_id
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data))


def _load_last_session(work_dir: Path) -> str | None:
    f = _last_session_file()
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text())
        return data.get(str(work_dir))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# 当前会话（模块级单例）
# ---------------------------------------------------------------------------

_current_session: Session | None = None


def set_current_session(session: Session) -> None:
    global _current_session
    _current_session = session


def get_current_session() -> Session | None:
    return _current_session
