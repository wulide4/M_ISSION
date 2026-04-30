from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isd.domain.enums import TaskStatus
from isd.domain.models import SubTask, Task
from isd.infrastructure.repositories.base import from_json, to_json


@dataclass
class TaskRepository:
    conn: Any

    def upsert_task(self, task: Task) -> None:
        self.conn.execute(
            """
            INSERT INTO tasks(id,project_id,name,status,task_type,chain_level,sampling_mode,config_json,created_at,started_at,finished_at,created_from_template_id,summary,latest_error,snapshot_path)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              status=excluded.status,
              started_at=excluded.started_at,
              finished_at=excluded.finished_at,
              summary=excluded.summary,
              latest_error=excluded.latest_error
            """,
            (
                task.id,
                task.project_id,
                task.name,
                task.status.value,
                task.task_type.value,
                task.chain_level.value,
                task.sampling_mode.value,
                task.config.model_dump_json(),
                task.created_at,
                task.started_at,
                task.finished_at,
                task.created_from_template_id,
                task.summary,
                task.latest_error,
                task.snapshot_path,
            ),
        )
        self.conn.commit()

    def replace_subtasks(self, task_id: str, subtasks: list[SubTask]) -> None:
        self.conn.execute("DELETE FROM sub_tasks WHERE task_id=?", (task_id,))
        for s in subtasks:
            self.conn.execute(
                """
                INSERT INTO sub_tasks(id,task_id,station_id,date,system,metric_keys_json,status,current_step_key,duration_ms,error_message)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    s.id,
                    s.task_id,
                    s.station_id,
                    s.date,
                    s.system.value,
                    to_json([m.value for m in s.metric_keys]),
                    s.status.value,
                    s.current_step_key,
                    s.duration_ms,
                    s.error_message,
                ),
            )
        self.conn.commit()

    def update_subtask_status(
        self,
        sub_task_id: str,
        status: TaskStatus,
        *,
        current_step_key: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE sub_tasks
            SET status=?, current_step_key=?, error_message=?
            WHERE id=?
            """,
            (
                status.value,
                current_step_key,
                error_message,
                sub_task_id,
            ),
        )
        self.conn.commit()

    def update_subtasks_for_task(self, task_id: str, status: TaskStatus) -> None:
        self.conn.execute(
            "UPDATE sub_tasks SET status=?, current_step_key=NULL, error_message=NULL WHERE task_id=?",
            (status.value, task_id),
        )
        self.conn.commit()

    def list_tasks(self, project_id: str | None = None) -> list[Task]:
        if project_id:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE project_id=? ORDER BY created_at DESC", (project_id,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [Task(**self._task_dict(r)) for r in rows]

    def delete_task(self, task_id: str) -> None:
        # Delete in dependency order to avoid FK violations
        self.conn.execute("DELETE FROM results WHERE task_id=?", (task_id,))
        self.conn.execute("DELETE FROM task_steps WHERE task_id=?", (task_id,))
        self.conn.execute("DELETE FROM task_logs WHERE task_id=?", (task_id,))
        self.conn.execute("DELETE FROM validation_issues WHERE task_id=?", (task_id,))
        self.conn.execute("DELETE FROM sub_tasks WHERE task_id=?", (task_id,))
        self.conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        self.conn.commit()

    def get_task(self, task_id: str) -> Task | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        return Task(**self._task_dict(row))

    def list_subtasks(self, task_id: str) -> list[SubTask]:
        rows = self.conn.execute("SELECT * FROM sub_tasks WHERE task_id=?", (task_id,)).fetchall()
        out: list[SubTask] = []
        for r in rows:
            out.append(
                SubTask(
                    id=r["id"],
                    task_id=r["task_id"],
                    station_id=r["station_id"],
                    date=r["date"],
                    system=r["system"],
                    metric_keys=from_json(r["metric_keys_json"], []),
                    status=r["status"],
                    current_step_key=r["current_step_key"],
                    duration_ms=r["duration_ms"],
                    error_message=r["error_message"],
                )
            )
        return out

    def _task_dict(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "status": row["status"],
            "task_type": row["task_type"],
            "chain_level": row["chain_level"],
            "sampling_mode": row["sampling_mode"],
            "config": from_json(row["config_json"], {}),
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "created_from_template_id": row["created_from_template_id"],
            "summary": row["summary"],
            "latest_error": row["latest_error"],
            "snapshot_path": row["snapshot_path"],
        }
