"""Skills 工具 — 技能列表、查看、管理。

复刻自 code/simple-agent/tools/skills_tool.py + skill_manager.py

功能：
  - skills_list: 列出所有可用技能 (Tier 1 元数据)
  - skill_view:  加载技能完整内容 (Tier 2) 或引用文件 (Tier 3)
  - skill_manage: CRUD 操作 (create/edit/patch/delete)
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from app.agent.tools.base import Tool, ToolParam
from app.agent.skills import (
    scan_skills, load_skill, load_skill_file, build_catalog,
    _get_write_dir,  # 写入操作使用（用户级目录）
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# skills_list 工具
# ---------------------------------------------------------------------------

def _current_user_id() -> int:
    """获取当前请求上下文的 user_id（由 agent_manager 设置）。"""
    from app.services.cron_service import _current_user_id as _ctx_uid
    return _ctx_uid.get()


class SkillsList(Tool):
    """列出所有可用技能"""

    name = "skills_list"
    description = "List all available skills with names and descriptions. Use skill_view to load full details."

    parameters: list[ToolParam] = []

    async def call(self, arguments: dict) -> dict:
        uid = _current_user_id()
        skills = scan_skills(uid)
        catalog = build_catalog(uid)
        return {
            "is_error": False,
            "output": json.dumps({
                "skills": [
                    {"name": s.name, "description": s.description, "category": s.category}
                    for s in skills
                ],
                "count": len(skills),
                "catalog": catalog,
            }, ensure_ascii=False),
        }


# ---------------------------------------------------------------------------
# skill_view 工具
# ---------------------------------------------------------------------------

class SkillView(Tool):
    """查看技能详情"""

    name = "skill_view"
    description = "Load the full instructions for a skill. Optionally load a specific reference file within the skill."

    parameters = [
        ToolParam("skill_name", str, "Name of the skill to load."),
        ToolParam("file_path", str, "Optional path to a reference file within the skill.", default="", required=False),
    ]

    async def call(self, arguments: dict) -> dict:
        skill_name = arguments.get("skill_name", "")
        file_path = arguments.get("file_path", "")

        if not skill_name:
            return {"is_error": True, "message": "skill_name is required."}

        uid = _current_user_id()

        # 搜索所有技能目录（用户级 + 官方 + 项目级）
        if file_path:
            content = load_skill_file(uid, skill_name, file_path)
            if content is None:
                return {"is_error": True, "message": f"File not found: {file_path} in skill '{skill_name}'."}
            return {
                "is_error": False,
                "output": json.dumps({
                    "skill_name": skill_name,
                    "file_path": file_path,
                    "content": content,
                }, ensure_ascii=False),
            }

        skill = load_skill(uid, skill_name)
        if skill is None:
            return {"is_error": True, "message": f"Skill not found: {skill_name}"}

        return {
            "is_error": False,
            "output": json.dumps({
                "name": skill.meta.name,
                "description": skill.meta.description,
                "category": skill.meta.category,
                "content": skill.content,
                "files": skill.files,
            }, ensure_ascii=False),
        }


# ---------------------------------------------------------------------------
# skill_manage 工具
# ---------------------------------------------------------------------------

def _sanitize_name(name: str) -> str:
    """清理技能名：仅保留字母数字、连字符、下划线，最长 64 字符"""
    name = re.sub(r'[^a-zA-Z0-9_-]', '-', name).strip('-')
    return name[:64]


class SkillManage(Tool):
    """技能 CRUD 管理"""

    name = "skill_manage"
    description = (
        "Create, edit, patch, or delete skills. Skills are YAML frontmatter + markdown files. "
        "Create: add a new skill. Edit: replace entire SKILL.md. "
        "Patch: exact find-and-replace in SKILL.md. Delete: remove entire skill directory."
    )

    parameters = [
        ToolParam("action", str, "Action: create, edit, patch, delete."),
        ToolParam("skill_name", str, "Name of the skill.", default="", required=False),
        ToolParam("content", str, "SKILL.md content (for create/edit).", default="", required=False),
        ToolParam("find", str, "Text to find (for patch).", default="", required=False),
        ToolParam("replace", str, "Replacement text (for patch).", default="", required=False),
    ]

    async def call(self, arguments: dict) -> dict:
        action = arguments.get("action", "")
        skill_name = arguments.get("skill_name", "")
        content = arguments.get("content", "")
        find = arguments.get("find", "")
        replace = arguments.get("replace", "")

        # 写入目录：用户自己的 skills 目录（隔离）
        uid = _current_user_id()
        skills_dir = _get_write_dir(uid)
        skills_dir.mkdir(parents=True, exist_ok=True)

        if action == "create":
            if not skill_name:
                return {"is_error": True, "message": "skill_name is required for 'create'."}
            if not content:
                return {"is_error": True, "message": "content is required for 'create'."}
            return self._create(skills_dir, skill_name, content)

        elif action == "edit":
            if not skill_name:
                return {"is_error": True, "message": "skill_name is required for 'edit'."}
            if not content:
                return {"is_error": True, "message": "content is required for 'edit'."}
            return self._edit(skills_dir, skill_name, content)

        elif action == "patch":
            if not skill_name:
                return {"is_error": True, "message": "skill_name is required for 'patch'."}
            if not find:
                return {"is_error": True, "message": "find is required for 'patch'."}
            return self._patch(skills_dir, skill_name, find, replace)

        elif action == "delete":
            if not skill_name:
                return {"is_error": True, "message": "skill_name is required for 'delete'."}
            return self._delete(skills_dir, skill_name)

        return {"is_error": True, "message": f"Unknown action '{action}'. Use: create, edit, patch, delete."}

    def _create(self, skills_dir: Path, name: str, content: str) -> dict:
        safe_name = _sanitize_name(name)
        if not safe_name:
            return {"is_error": True, "message": "Invalid skill name."}

        skill_dir = skills_dir / safe_name
        if skill_dir.exists():
            return {"is_error": True, "message": f"Skill '{safe_name}' already exists. Use 'edit' or 'delete' first."}

        # 确保有 frontmatter
        if not content.strip().startswith("---"):
            description = content.strip().split("\n")[0][:200]
            frontmatter = f"---\nname: {safe_name}\ndescription: {description}\n---\n\n"
            content = frontmatter + content

        try:
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
            return {"is_error": False, "output": json.dumps({"success": True, "skill_name": safe_name, "message": "Skill created."}, ensure_ascii=False)}
        except Exception as e:
            return {"is_error": True, "message": str(e)}

    def _edit(self, skills_dir: Path, name: str, content: str) -> dict:
        safe_name = _sanitize_name(name)
        skill_md = skills_dir / safe_name / "SKILL.md"
        if not skill_md.exists():
            return {"is_error": True, "message": f"Skill '{safe_name}' not found."}

        try:
            skill_md.write_text(content, encoding="utf-8")
            return {"is_error": False, "output": json.dumps({"success": True, "skill_name": safe_name, "message": "Skill updated."}, ensure_ascii=False)}
        except Exception as e:
            return {"is_error": True, "message": str(e)}

    def _patch(self, skills_dir: Path, name: str, find_text: str, replace_text: str) -> dict:
        safe_name = _sanitize_name(name)
        skill_md = skills_dir / safe_name / "SKILL.md"
        if not skill_md.exists():
            return {"is_error": True, "message": f"Skill '{safe_name}' not found."}

        try:
            original = skill_md.read_text(encoding="utf-8")
        except Exception as e:
            return {"is_error": True, "message": str(e)}

        if find_text not in original:
            return {"is_error": True, "message": "Find text not found in SKILL.md. Ensure exact whitespace match."}

        updated = original.replace(find_text, replace_text, 1)
        try:
            skill_md.write_text(updated, encoding="utf-8")
            return {"is_error": False, "output": json.dumps({"success": True, "skill_name": safe_name, "message": "Skill patched."}, ensure_ascii=False)}
        except Exception as e:
            return {"is_error": True, "message": str(e)}

    def _delete(self, skills_dir: Path, name: str) -> dict:
        safe_name = _sanitize_name(name)
        skill_dir = skills_dir / safe_name
        if not skill_dir.exists():
            return {"is_error": True, "message": f"Skill '{safe_name}' not found."}

        try:
            shutil.rmtree(skill_dir)
            return {"is_error": False, "output": json.dumps({"success": True, "skill_name": safe_name, "message": "Skill deleted."}, ensure_ascii=False)}
        except Exception as e:
            return {"is_error": True, "message": str(e)}
