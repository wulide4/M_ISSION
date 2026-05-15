from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isd.application.ids import make_id
from isd.domain.models import ProcessingStep
from isd.infrastructure.repositories.base import from_json, to_json


@dataclass
class TaskStepRepository:
    conn: Any

    def upsert(self, task_id: str, sub_task_id: str | None, step: ProcessingStep) -> None:
        step_id = f"{task_id}:{sub_task_id or 'task'}:{step.key}"
        row = self.conn.execute("SELECT id FROM task_steps WHERE id=?", (step_id,)).fetchone()
        if row:
            self.conn.execute(
                """
                UPDATE task_steps
                SET status=?, started_at=?, finished_at=?, input_summary=?, output_summary=?, artifact_paths_json=?
                WHERE id=?
                """,
                (
                    step.status.value,
                    step.started_at,
                    step.finished_at,
                    step.input_summary,
                    step.output_summary,
                    to_json(step.artifact_paths),
                    step_id,
                ),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO task_steps(
                    id,task_id,sub_task_id,step_key,label,status,started_at,finished_at,input_summary,output_summary,artifact_paths_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    step_id,
                    task_id,
                    sub_task_id,
                    step.key,
                    step.label,
                    step.status.value,
                    step.started_at,
                    step.finished_at,
                    step.input_summary,
                    step.output_summary,
                    to_json(step.artifact_paths),
                ),
            )
        self.conn.commit()

    def list_by_task(self, task_id: str) -> list[ProcessingStep]:
        rows = self.conn.execute(
            "SELECT * FROM task_steps WHERE task_id=? ORDER BY started_at ASC", (task_id,)
        ).fetchall()
        return [
            ProcessingStep(
                key=row["step_key"],
                label=row["label"],
                status=row["status"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                input_summary=row["input_summary"],
                output_summary=row["output_summary"],
                artifact_paths=from_json(row["artifact_paths_json"], []),
            )
            for row in rows
        ]

    def delete_by_task(self, task_id: str) -> None:
        self.conn.execute("DELETE FROM task_steps WHERE task_id=?", (task_id,))
        self.conn.commit()

