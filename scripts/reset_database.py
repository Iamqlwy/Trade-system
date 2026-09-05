"""
清空数据库中所有表数据（保留表结构），不插入任何种子数据。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy import inspect
from app.config import settings


def reset_database():
    engine = create_engine(settings.db_url)

    tables = inspect(engine).get_table_names()
    print(f"发现 {len(tables)} 张表，开始清空...")

    with engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in tables:
            try:
                conn.execute(text(f"TRUNCATE TABLE `{table}`"))
                print(f"  ✓ {table}")
            except Exception as e:
                print(f"  ✗ {table} ({e})")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()

    print("\n全部表已清空，无种子数据。")


if __name__ == "__main__":
    reset_database()