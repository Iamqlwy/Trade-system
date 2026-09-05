"""
数据库迁移脚本 — 添加 owner_id 列

用途：为 strategys 表添加 owner_id 列，支持策略权限归属。
运行方式：python scripts/migrate_owner_id.py
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from sqlalchemy import create_engine, text, inspect

from app.config import settings


def migrate():
    engine = create_engine(settings.db_url)
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("strategys")]

    print(f"当前 strategys 表列: {cols}")

    if "owner_id" in cols:
        print("⏭  owner_id 列已存在，无需迁移")
        return

    with engine.connect() as conn:
        conn.execute(text(
            'ALTER TABLE strategys ADD COLUMN owner_id INT NULL '
            'COMMENT "策略所有者用户ID"'
        ))
        conn.commit()

    print("✅ ALTER TABLE 成功: strategys.owner_id 已添加")

    # 验证
    insp2 = inspect(engine)
    cols2 = [c["name"] for c in insp2.get_columns("strategys")]
    print(f"迁移后列: {cols2}")


if __name__ == "__main__":
    migrate()
