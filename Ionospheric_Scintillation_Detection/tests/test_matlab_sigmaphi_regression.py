from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat

from isd.application.task_service import TaskService
from isd.domain.enums import ProjectStatus, StepStatus, TaskStatus
from isd.domain.models import Project
from isd.infrastructure.db.sqlite import Database
from isd.infrastructure.filesystem.paths import WorkspacePaths
from isd.infrastructure.filesystem.result_store import ResultStore
from isd.infrastructure.repositories.project_file_repository import ProjectFileRepository
from isd.infrastructure.repositories.result_repository import ResultRepository
from isd.infrastructure.repositories.station_repository import StationRepository
from isd.infrastructure.repositories.task_log_repository import TaskLogRepository
from isd.infrastructure.repositories.task_repository import TaskRepository
from isd.infrastructure.repositories.task_step_repository import TaskStepRepository
from isd.infrastructure.repositories.validation_repository import ValidationIssueRepository
from isd.workers.task_worker import TaskWorkerManager
from isd.algorithms.matlab_metrics import load_gps_sigmaphi_from_mat

STATIONS = ["ALBH", "BAMF", "CHWK", "HOLB", "NANO", "UCLU"]


def _service(tmp_path: Path) -> TaskService:
    db_path = tmp_path / "test_sigmaphi.sqlite3"
    db = Database(db_path)
    migrations = Path(__file__).resolve().parents[1] / "src" / "isd" / "infrastructure" / "db" / "migrations"
    db.init(migrations)
    conn = db.connect()
    workspace = WorkspacePaths(tmp_path / "workspace")
    workspace.ensure()
    return TaskService(
        workspace=workspace,
        task_repo=TaskRepository(conn),
        station_repo=StationRepository(conn),
        project_file_repo=ProjectFileRepository(conn),
        validation_repo=ValidationIssueRepository(conn),
        result_repo=ResultRepository(conn),
        task_log_repo=TaskLogRepository(conn),
        task_step_repo=TaskStepRepository(conn),
        worker=TaskWorkerManager(workspace, ResultStore()),
    )


def _seed_project(service: TaskService, project_id: str) -> None:
    now = "2026-04-21T00:00:00Z"
    project = Project(
        id=project_id,
        name="sigmaphi_project",
        description="",
        root_path=str(Path.cwd()),
        created_at=now,
        updated_at=now,
        default_output_path=str(Path.cwd() / "workspace" / "reports"),
        tags=[],
        status=ProjectStatus.ACTIVE,
    )
    service.task_repo.conn.execute(
        """
        INSERT INTO projects(
            id,name,description,root_path,created_at,updated_at,data_range_start,data_range_end,default_output_path,tags_json,status
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            project.id,
            project.name,
            project.description,
            project.root_path,
            project.created_at,
            project.updated_at,
            None,
            None,
            project.default_output_path,
            "[]",
            project.status.value,
        ),
    )
    service.task_repo.conn.commit()


def _wait_task_terminal(service: TaskService, task_id: str, timeout_sec: float = 20.0) -> TaskStatus:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        rsp = service.get_task({"taskId": task_id})
        if rsp.success:
            status = TaskStatus(rsp.data["task"]["status"])
            if status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED}:
                return status
        time.sleep(0.2)
    raise TimeoutError(f"Task {task_id} did not finish within {timeout_sec}s")


def test_sigmaphi_l1_loader_regression_24084():
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    sigmaphi_root = repo_root / "resSIGMAPHI" / "GPSsigmaphi24084"
    if not sigmaphi_root.exists():
        pytest.skip("resSIGMAPHI/GPSsigmaphi24084 not found")

    for station in STATIONS:
        file_path = sigmaphi_root / f"{station.lower()}24084GPSsigmaphi.mat"
        if not file_path.exists():
            pytest.skip(f"missing sigmaphi baseline for station {station}")
        parsed = load_gps_sigmaphi_from_mat(file_path).l1
        direct = np.asarray(
            loadmat(file_path, squeeze_me=True, struct_as_record=False)["GPSsigmaphi"].L1,
            dtype=float,
        )

        assert parsed is not None
        mae = float(np.nanmean(np.abs(parsed - direct)))
        assert parsed.shape == direct.shape
        assert mae < 1e-12


def test_sigmaphi_worker_result_matches_matlab_24084(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    sigmaphi_root = repo_root / "resSIGMAPHI"
    golden_file = repo_root / "resSIGMAPHI" / "GPSsigmaphi24084" / "albh24084GPSsigmaphi.mat"
    if not sigmaphi_root.exists() or not golden_file.exists():
        pytest.skip("sigmaphi baseline data not found")

    monkeypatch.setenv("ISD_MATLAB_SIGMAPHI_ROOT", str(sigmaphi_root))

    service = _service(tmp_path)
    project_id = "proj_sigmaphi_1"
    _seed_project(service, project_id)

    create_rsp = service.create_task(
        {
            "name": "sigmaphi_task",
            "taskType": "SINGLE",
            "config": {
                "project_id": project_id,
                "station_ids": ["ALBH"],
                "date_range": {"start": "2024-03-24", "end": "2024-03-24"},
                "systems": ["GPS"],
                "metrics": ["SIGMA_PHI_F"],
                "chain_level": "FORMAL",
                "sampling_mode": "STANDARD_30S",
                "output_path": str(tmp_path / "output"),
                "parallelism": 1,
                "enable_intermediate_save": True,
                "enable_intermediate_preview": True,
                "enable_nav_fallback": False,
                "enable_experimental_sigma_phi_f": False,
                "enable_1s_resample": False,
                "threshold_config": [],
                "algorithm_config": {},
            },
        }
    )
    task_id = create_rsp.data["task"]["id"]
    assert service.start_task({"taskId": task_id}).success is True
    assert _wait_task_terminal(service, task_id) == TaskStatus.COMPLETED

    rows = service.result_repo.list_results(project_id=project_id)
    assert rows
    result = rows[0]
    assert result.metric.value == "SIGMA_PHI_F"

    with np.load(result.data_path) as npz:
        actual = np.asarray(npz["values"], dtype=float)
    expected = np.asarray(
        loadmat(golden_file, squeeze_me=True, struct_as_record=False)["GPSsigmaphi"].L1,
        dtype=float,
    )
    mae = float(np.nanmean(np.abs(actual - expected)))
    assert actual.shape == expected.shape
    assert mae < 1e-12

    steps = service.task_step_repo.list_by_task(task_id)
    step_map = {step.key: step for step in steps}
    required = {
        "sigmaphi_cutoff_elevation",
        "sigmaphi_short_arc_removal",
        "sigmaphi_cycle_slip_detection",
        "sigmaphi_cycle_slip_repair",
        "sigmaphi_geodetic_detrending",
        "sigmaphi_polynomial_detrending",
        "sigmaphi_butterworth_filter",
        "sigmaphi_moving_window_sigma",
        "sigma_phi_f_compute",
    }
    assert required.issubset(set(step_map.keys()))
    for key in required:
        step = step_map[key]
        assert step.status == StepStatus.COMPLETED
        if key.startswith("sigmaphi_"):
            assert len(step.artifact_paths) >= 1
            for artifact_path in step.artifact_paths:
                assert Path(artifact_path).exists()
