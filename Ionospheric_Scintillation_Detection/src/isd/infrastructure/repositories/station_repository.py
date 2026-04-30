from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isd.domain.models import DateRange, Station
from isd.infrastructure.repositories.base import from_json, to_json


@dataclass
class StationRepository:
    conn: Any

    def replace_for_project(self, project_id: str, stations: list[Station]) -> None:
        self.conn.execute("DELETE FROM stations WHERE project_id=?", (project_id,))
        for s in stations:
            self.conn.execute(
                """
                INSERT INTO stations(
                    id,project_id,station_code,latitude,longitude,height,systems_json,coverage_start,coverage_end,
                    coordinate_source,receiver_model,receiver_manufacturer,firmware_version,antenna_model,
                    antenna_calibration_source,is_scintillation_reference_station,ppp_status,ppp_log_path,validation_summary
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    s.id,
                    s.project_id,
                    s.station_code,
                    s.latitude,
                    s.longitude,
                    s.height,
                    to_json([x.value for x in s.systems]),
                    s.time_coverage.start if s.time_coverage else None,
                    s.time_coverage.end if s.time_coverage else None,
                    s.coordinate_source.value,
                    s.receiver_model,
                    s.receiver_manufacturer,
                    s.firmware_version,
                    s.antenna_model,
                    s.antenna_calibration_source,
                    1 if s.is_scintillation_reference_station else 0,
                    s.ppp_status.value,
                    s.ppp_log_path,
                    s.validation_summary,
                ),
            )
        self.conn.commit()

    def list_by_project(self, project_id: str) -> list[Station]:
        rows = self.conn.execute(
            "SELECT * FROM stations WHERE project_id=? ORDER BY station_code", (project_id,)
        ).fetchall()
        out: list[Station] = []
        for row in rows:
            dr = None
            if row["coverage_start"] and row["coverage_end"]:
                dr = DateRange(start=row["coverage_start"], end=row["coverage_end"])
            out.append(
                Station(
                    id=row["id"],
                    project_id=row["project_id"],
                    station_code=row["station_code"],
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                    height=row["height"],
                    systems=from_json(row["systems_json"], []),
                    time_coverage=dr,
                    coordinate_source=row["coordinate_source"],
                    receiver_model=row["receiver_model"],
                    receiver_manufacturer=row["receiver_manufacturer"],
                    firmware_version=row["firmware_version"],
                    antenna_model=row["antenna_model"],
                    antenna_calibration_source=row["antenna_calibration_source"],
                    is_scintillation_reference_station=bool(row["is_scintillation_reference_station"]),
                    ppp_status=row["ppp_status"],
                    ppp_log_path=row["ppp_log_path"],
                    validation_summary=row["validation_summary"],
                )
            )
        return out
