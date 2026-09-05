"""迁移 monitor_records 表：
- 添加所有缺失列（确保与 ORM 模型一致）
- 删除 needs_stocks 列
- 清空旧数据（旧 monitor 全部废弃，通过 AI 重新创建）
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from sqlalchemy import text, create_engine
from app.config import settings

engine = create_engine(settings.db_url)


def _column_exists(conn, column_name: str) -> bool:
    result = conn.execute(text(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'monitor_records' "
        "AND COLUMN_NAME = :col"
    ), {"db": settings.db_name, "col": column_name})
    return result.fetchone() is not None


def _add_column_if_missing(conn, col_name: str, col_def: str):
    """添加列（如果不存在）"""
    if not _column_exists(conn, col_name):
        conn.execute(text(
            f"ALTER TABLE monitor_records ADD COLUMN {col_name} {col_def}"
        ))
        print(f"  + 已添加 {col_name} 列")
    else:
        print(f"  - {col_name} 已存在，跳过")


# 与 ORM 模型 MonitorRecord 对齐的列定义
_COLUMNS_TO_ENSURE = {
    "session_id":       "VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'agent 工作区 session_id'",
    "script_path":      "VARCHAR(200) NOT NULL DEFAULT 'check.py' COMMENT '工作区内脚本相对路径'",
    "script_metadata":  "JSON NOT NULL COMMENT 'AI生成的脚本元数据'",
    "params":           "JSON NOT NULL COMMENT '用户配置的参数值'",
}


with engine.connect() as conn:
    # 0. 检查表是否存在
    result = conn.execute(text(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'monitor_records'"
    ), {"db": settings.db_name})
    if not result.fetchone():
        print("monitor_records 表不存在，正在创建...")
        conn.execute(text("""
            CREATE TABLE monitor_records (
                monitor_id VARCHAR(20) PRIMARY KEY,
                owner_id INT NULL,
                session_id VARCHAR(64) NOT NULL DEFAULT '',
                monitor_name VARCHAR(100) NOT NULL DEFAULT '',
                description TEXT,
                stock_codes JSON,
                strategy_ids JSON,
                `interval` VARCHAR(10) NOT NULL DEFAULT '30s',
                trigger_mode VARCHAR(20) NOT NULL DEFAULT 'periodic',
                enabled TINYINT(1) NOT NULL DEFAULT 1,
                cooldown_seconds INT NOT NULL DEFAULT 300,
                script_metadata JSON NOT NULL,
                params JSON NOT NULL,
                script_path VARCHAR(200) NOT NULL DEFAULT 'check.py',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        conn.commit()
        print("monitor_records 表已创建")
        # 也创建 alert_logs 表（如果不存在）
        result2 = conn.execute(text(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'monitor_alert_logs'"
        ), {"db": settings.db_name})
        if not result2.fetchone():
            conn.execute(text("""
                CREATE TABLE monitor_alert_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    monitor_id VARCHAR(20) NOT NULL,
                    monitor_name VARCHAR(100) NOT NULL DEFAULT '',
                    stock_code VARCHAR(20) NOT NULL DEFAULT '',
                    message TEXT,
                    data JSON,
                    triggered_at DATETIME NOT NULL,
                    INDEX idx_monitor_id (monitor_id),
                    INDEX idx_stock_code (stock_code),
                    INDEX idx_triggered_at (triggered_at)
                )
            """))
            conn.commit()
            print("monitor_alert_logs 表已创建")
        print("迁移完成")
        sys.exit(0)

    # 1. 清空旧数据
    conn.execute(text("DELETE FROM monitor_records"))
    conn.execute(text("DELETE FROM monitor_alert_logs"))
    print("已清空旧 monitor 数据")

    # 2. 确保所有列存在
    print("检查列完整性...")
    for col_name, col_def in _COLUMNS_TO_ENSURE.items():
        _add_column_if_missing(conn, col_name, col_def)

    # 3. 删除 needs_stocks 列（如果存在）
    if _column_exists(conn, "needs_stocks"):
        conn.execute(text("ALTER TABLE monitor_records DROP COLUMN needs_stocks"))
        print("  + 已删除 needs_stocks 列")
    else:
        print("  - needs_stocks 不存在，跳过")

    conn.commit()
    print("迁移完成")
