from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from isd.application.result_service import ResultService
from isd.domain.enums import ChainLevel, GnssSystem, MetricKey, SamplingMode, ThresholdSource
from isd.domain.models import ResultSet, ResultStats
from isd.infrastructure.db.sqlite import Database
from isd.infrastructure.filesystem.result_store import ResultStore
from isd.infrastructure.repositories.result_repository import ResultRepository


def _service(tmp_path: Path) -> ResultService:
    db = Database(tmp_path / "workspace" / "isd.sqlite3")
    migrations = Path(__file__).resolve().parents[1] / "src" / "isd" / "infrastructure" / "db" / "migrations"
    db.init(migrations)
    conn = db.connect()
    return ResultService(ResultRepository(conn), ResultStore())


def _seed_result(service: ResultService, project_id: str, result_id: str, data_path: Path) -> None:
    row = ResultSet(
        id=result_id,
        task_id="task_1",
        sub_task_id="sub_1",
        project_id=project_id,
        metric=MetricKey.ROTI,
        station_id="ABCD",
        system=GnssSystem.GPS,
        chain_level=ChainLevel.FORMAL,
        sampling_mode=SamplingMode.STANDARD_30S,
        threshold_source=ThresholdSource.LITERATURE_REFERENCE,
        parameter_source_summary="unit-test",
        data_path=str(data_path),
        stats=ResultStats(min=1.0, max=2.0, mean=1.5, missing_ratio=0.0, event_count=0),
        created_at="2026-04-21T00:00:00Z",
    )
    service.repo.insert_many([row])


def test_export_result_by_data_path(tmp_path: Path):
    service = _service(tmp_path)
    source = tmp_path / "results" / "demo.npz"
    service.store.save_series(source, np.arange(5, dtype=int), np.linspace(0, 1, 5))

    out = tmp_path / "exports" / "demo.mat"
    rsp = service.export_result({"dataPath": str(source), "outputPath": str(out)})

    assert rsp.success is True
    assert Path(rsp.data["outputPath"]).exists()
    assert out.suffix.lower() == ".mat"


def test_export_result_by_result_reference(tmp_path: Path):
    service = _service(tmp_path)
    source = tmp_path / "results" / "seed.npz"
    service.store.save_series(source, np.arange(3, dtype=int), np.array([1.0, 2.0, 3.0]))
    _seed_result(service, "proj_1", "res_1", source)

    out = tmp_path / "exports" / "seed.parquet"
    rsp = service.export_result({"projectId": "proj_1", "resultId": "res_1", "outputPath": str(out)})

    assert rsp.success is True
    assert Path(rsp.data["outputPath"]).exists()
    assert out.suffix.lower() == ".parquet"


def test_export_result_validates_input(tmp_path: Path):
    service = _service(tmp_path)

    rsp_1 = service.export_result({"dataPath": "x.npz"})
    assert rsp_1.success is False
    assert rsp_1.error.code == "MISSING_OUTPUT_PATH"

    rsp_2 = service.export_result({"outputPath": str(tmp_path / "x.mat")})
    assert rsp_2.success is False
    assert rsp_2.error.code == "MISSING_RESULT_REFERENCE"

    rsp_3 = service.export_result(
        {"projectId": "proj_none", "resultId": "res_none", "outputPath": str(tmp_path / "x.mat")}
    )
    assert rsp_3.success is False
    assert rsp_3.error.code == "RESULT_NOT_FOUND"


def test_get_intermediate_prefers_project_scoped_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service = _service(tmp_path)
    monkeypatch.chdir(tmp_path)
    interm = (
        tmp_path
        / "workspace"
        / "projects"
        / "proj_1"
        / "tasks"
        / "task_1"
        / "intermediate"
    )
    interm.mkdir(parents=True, exist_ok=True)
    (interm / "sub_1_ROTI.json").write_text('{"k":1}', encoding="utf-8")
    (interm / "sub_1_AATR.json").write_text('{"k":2}', encoding="utf-8")

    rsp = service.get_intermediate(
        {"projectId": "proj_1", "taskId": "task_1", "subTaskId": "sub_1", "stepKey": "ROTI"}
    )
    assert rsp.success is True
    files = rsp.data["files"]
    assert len(files) >= 1
    names = [Path(row["filePath"]).name for row in files]
    assert "sub_1_ROTI.json" in names


def test_get_grid_returns_coverage(tmp_path: Path):
    service = _service(tmp_path)
    source = tmp_path / "results" / "grid_seed.npz"
    service.store.save_payload(
        source,
        {
            "time": np.arange(4, dtype=int),
            "values": np.array([1.0, 2.0, 3.0, 4.0], dtype=float),
            "grid": np.array([[1.0, np.nan], [2.0, 4.0]], dtype=float),
        },
    )
    _seed_result(service, "proj_1", "res_grid", source)

    rsp = service.get_grid({"projectId": "proj_1", "resultId": "res_grid"})
    assert rsp.success is True
    assert rsp.data["shape"] == [2, 2]
    assert rsp.data["validCount"] == 3
    assert rsp.data["totalCount"] == 4
    assert rsp.data["coverage"] == pytest.approx(0.75)


def test_get_grid_returns_not_available_for_series_only_result(tmp_path: Path):
    service = _service(tmp_path)
    source = tmp_path / "results" / "series_only.npz"
    service.store.save_series(source, np.arange(3, dtype=int), np.array([1.0, 2.0, 3.0], dtype=float))
    _seed_result(service, "proj_2", "res_series", source)

    rsp = service.get_grid({"projectId": "proj_2", "resultId": "res_series"})
    assert rsp.success is False
    assert rsp.error.code == "GRID_NOT_AVAILABLE"
