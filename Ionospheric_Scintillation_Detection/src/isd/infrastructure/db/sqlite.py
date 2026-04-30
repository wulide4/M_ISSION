from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from isd.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Database:
    path: Path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init(self, migrations_dir: Path) -> None:
        with self.connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            files = sorted(migrations_dir.glob("*.sql"))
            for migration_file in files:
                version = migration_file.stem
                row = conn.execute(
                    "SELECT version FROM schema_migrations WHERE version = ?", (version,)
                ).fetchone()
                if row:
                    continue
                sql = migration_file.read_text(encoding="utf-8")
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES(?, datetime('now'))",
                    (version,),
                )
                logger.info("migration_applied", version=version)
            conn.commit()
