"""记忆服务 — 用户画像 + 交互记忆的 CRUD 与系统提示注入

替代原有的文件级 MemoryStore，使用 MySQL 持久化。
按 user_id 隔离，支持结构化查询和前端管理。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from ..dependencies import repository

logger = logging.getLogger(__name__)

# 画像字段中文标签（前端 / 系统提示共用）
_PROFILE_LABELS: dict[str, str] = {
    "trading_style": "交易风格",
    "risk_level": "风险偏好",
    "focus_sectors": "关注板块",
    "focus_stocks": "关注个股",
    "capital_range": "资金规模",
    "indicators": "偏好指标",
}

# 画像字段可选值映射（中文 → 英文 key）
_TRADING_STYLE_MAP = {
    "短线": "short_term",
    "波段": "swing",
    "长线": "long_term",
}
_TRADING_STYLE_REVERSE = {v: k for k, v in _TRADING_STYLE_MAP.items()}

_RISK_LEVEL_MAP = {
    "保守": "conservative",
    "稳健": "moderate",
    "激进": "aggressive",
}
_RISK_LEVEL_REVERSE = {v: k for k, v in _RISK_LEVEL_MAP.items()}


class MemoryService:
    """用户记忆管理服务（单例）"""

    # ------------------------------------------------------------------
    # 画像 CRUD
    # ------------------------------------------------------------------

    def get_profile(self, user_id: int) -> dict[str, Any]:
        """获取用户画像，不存在则返回默认空结构"""
        from ..models.memory import UserProfile

        session = repository.SessionLocal()
        try:
            row = session.query(UserProfile).filter_by(user_id=user_id).first()
            if not row:
                return self._empty_profile()
            return {
                "trading_style": row.trading_style,
                "risk_level": row.risk_level,
                "focus_sectors": row.focus_sectors or [],
                "focus_stocks": row.focus_stocks or [],
                "capital_range": row.capital_range,
                "indicators": row.indicators or [],
                "extra": row.extra or {},
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        finally:
            session.close()

    def update_profile(self, user_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        """部分更新用户画像，返回更新后的完整画像"""
        from ..models.memory import UserProfile

        allowed_fields = {
            "trading_style", "risk_level", "focus_sectors",
            "focus_stocks", "capital_range", "indicators", "extra",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return self.get_profile(user_id)

        session = repository.SessionLocal()
        try:
            row = session.query(UserProfile).filter_by(user_id=user_id).first()
            if not row:
                row = UserProfile(user_id=user_id)
                session.add(row)

            for key, value in filtered.items():
                setattr(row, key, value)
            row.updated_at = datetime.now()

            session.commit()
            return self.get_profile(user_id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # 记忆 CRUD
    # ------------------------------------------------------------------

    def get_memories(
        self,
        user_id: int,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取用户记忆列表（按创建时间倒序）"""
        from ..models.memory import UserMemory

        session = repository.SessionLocal()
        try:
            q = session.query(UserMemory).filter_by(user_id=user_id)
            if category:
                q = q.filter_by(category=category)
            q = q.order_by(UserMemory.created_at.desc()).limit(limit)

            return [
                {
                    "id": m.id,
                    "category": m.category,
                    "content": m.content,
                    "source": m.source,
                    "confidence": m.confidence,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                }
                for m in q.all()
            ]
        finally:
            session.close()

    def add_memory(
        self,
        user_id: int,
        category: str,
        content: str,
        source: str = "manual",
    ) -> dict[str, Any]:
        """添加一条记忆"""
        from ..models.memory import UserMemory

        content = content.strip()
        if not content:
            raise ValueError("记忆内容不能为空")
        if category not in ("preference", "observation", "lesson", "context"):
            raise ValueError(f"无效分类: {category}")

        session = repository.SessionLocal()
        try:
            # 简单去重：同一用户同一内容不重复插入
            existing = (
                session.query(UserMemory)
                .filter_by(user_id=user_id, content=content)
                .first()
            )
            if existing:
                return {
                    "id": existing.id,
                    "category": existing.category,
                    "content": existing.content,
                    "source": existing.source,
                    "created_at": existing.created_at.isoformat() if existing.created_at else None,
                    "message": "该记忆已存在",
                }

            mem = UserMemory(
                user_id=user_id,
                category=category,
                content=content,
                source=source,
            )
            session.add(mem)
            session.commit()
            session.refresh(mem)
            return {
                "id": mem.id,
                "category": mem.category,
                "content": mem.content,
                "source": mem.source,
                "created_at": mem.created_at.isoformat() if mem.created_at else None,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def remove_memory(self, user_id: int, memory_id: int) -> bool:
        """删除一条记忆，返回是否成功"""
        from ..models.memory import UserMemory

        session = repository.SessionLocal()
        try:
            row = (
                session.query(UserMemory)
                .filter_by(id=memory_id, user_id=user_id)
                .first()
            )
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def batch_add_memories(
        self,
        user_id: int,
        memories: list[dict[str, str]],
        source: str = "auto",
    ) -> int:
        """批量添加记忆（自动提取结果写入）。返回新增条数。

        Args:
            memories: [{"category": "...", "content": "..."}, ...]
        """
        from ..models.memory import UserMemory

        session = repository.SessionLocal()
        added = 0
        try:
            # 获取已有内容用于去重
            existing_contents: set[str] = set()
            for m in session.query(UserMemory.content).filter_by(user_id=user_id).all():
                existing_contents.add(m.content)

            for item in memories:
                content = item.get("content", "").strip()
                category = item.get("category", "observation")
                if not content:
                    continue
                if content in existing_contents:
                    continue

                mem = UserMemory(
                    user_id=user_id,
                    category=category,
                    content=content,
                    source=source,
                )
                session.add(mem)
                existing_contents.add(content)
                added += 1

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        return added

    # ------------------------------------------------------------------
    # 系统提示注入
    # ------------------------------------------------------------------

    def format_profile_for_prompt(self, user_id: int) -> str | None:
        """将用户画像格式化为系统提示文本块"""
        profile = self.get_profile(user_id)

        lines: list[str] = []
        for key, label in _PROFILE_LABELS.items():
            value = profile.get(key)
            if not value:
                continue
            # JSON 列表字段：用逗号拼接
            if isinstance(value, list):
                if value:
                    lines.append(f"{label}: {'、'.join(str(v) for v in value)}")
            elif isinstance(value, dict):
                if value:
                    lines.append(f"{label}: {json.dumps(value, ensure_ascii=False)}")
            elif isinstance(value, str):
                # 英文 key 转中文显示
                display = _EN_TO_CN.get(key, {}).get(value, value)
                lines.append(f"{label}: {display}")

        if not lines:
            return None

        return "## 用户画像\n" + "\n".join(lines)

    def format_memories_for_prompt(self, user_id: int, limit: int = 10) -> str | None:
        """将近期记忆格式化为系统提示文本块"""
        memories = self.get_memories(user_id, limit=limit)
        if not memories:
            return None

        lines: list[str] = []
        category_emoji = {
            "preference": "偏好",
            "observation": "观察",
            "lesson": "经验",
            "context": "上下文",
        }
        for m in memories:
            prefix = category_emoji.get(m["category"], "")
            date_str = ""
            if m["created_at"]:
                try:
                    dt = datetime.fromisoformat(m["created_at"])
                    date_str = f"{dt.month}/{dt.day}"
                except (ValueError, TypeError):
                    pass
            lines.append(f"- {date_str} [{prefix}] {m['content']}")

        if not lines:
            return None

        return "## AI 笔记\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_profile() -> dict[str, Any]:
        return {
            "trading_style": None,
            "risk_level": None,
            "focus_sectors": [],
            "focus_stocks": [],
            "capital_range": None,
            "indicators": [],
            "extra": {},
            "updated_at": None,
        }


# 英文值 → 中文显示映射
_EN_TO_CN: dict[str, dict[str, str]] = {
    "trading_style": _TRADING_STYLE_REVERSE,
    "risk_level": _RISK_LEVEL_REVERSE,
}


# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------

memory_service = MemoryService()
