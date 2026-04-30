from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isd.application.ids import utc_now
from isd.infrastructure.repositories.base import from_json, to_json


@dataclass
class SettingsRepository:
    conn: Any

    def get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        return from_json(row["value_json"], default)

    def set(self, key: str, value: Any) -> None:
        self.conn.execute(
            """
            INSERT INTO settings(key,value_json,updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at
            """,
            (key, to_json(value), utc_now()),
        )
        self.conn.commit()
