from __future__ import annotations

import json
import sqlite3
from typing import Any


def to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def from_json(data: str | None, default: Any) -> Any:
    if not data:
        return default
    return json.loads(data)


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}
