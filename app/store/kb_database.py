"""
知识库 PostgreSQL 数据库连接（只读）

直连 Docker pgbouncer，用于知识图谱可视化查询。
"""
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from ..config import settings

logger = logging.getLogger(__name__)

_kb_engine = None
_kb_session_factory = None


def _get_kb_engine():
    global _kb_engine
    if _kb_engine is None:
        _kb_engine = create_engine(
            settings.kb_db_url,
            pool_size=5,
            max_overflow=5,
            pool_timeout=30,
            pool_pre_ping=True,
        )
        logger.info("知识库 PostgreSQL 连接池初始化完成")
    return _kb_engine


def _get_kb_session_factory():
    global _kb_session_factory
    if _kb_session_factory is None:
        _kb_session_factory = sessionmaker(
            bind=_get_kb_engine(),
            expire_on_commit=False,
        )
    return _kb_session_factory


@contextmanager
def kb_session():
    """获取知识库数据库 session（只读）"""
    factory = _get_kb_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def check_kb_health() -> bool:
    """检查知识库数据库是否可连接"""
    try:
        with kb_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning("知识库数据库连接失败: %s", e)
        return False
