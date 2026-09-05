"""迁移工具 — 为现有 JSONL 记录批量添加 _meta 可见性元数据

用法：
    python -m app.agent.migrate_visibility           # 迁移所有会话
    python -m app.agent.migrate_visibility --dry-run  # 仅统计，不写入
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# 确保可以导入 app 包
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.agent.context import _ensure_meta


def migrate_jsonl_file(file_path: Path, backup: bool = True, dry_run: bool = False) -> int:
    """为单个 JSONL 文件的所有记录添加 _meta 字段。

    Args:
        file_path: context.jsonl 文件路径
        backup: 是否在迁移前创建备份
        dry_run: 仅统计需要迁移的记录数，不写入

    Returns:
        迁移（或需迁移）的记录数
    """
    if not file_path.exists():
        return 0

    migrated_count = 0
    total_count = 0
    temp_lines: list[str] = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_count += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                temp_lines.append(line)
                continue

            if "_meta" not in record:
                _ensure_meta(record)
                migrated_count += 1

            temp_lines.append(json.dumps(record, ensure_ascii=False))

    if dry_run:
        return migrated_count

    # 创建备份
    if backup and migrated_count > 0:
        backup_path = file_path.with_suffix(".jsonl.pre-visibility")
        shutil.copy2(file_path, backup_path)

    # 写回迁移后的文件
    if migrated_count > 0:
        with open(file_path, "w", encoding="utf-8") as f:
            for line in temp_lines:
                f.write(line + "\n")

    return migrated_count


def migrate_all_sessions(sessions_dir: Path | None = None, dry_run: bool = False) -> dict[str, int]:
    """迁移所有会话的 context.jsonl 文件。

    Args:
        sessions_dir: 会话目录，默认从配置读取
        dry_run: 仅统计

    Returns:
        {session_id: 迁移记录数} 字典
    """
    if sessions_dir is None:
        from app.agent.config import get_agent_home
        sessions_dir = get_agent_home() / "sessions"

    results: dict[str, int] = {}

    if not sessions_dir.exists():
        return results

    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue

        context_file = session_dir / "context.jsonl"
        if not context_file.exists():
            continue

        count = migrate_jsonl_file(context_file, dry_run=dry_run)
        if count > 0:
            results[session_dir.name] = count

    return results


def main():
    parser = argparse.ArgumentParser(description="迁移 JSONL 可见性元数据")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写入")
    parser.add_argument("--sessions-dir", type=str, default=None, help="会话目录路径")
    parser.add_argument("--no-backup", action="store_true", help="不创建备份")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir) if args.sessions_dir else None

    if sessions_dir is None:
        from app.agent.config import get_agent_home
        sessions_dir = get_agent_home() / "sessions"

    print(f"会话目录: {sessions_dir}")
    print(f"模式: {'Dry Run (仅统计)' if args.dry_run else '迁移'}")
    print()

    results = migrate_all_sessions(
        sessions_dir=sessions_dir,
        dry_run=args.dry_run,
    )

    if results:
        total = 0
        for session_id, count in sorted(results.items()):
            print(f"  会话 {session_id}: {count} 条记录{'需' if args.dry_run else '已'}迁移")
            total += count
        print(f"\n总计: {total} 条记录")
    else:
        print("所有会话均已是最新格式，无需迁移。")


if __name__ == "__main__":
    main()
