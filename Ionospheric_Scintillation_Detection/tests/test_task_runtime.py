from __future__ import annotations

import time
from pathlib import Path

from isd.application.task_service import TaskService
from isd.domain.enums import CoordinateSource, FileKind, GnssSystem, PppStatus, ProjectStatus, TaskStatus
from isd.domain.models import Project, ProjectFile, Station
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


def _service(tmp_path: Path) -> TaskService:
    db_path = tmp_path / "test_runtime.sqlite3"
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
    now = "2026-04-20T00:00:00Z"
    project = Project(
        id=project_id,
        name="runtime_project",
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


def _seed_station(service: TaskService, project_id: str, station_code: str) -> None:
    station = Station(
        id=f"{project_id}:{station_code}",
        project_id=project_id,
        station_code=station_code,
        systems=[GnssSystem.GPS],
        coordinate_source=CoordinateSource.PRECISE_FILE,
        ppp_status=PppStatus.SUCCESS,
    )
    service.station_repo.replace_for_project(project_id, [station])


def _seed_files(service: TaskService, project_id: str, station_code: str) -> None:
    service.project_file_repo.replace_for_project(
        project_id,
        [
            ProjectFile(
                id="obs",
                project_id=project_id,
                station_id=station_code,
                kind=FileKind.OBS,
                file_path="obs.24o",
                file_name="obs.24o",
                file_date="2024-03-24",
                systems=[GnssSystem.GPS],
            ),
            ProjectFile(
                id="sp3",
                project_id=project_id,
                station_id=None,
                kind=FileKind.SP3,
                file_path="igs24084.sp3",
                file_name="igs24084.sp3",
                file_date="2024-03-24",
            ),
            ProjectFile(
                id="clk",
                project_id=project_id,
                station_id=None,
                kind=FileKind.CLK,
                file_path="igs24084.clk",
                file_name="igs24084.clk",
                file_date="2024-03-24",
            ),
            ProjectFile(
                id="atx",
                project_id=project_id,
                station_id=None,
                kind=FileKind.ATX,
                file_path="igs20.atx",
                file_name="igs20.atx",
            ),
        ],
    )


def _wait_task_terminal(service: TaskService, task_id: str, timeout_sec: float = 120.0) -> TaskStatus:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        rsp = service.get_task({"taskId": task_id})
        if rsp.success:
            status = TaskStatus(rsp.data["task"]["status"])
            if status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED}:
                return status
        time.sleep(0.2)
    raise TimeoutError(f"Task {task_id} did not finish within {timeout_sec}s")


def test_task_runtime_snapshot_and_logs(tmp_path: Path):
    service = _service(tmp_path)
    project_id = "proj_runtime_1"
    _seed_project(service, project_id)

    create_rsp = service.create_task(
        {
            "name": "runtime_task",
            "taskType": "SINGLE",
            "config": {
                "project_id": project_id,
                "station_ids": ["ABCD"],
                "date_range": {"start": "2024-03-24", "end": "2024-03-25"},
                "systems": ["GPS"],
                "metrics": ["ROTI", "AATR"],
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
    start_rsp = service.start_task({"taskId": task_id})
    assert start_rsp.success is True
    status = _wait_task_terminal(service, task_id)
    assert status == TaskStatus.COMPLETED

    logs_rsp = service.get_logs({"taskId": task_id})
    assert logs_rsp.success is True
    assert len(logs_rsp.data) > 0

    snapshot = service.task_repo.get_task(task_id).snapshot_path
    assert Path(snapshot).exists()
    log_file = Path(snapshot).parent / "logs" / "runtime.log.jsonl"
    assert log_file.exists()


def test_task_stop_then_retry(tmp_path: Path):
    service = _service(tmp_path)
    project_id = "proj_runtime_2"
    _seed_project(service, project_id)

    create_rsp = service.create_task(
        {
            "name": "stop_retry_task",
            "taskType": "SINGLE",
            "config": {
                "project_id": project_id,
                "station_ids": ["ABCD"],
                "date_range": {"start": "2024-03-24", "end": "2024-03-25"},
                "systems": ["GPS"],
                "metrics": ["ROTI", "AATR"],
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
    assert service.stop_task({"taskId": task_id}).success is True
    status1 = _wait_task_terminal(service, task_id)
    assert status1 in {TaskStatus.CANCELLED, TaskStatus.COMPLETED}

    retry_rsp = service.retry_task({"taskId": task_id})
    assert retry_rsp.success is True
    status2 = _wait_task_terminal(service, task_id)
    assert status2 in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}

    rows = service.task_log_repo.list_by_task(task_id)
    assert len(rows) > 0


def test_task_result_metadata_contains_provider_summary(tmp_path: Path):
    service = _service(tmp_path)
    project_id = "proj_runtime_provider"
    _seed_project(service, project_id)
    _seed_station(service, project_id, "ABCD")
    _seed_files(service, project_id, "ABCD")

    create_rsp = service.create_task(
        {
            "name": "provider_meta_task",
            "taskType": "SINGLE",
            "config": {
                "project_id": project_id,
                "station_ids": ["ABCD"],
                "date_range": {"start": "2024-03-24", "end": "2024-03-24"},
                "systems": ["GPS"],
                "metrics": ["ROTI"],
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
    status = _wait_task_terminal(service, task_id)
    assert status == TaskStatus.COMPLETED

    rows = service.result_repo.list_results(project_id, task_id)
    assert len(rows) >= 1
    first = rows[0]
    assert first.coordinate_source == CoordinateSource.PRECISE_FILE
    assert "providers=coord:" in first.parameter_source_summary
