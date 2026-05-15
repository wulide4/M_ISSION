from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from isd.domain.models import ResultSet
from isd.infrastructure.repositories.base import from_json, to_json


@dataclass
class ResultRepository:
    conn: Any

    def insert_many(self, results: list[ResultSet]) -> None:
        for r in results:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO results(
                    id,task_id,sub_task_id,project_id,metric,station_id,system,satellite_prn,satellite_ids_json,chain_level,
                    sampling_mode,coordinate_source,receiver_model,threshold_source,parameter_source_summary,
                    data_path,preview_image_path,stats_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    r.id,
                    r.task_id,
                    r.sub_task_id,
                    r.project_id,
                    r.metric.value,
                    r.station_id,
                    r.system.value if r.system else None,
                    r.satellite_prn,
                    json.dumps(r.satellite_ids or []),
                    r.chain_level.value,
                    r.sampling_mode.value,
                    r.coordinate_source.value if r.coordinate_source else None,
                    r.receiver_model,
                    r.threshold_source.value if r.threshold_source else None,
                    r.parameter_source_summary,
                    r.data_path,
                    r.preview_image_path,
                    r.stats.model_dump_json(),
                    r.created_at,
                ),
            )
        self.conn.commit()

    def list_results(self, project_id: str, task_id: str | None = None) -> list[ResultSet]:
        if task_id:
            rows = self.conn.execute(
                "SELECT * FROM results WHERE project_id=? AND task_id=? ORDER BY created_at DESC",
                (project_id, task_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM results WHERE project_id=? ORDER BY created_at DESC", (project_id,)
            ).fetchall()
        out: list[ResultSet] = []
        for r in rows:
            # Parse satellite_ids_json, handle column missing on old DBs
            sat_ids_raw = r["satellite_ids_json"] if "satellite_ids_json" in r.keys() else "[]"
            try:
                sat_ids = json.loads(sat_ids_raw) if sat_ids_raw else []
            except (json.JSONDecodeError, TypeError):
                sat_ids = []
            out.append(
                ResultSet(
                    id=r["id"],
                    task_id=r["task_id"],
                    sub_task_id=r["sub_task_id"],
                    project_id=r["project_id"],
                    metric=r["metric"],
                    station_id=r["station_id"],
                    system=r["system"],
                    satellite_prn=r["satellite_prn"],
                    satellite_ids=sat_ids,
                    chain_level=r["chain_level"],
                    sampling_mode=r["sampling_mode"],
                    coordinate_source=r["coordinate_source"],
                    receiver_model=r["receiver_model"],
                    threshold_source=r["threshold_source"],
                    parameter_source_summary=r["parameter_source_summary"],
                    data_path=r["data_path"],
                    preview_image_path=r["preview_image_path"],
                    stats=from_json(r["stats_json"], {}),
                    created_at=r["created_at"],
                )
            )
        return out

    def delete_by_task(self, task_id: str) -> None:
        self.conn.execute("DELETE FROM results WHERE task_id=?", (task_id,))
        self.conn.commit()
