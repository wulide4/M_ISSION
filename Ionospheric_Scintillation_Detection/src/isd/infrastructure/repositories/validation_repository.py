from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isd.domain.models import ValidationIssue


@dataclass
class ValidationIssueRepository:
    conn: Any

    def replace_for_task(self, task_id: str, issues: list[ValidationIssue]) -> None:
        self.conn.execute("DELETE FROM validation_issues WHERE task_id=?", (task_id,))
        for i in issues:
            self.conn.execute(
                """
                INSERT INTO validation_issues(id,task_id,station_id,metric,level,code,message,detail,blocking,recommendation)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    i.id,
                    task_id,
                    i.station_id,
                    i.metric.value if i.metric else None,
                    i.level.value,
                    i.code,
                    i.message,
                    i.detail,
                    1 if i.blocking else 0,
                    i.recommendation,
                ),
            )
        self.conn.commit()
