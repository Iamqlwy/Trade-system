"""为 monitor_records 表添加 needs_stocks 列。"""
import sys, os
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from sqlalchemy import text, create_engine
from app.config import settings

engine = create_engine(settings.db_url)

with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'monitor_records' AND COLUMN_NAME = 'needs_stocks'"
    ), {"db": settings.db_name})
    if result.fetchone():
        print("列 needs_stocks 已存在，无需迁移")
    else:
        conn.execute(text(
            "ALTER TABLE monitor_records "
            "ADD COLUMN needs_stocks TINYINT(1) NOT NULL DEFAULT 1 "
            "COMMENT '是否需要传入股票代码（0=复杂条件监控）'"
        ))
        conn.commit()
        print("已添加 needs_stocks 列")
