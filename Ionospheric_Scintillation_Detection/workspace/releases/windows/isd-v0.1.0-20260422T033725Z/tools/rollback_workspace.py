from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _list_backups(backups_dir: Path) -> list[Path]:
    if not backups_dir.exists():
        return []
    return sorted(backups_dir.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)


def _resolve_backup(backups: list[Path], selected: str | None, latest: bool) -> Path | None:
    if not backups:
        return None
    if latest or not selected:
        return backups[0]
    query = selected.strip().lower()
    for path in backups:
        if query in path.name.lower():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore workspace database from backup snapshot.")
    parser.add_argument("--workspace", default="workspace", help="Workspace root path.")
    parser.add_argument("--database", default="", help="Database file path. Default: <workspace>/isd.sqlite3")
    parser.add_argument("--backup", default="", help="Backup file name or partial token to restore from.")
    parser.add_argument("--latest", action="store_true", help="Restore latest backup.")
    parser.add_argument("--list", action="store_true", help="List available backups and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print restore plan without copying files.")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    database_path = Path(args.database).resolve() if args.database else workspace / "isd.sqlite3"
    backup_dir = workspace / "backups" / "db"
    backups = _list_backups(backup_dir)

    if args.list:
        if not backups:
            print("No database backups found.")
            return 0
        print(f"Backups in {backup_dir}:")
        for path in backups:
            print(f"- {path.name}")
        return 0

    chosen = _resolve_backup(backups, args.backup or None, args.latest)
    if not chosen:
        print("No matching backup found. Use --list to inspect available snapshots.")
        return 1

    rollback_dir = workspace / "backups" / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        before_restore = rollback_dir / f"isd_before_rollback_{_timestamp()}.sqlite3"
    else:
        before_restore = None

    print("Rollback plan:")
    print(f"- workspace: {workspace}")
    print(f"- database:  {database_path}")
    print(f"- restore:   {chosen}")
    if before_restore:
        print(f"- backup current db to: {before_restore}")

    if args.dry_run:
        print("Dry-run mode enabled, no files were changed.")
        return 0

    if before_restore and database_path.exists():
        shutil.copy2(database_path, before_restore)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(chosen, database_path)
    print("Rollback completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

