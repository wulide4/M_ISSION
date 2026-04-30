from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isd.application.ids import make_id
from isd.domain.models import TaskLogEvent


@dataclass
class TaskLogRepository:
    conn: Any

    def append(self, event: TaskLogEvent, *, log_file_path: str | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO task_logs(id,task_id,sub_task_id,timestamp,level,step_key,message,detail,log_file_path)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                make_id("log"),
                event.task_id,
                event.sub_task_id,
                event.timestamp,
                event.level.value,
                event.step_key,
                event.message,
                event.detail,
                log_file_path,
            ),
        )
        self.conn.commit()

    def list_by_task(self, task_id: str, limit: int = 2000) -> list[TaskLogEvent]:
        rows = self.conn.execute(
            """
            SELECT task_id,sub_task_id,timestamp,level,step_key,message,detail
            FROM task_logs WHERE task_id=?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()
        return [
            TaskLogEvent(
                task_id=row["task_id"],
                sub_task_id=row["sub_task_id"],
                timestamp=row["timestamp"],
                level=row["level"],
                step_key=row["step_key"],
                message=row["message"],
                detail=row["detail"],
            )
            for row in rows
        ]

    def delete_by_task(self, task_id: str) -> None:
        self.conn.execute("DELETE FROM task_logs WHERE task_id=?", (task_id,))
        self.conn.commit()

