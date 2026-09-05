"""添加 agent_sessions 缺失的 user_message_count / total_context_chars 列"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
from app.config import settings

engine = create_engine(settings.db_url)
inspector = inspect(engine)

columns = [c["name"] for c in inspector.get_columns("agent_sessions")]
missing = [col for col in ("user_message_count", "total_context_chars") if col not in columns]

if not missing:
    print("✅ 所有列已存在，无需操作")
else:
    with engine.connect() as conn:
        for col in missing:
            if col == "user_message_count":
                conn.execute(text(
                    "ALTER TABLE agent_sessions "
                    "ADD COLUMN user_message_count INT DEFAULT 0 "
                    "COMMENT '用户消息数量'"
                ))
                print(f"✅ 已添加 {col} 列")
            elif col == "total_context_chars":
                conn.execute(text(
                    "ALTER TABLE agent_sessions "
                    "ADD COLUMN total_context_chars INT DEFAULT 0 "
                    "COMMENT '会话上下文总字符数'"
                ))
                print(f"✅ 已添加 {col} 列")
        conn.commit()
