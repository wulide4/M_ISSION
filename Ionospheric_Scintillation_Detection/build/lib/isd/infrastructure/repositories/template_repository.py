from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isd.application.ids import utc_now
from isd.domain.models import Template
from isd.infrastructure.repositories.base import from_json, to_json


@dataclass
class TemplateRepository:
    conn: Any

    def get(self, template_id: str) -> Template | None:
        row = self.conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
        if not row:
            return None
        return Template(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            scope=row["scope"],
            is_default=bool(row["is_default"]),
            payload=from_json(row["payload_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_all(self) -> list[Template]:
        rows = self.conn.execute("SELECT * FROM templates ORDER BY updated_at DESC").fetchall()
        return [self._row_to_model(r) for r in rows]

    def list_by_scope(self, scope: str) -> list[Template]:
        rows = self.conn.execute(
            "SELECT * FROM templates WHERE scope=? ORDER BY updated_at DESC",
            (scope,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def find_by_scope_name(self, scope: str, name: str) -> Template | None:
        row = self.conn.execute(
            "SELECT * FROM templates WHERE scope=? AND name=? ORDER BY updated_at DESC LIMIT 1",
            (scope, name),
        ).fetchone()
        if not row:
            return None
        return self._row_to_model(row)

    def upsert(self, template: Template) -> Template:
        now = utc_now()
        created_at = template.created_at or now
        updated_at = now
        self.conn.execute(
            """
            INSERT INTO templates(id,name,description,scope,is_default,payload_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              description=excluded.description,
              scope=excluded.scope,
              is_default=excluded.is_default,
              payload_json=excluded.payload_json,
              updated_at=excluded.updated_at
            """,
            (
                template.id,
                template.name,
                template.description,
                template.scope.value,
                1 if template.is_default else 0,
                to_json(template.payload),
                created_at,
                updated_at,
            ),
        )
        self.conn.commit()
        stored = self.get(template.id)
        assert stored is not None
        return stored

    def delete(self, template_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
        self.conn.commit()
        return int(cur.rowcount or 0) > 0

    def _row_to_model(self, row: Any) -> Template:
        return Template(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            scope=row["scope"],
            is_default=bool(row["is_default"]),
            payload=from_json(row["payload_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
