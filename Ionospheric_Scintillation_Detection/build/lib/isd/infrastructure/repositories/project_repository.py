from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isd.domain.models import DateRange, Project
from isd.infrastructure.repositories.base import from_json, to_json


@dataclass
class ProjectRepository:
    conn: Any

    def upsert(self, project: Project) -> None:
        self.conn.execute(
            """
            INSERT INTO projects(id,name,description,root_path,created_at,updated_at,data_range_start,data_range_end,default_output_path,tags_json,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                root_path=excluded.root_path,
                updated_at=excluded.updated_at,
                data_range_start=excluded.data_range_start,
                data_range_end=excluded.data_range_end,
                default_output_path=excluded.default_output_path,
                tags_json=excluded.tags_json,
                status=excluded.status
            """,
            (
                project.id,
                project.name,
                project.description,
                project.root_path,
                project.created_at,
                project.updated_at,
                project.data_range.start if project.data_range else None,
                project.data_range.end if project.data_range else None,
                project.default_output_path,
                to_json(project.tags),
                project.status.value,
            ),
        )
        self.conn.commit()

    def list_all(self) -> list[Project]:
        rows = self.conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        out: list[Project] = []
        for row in rows:
            dr = None
            if row["data_range_start"] and row["data_range_end"]:
                dr = DateRange(start=row["data_range_start"], end=row["data_range_end"])
            out.append(
                Project(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    root_path=row["root_path"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    data_range=dr,
                    default_output_path=row["default_output_path"],
                    tags=from_json(row["tags_json"], []),
                    status=row["status"],
                )
            )
        return out

    def get(self, project_id: str) -> Project | None:
        row = self.conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return None
        dr = None
        if row["data_range_start"] and row["data_range_end"]:
            dr = DateRange(start=row["data_range_start"], end=row["data_range_end"])
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            root_path=row["root_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            data_range=dr,
            default_output_path=row["default_output_path"],
            tags=from_json(row["tags_json"], []),
            status=row["status"],
        )

    def delete(self, project_id: str) -> None:
        task_rows = self.conn.execute("SELECT id FROM tasks WHERE project_id=?", (project_id,)).fetchall()
        task_ids = [row["id"] for row in task_rows]

        if task_ids:
            placeholders = ",".join(["?"] * len(task_ids))
            self.conn.execute(f"DELETE FROM task_logs WHERE task_id IN ({placeholders})", tuple(task_ids))
            self.conn.execute(f"DELETE FROM task_steps WHERE task_id IN ({placeholders})", tuple(task_ids))
            self.conn.execute(f"DELETE FROM sub_tasks WHERE task_id IN ({placeholders})", tuple(task_ids))
            self.conn.execute(f"DELETE FROM validation_issues WHERE task_id IN ({placeholders})", tuple(task_ids))
            self.conn.execute(f"DELETE FROM results WHERE task_id IN ({placeholders})", tuple(task_ids))
            self.conn.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", tuple(task_ids))

        self.conn.execute("DELETE FROM validation_issues WHERE station_id LIKE ?", (f"{project_id}:%",))
        self.conn.execute("DELETE FROM results WHERE project_id=?", (project_id,))
        self.conn.execute("DELETE FROM project_files WHERE project_id=?", (project_id,))
        self.conn.execute("DELETE FROM stations WHERE project_id=?", (project_id,))
        self.conn.execute("DELETE FROM recent_items WHERE item_type='project' AND item_id=?", (project_id,))
        self.conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        self.conn.commit()
