"""Skill 扫描器 — 渐进式披露架构。

复刻自 code/simple-agent/agent/skills.py

架构：
  Tier 1: scan_skills()  — 返回元数据 (name + description) 用于系统提示
  Tier 2: load_skill()   — 返回完整 SKILL.md 内容
  Tier 3: load_skill_file() — 返回技能内引用文件

技能存储位置（扫描优先级从高到低）:
  1. SKILLS_DIR 环境变量（向后兼容）
  2. <project_root>/skills/（项目级）
  3. {agent_home}/skills/users/{user_id}/（用户级 — 每个用户独立空间）
  4. {agent_home}/skills/（官方/全局级 — 系统内置技能）

新建技能写入用户级目录。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# 项目根目录（app/agent/skills.py → 上溯 2 级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_skills_dirs(user_id: int = 0) -> list[Path]:
    """获取所有技能目录（去重，保持优先级顺序）。

    扫描顺序（同名技能优先匹配高优先级目录）:
      1. SKILLS_DIR 环境变量
      2. 项目级 skills/
      3. 用户级 skills/users/{user_id}/（user_id > 0 时）
      4. 官方/全局级 skills/
    """
    import os
    dirs: list[Path] = []

    def _add(p: Path) -> None:
        if p.is_dir() and p not in dirs:
            dirs.append(p)

    # 1. 环境变量指定目录（最高优先级，向后兼容）
    env_dir = os.getenv("SKILLS_DIR", "")
    if env_dir:
        _add(Path(env_dir))

    # 2. 项目级 skills/ 目录
    _add(_PROJECT_ROOT / "skills")

    # 3. 用户级 skills（user_id > 0 时）
    if user_id > 0:
        from app.agent.config import get_user_skills_dir
        _add(get_user_skills_dir(user_id))

    # 4. 官方/全局级 skills/
    from app.agent.config import get_official_skills_dir
    _add(get_official_skills_dir())

    return dirs


def _get_write_dir(user_id: int = 0) -> Path:
    """获取技能写入目录。

    有 user_id 时写入用户自己的目录，否则写入官方目录（向后兼容）。
    """
    if user_id > 0:
        from app.agent.config import get_user_skills_dir
        return get_user_skills_dir(user_id)
    from app.agent.config import get_official_skills_dir
    return get_official_skills_dir()


@dataclass
class SkillMeta:
    name: str
    description: str
    category: str
    path: Path


@dataclass
class SkillFull:
    meta: SkillMeta
    content: str
    files: list[str]


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML frontmatter。返回 (meta_dict, body)。"""
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    try:
        import yaml
        fm = yaml.safe_load(content[3:end])
    except Exception:
        # 简单解析 fallback
        fm = _simple_parse_yaml(content[3:end])
    body = content[end + 4:].lstrip("\n")
    return fm or {}, body


def _simple_parse_yaml(text: str) -> dict:
    """简单 YAML 解析（无需 yaml 库）"""
    result: dict = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                result[key] = value
    return result


def scan_skills(user_id: int = 0) -> list[SkillMeta]:
    """扫描所有技能目录，返回所有技能元数据 (Tier 1)。"""
    dirs = _get_skills_dirs(user_id)

    skills: list[SkillMeta] = []
    seen_names: set[str] = set()
    for sd in dirs:
        if not sd.exists():
            continue
        for d in sorted(sd.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            skill_md = d / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                raw = skill_md.read_text(encoding="utf-8")
            except Exception:
                continue
            fm, _ = _parse_frontmatter(raw)
            name = fm.get("name", d.name)
            # 去重：同名技能优先项目级（先扫描的目录优先）
            if name in seen_names:
                continue
            seen_names.add(name)
            description = fm.get("description", "")[:1024]
            category = fm.get("category", "general")
            skills.append(SkillMeta(name=name, description=description, category=category, path=skill_md))
    return skills


def load_skill(user_id: int, name: str) -> SkillFull | None:
    """加载技能的完整 SKILL.md 内容 (Tier 2)。搜索所有技能目录。"""
    dirs = _get_skills_dirs(user_id)

    for sd in dirs:
        if not sd.exists():
            continue
        for d in sorted(sd.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            skill_md = d / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                raw = skill_md.read_text(encoding="utf-8")
            except Exception:
                continue
            fm, body = _parse_frontmatter(raw)
            fm_name = fm.get("name", d.name)
            if fm_name != name and d.name != name:
                continue

            # 列出引用文件
            ref_files: list[str] = []
            for sub in ("references", "templates", "scripts"):
                sub_dir = d / sub
                if sub_dir.is_dir():
                    for f in sorted(sub_dir.rglob("*")):
                        if f.is_file():
                            ref_files.append(str(f.relative_to(d)))

            return SkillFull(
                meta=SkillMeta(
                    name=fm_name,
                    description=fm.get("description", "")[:1024],
                    category=fm.get("category", "general"),
                    path=skill_md,
                ),
                content=body,
                files=ref_files,
            )
    return None


def load_skill_file(user_id: int, name: str, file_path: str) -> str | None:
    """加载技能内的引用文件 (Tier 3)。搜索所有技能目录。"""
    dirs = _get_skills_dirs(user_id)

    # 确保 file_path 是相对路径
    file_path = file_path.lstrip("/\\")
    # 阻止路径穿越
    if ".." in file_path:
        return None

    for sd in dirs:
        if not sd.exists():
            continue
        for d in sorted(sd.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            skill_md = d / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                raw = skill_md.read_text(encoding="utf-8")
            except Exception:
                continue
            fm, _ = _parse_frontmatter(raw)
            fm_name = fm.get("name", d.name)
            if fm_name != name and d.name != name:
                continue

            target = d / file_path
            resolved = target.resolve()
            if not str(resolved).startswith(str(d.resolve())):
                return None  # 路径穿越被阻止
            if not resolved.is_file():
                return None
            try:
                return resolved.read_text(encoding="utf-8")
            except Exception:
                return None
    return None


def build_catalog(user_id: int = 0) -> str:
    """构建紧凑的技能目录，用于系统提示词。"""
    skills = scan_skills(user_id)
    if not skills:
        return "(No skills available)"
    lines = ["Available skills (use skill_view to load full instructions):"]
    for s in skills:
        lines.append(f"- {s.name}: {s.description}")
    return "\n".join(lines)
