"""记忆系统 ORM 模型 — 用户画像 + 交互记忆

替代原有的文件级 MemoryStore（MEMORY.md / USER.md），
改用 MySQL 持久化，支持多用户、结构化查询、前端管理。
"""

from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, JSON,
)

from ..store.models import Base


class UserProfile(Base):
    """用户画像 — 结构化交易偏好

    每个用户一行。字段由 AI 自动提取或用户手动编辑。
    """

    __tablename__ = "user_profiles"

    user_id = Column(Integer, primary_key=True)
    trading_style = Column(String(20), nullable=True, comment="short_term|swing|long_term")
    risk_level = Column(String(10), nullable=True, comment="conservative|moderate|aggressive")
    focus_sectors = Column(JSON, default=list, comment='["半导体", "新能源"]')
    focus_stocks = Column(JSON, default=list, comment='["002594.SZ", "300750.SZ"]')
    capital_range = Column(String(20), nullable=True, comment="under_50w|50w_200w|above_200w")
    indicators = Column(JSON, default=list, comment='["MA", "MACD", "RSI"]')
    extra = Column(JSON, default=dict, comment="其他自由格式信息")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class UserMemory(Base):
    """交互记忆 — AI 在历次对话中积累的半结构化笔记

    每条记忆属于一个用户，按 category 分类。
    """

    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    category = Column(String(30), nullable=False, comment="preference|observation|lesson|context")
    content = Column(Text, nullable=False)
    source = Column(String(20), default="auto", comment="auto=AI提取 | manual=用户手动")
    confidence = Column(Float, default=1.0, comment="衰减系数，随时间递减")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    expires_at = Column(DateTime, nullable=True, comment="可选过期时间")
