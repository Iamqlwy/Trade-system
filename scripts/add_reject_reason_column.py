"""为 order_confirmations 表添加缺失的 reject_reason 列。"""
import sys, os
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from sqlalchemy import text, create_engine
from app.config import settings

engine = create_engine(settings.db_url)

with engine.connect() as conn:
    # 检查列是否已存在
    result = conn.execute(text(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'order_confirmations' AND COLUMN_NAME = 'reject_reason'"
    ), {"db": settings.db_name})
    if result.fetchone():
        print("列 reject_reason 已存在，无需迁移")
    else:
        conn.execute(text(
            "ALTER TABLE order_confirmations "
            "ADD COLUMN reject_reason VARCHAR(200) NULL COMMENT '拒绝原因'"
        ))
        conn.commit()
        print("已添加 reject_reason 列")
