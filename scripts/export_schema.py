"""
导出当前数据库的完整表结构（DDL）和触发器到 SQL 文件。
用途：删除重建数据库前的备份。

运行方式：python scripts/export_schema.py
输出文件：data/schema_backup.sql
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
from app.config import settings


def export_schema():
    engine = create_engine(settings.db_url)
    insp = inspect(engine)

    lines = []
    lines.append("-- ============================================")
    lines.append(f"-- 数据库 {settings.db_name} 表结构导出（含触发器）")
    lines.append("-- 生成方式: python scripts/export_schema.py")
    lines.append("-- 重建步骤:")
    lines.append(f"--   1. DROP DATABASE `{settings.db_name}`;")
    lines.append(f"--   2. CREATE DATABASE `{settings.db_name}` DEFAULT CHARSET utf8mb4;")
    lines.append(f"--   3. USE `{settings.db_name}`;")
    lines.append("--   4. source data/schema_backup.sql")
    lines.append("-- ============================================")
    lines.append("")
    lines.append("SET NAMES utf8mb4;")
    lines.append("SET FOREIGN_KEY_CHECKS = 0;")
    lines.append("")

    # ── 导出每张表的 SHOW CREATE TABLE（保留完整 DDL，含索引/约束/注释）
    tables = insp.get_table_names()
    for tname in sorted(tables):
        with engine.connect() as conn:
            row = conn.execute(text(f"SHOW CREATE TABLE `{tname}`")).fetchone()
            if row is None:
                continue
            create_sql = row[1]

        lines.append(f"-- ----------------------------")
        lines.append(f"-- Table: {tname}")
        lines.append(f"-- ----------------------------")
        lines.append(f"DROP TABLE IF EXISTS `{tname}`;")
        lines.append(f"{create_sql};")
        lines.append("")

    # ── 导出触发器
    with engine.connect() as conn:
        triggers = conn.execute(text(
            "SELECT TRIGGER_NAME, EVENT_MANIPULATION, EVENT_OBJECT_TABLE, "
            "ACTION_TIMING, ACTION_ORIENTATION, ACTION_STATEMENT "
            "FROM INFORMATION_SCHEMA.TRIGGERS "
            "WHERE TRIGGER_SCHEMA = :schema "
            "ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING"
        ), {"schema": settings.db_name}).fetchall()

    if triggers:
        lines.append("-- ============================================")
        lines.append("-- 触发器")
        lines.append("-- ============================================")
        lines.append("")
        for tr in triggers:
            name, event, table, timing, _orientation, stmt = tr
            lines.append(f"DROP TRIGGER IF EXISTS `{name}`;")
            lines.append(f"DELIMITER $$")
            lines.append(
                f"CREATE TRIGGER `{name}` {timing} {event} ON `{table}`"
            )
            lines.append(f"FOR EACH ROW")
            lines.append(f"BEGIN")
            lines.append(stmt.rstrip(";"))
            lines.append(f"END$$")
            lines.append(f"DELIMITER ;")
            lines.append("")
    else:
        lines.append("-- 当前无触发器")
        lines.append("")

    lines.append("SET FOREIGN_KEY_CHECKS = 1;")

    # ── 写入文件
    out_dir = Path(__file__).parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "schema_backup.sql"

    output = "\n".join(lines)
    out_path.write_text(output, encoding="utf-8")

    print(f"✅ 导出完成")
    print(f"   表: {len(tables)} 张")
    print(f"   触发器: {len(triggers)} 个")
    print(f"   文件: {out_path}")
    print(f"   大小: {len(output):,} bytes")
    print()
    print("表列表:")
    for t in sorted(tables):
        print(f"  - {t}")
    if triggers:
        print()
        print("触发器:")
        for tr in triggers:
            print(f"  - {tr[0]} ({tr[3]} {tr[1]} ON {tr[2]})")


if __name__ == "__main__":
    export_schema()
