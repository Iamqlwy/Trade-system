"""
数据库迁移 — 创建 user_tool_permissions 表
运行方式：python scripts/migrate_tool_perms.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
from app.config import settings


def migrate():
    engine = create_engine(settings.db_url)
    insp = inspect(engine)

    if "user_tool_permissions" in insp.get_table_names():
        print("⏭  user_tool_permissions 表已存在")
        return

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE user_tool_permissions (
                user_id    INT          NOT NULL,
                tool_key   VARCHAR(32)  NOT NULL,
                enabled    TINYINT(1)   NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, tool_key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        conn.commit()

    print("✅ user_tool_permissions 表已创建")


if __name__ == "__main__":
    migrate()