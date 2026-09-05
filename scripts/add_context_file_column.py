"""添加 cron_job_runs.context_file 列（如缺失）"""
import sys, os
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
from app.config import settings

engine = create_engine(settings.db_url)
inspector = inspect(engine)

columns = [c["name"] for c in inspector.get_columns("cron_job_runs")]
if "context_file" not in columns:
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE cron_job_runs "
            "ADD COLUMN context_file VARCHAR(500) NULL "
            "COMMENT 'full conversation context .jsonl file path' "
            "AFTER user_id"
        ))
        conn.commit()
    print("✅ 已添加 context_file 列")
else:
    print("✅ context_file 列已存在，无需操作")
