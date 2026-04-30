from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isd.domain.models import ProjectFile
from isd.infrastructure.repositories.base import from_json, to_json


@dataclass
class ProjectFileRepository:
    conn: Any

    def replace_for_project(self, project_id: str, files: list[ProjectFile]) -> None:
        self.conn.execute("DELETE FROM project_files WHERE project_id=?", (project_id,))
        for f in files:
            self.conn.execute(
                """
                INSERT INTO project_files(
                    id,project_id,station_id,kind,file_path,file_name,rinex_version,sampling_interval_sec,
                    systems_json,file_date,matched,validation_status,issues_json,metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    f.id,
                    f.project_id,
                    f.station_id,
                    f.kind.value,
                    f.file_path,
                    f.file_name,
                    f.rinex_version,
                    f.sampling_interval_sec,
                    to_json([x.value for x in f.systems]) if f.systems else None,
                    f.file_date,
                    1 if f.matched else 0,
                    f.validation_status.value,
                    to_json(f.issues),
                    to_json(f.metadata_json or {}),
                ),
            )
        self.conn.commit()

    def list_by_project(self, project_id: str) -> list[ProjectFile]:
        rows = self.conn.execute(
            "SELECT * FROM project_files WHERE project_id=? ORDER BY file_name", (project_id,)
        ).fetchall()
        out: list[ProjectFile] = []
        for row in rows:
            out.append(
                ProjectFile(
                    id=row["id"],
                    project_id=row["project_id"],
                    station_id=row["station_id"],
                    kind=row["kind"],
                    file_path=row["file_path"],
                    file_name=row["file_name"],
                    rinex_version=row["rinex_version"],
                    sampling_interval_sec=row["sampling_interval_sec"],
                    systems=from_json(row["systems_json"], None),
                    file_date=row["file_date"],
                    matched=bool(row["matched"]),
                    validation_status=row["validation_status"],
                    issues=from_json(row["issues_json"], []),
                    metadata_json=from_json(row["metadata_json"], {}),
                )
            )
        return out

    def count_kind(self, project_id: str, kind: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM project_files WHERE project_id=? AND kind=?", (project_id, kind)
        ).fetchone()
        return int(row["c"]) if row else 0
