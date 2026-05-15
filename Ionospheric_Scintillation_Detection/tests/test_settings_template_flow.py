from pathlib import Path

from isd.application.settings_service import SettingsService
from isd.domain.enums import ProjectStatus
from isd.application.task_service import TaskService
from isd.application.template_service import TemplateService
from isd.infrastructure.db.sqlite import Database
from isd.infrastructure.filesystem.paths import WorkspacePaths
from isd.infrastructure.filesystem.result_store import ResultStore
from isd.infrastructure.repositories.project_file_repository import ProjectFileRepository
from isd.infrastructure.repositories.result_repository import ResultRepository
from isd.infrastructure.repositories.settings_repository import SettingsRepository
from isd.infrastructure.repositories.station_repository import StationRepository
from isd.infrastructure.repositories.task_log_repository import TaskLogRepository
from isd.infrastructure.repositories.task_repository import TaskRepository
from isd.infrastructure.repositories.task_step_repository import TaskStepRepository
from isd.infrastructure.repositories.template_repository import TemplateRepository
from isd.infrastructure.repositories.validation_repository import ValidationIssueRepository
from isd.workers.task_worker import TaskWorkerManager


def _conn(tmp_path: Path):
    db = Database(tmp_path / "workspace" / "isd.sqlite3")
    migrations = Path(__file__).resolve().parents[1] / "src" / "isd" / "infrastructure" / "db" / "migrations"
    db.init(migrations)
    return db.connect()


def _task_service(tmp_path: Path) -> TaskService:
    conn = _conn(tmp_path)
    workspace = WorkspacePaths(tmp_path / "workspace")
    workspace.ensure()
    settings_repo = SettingsRepository(conn)
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
        settings_repo=settings_repo,
    )


def _seed_project(service: TaskService, project_id: str) -> None:
    now = "2026-04-21T00:00:00Z"
    service.task_repo.conn.execute(
        """
        INSERT INTO projects(
            id,name,description,root_path,created_at,updated_at,data_range_start,data_range_end,default_output_path,tags_json,status
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            project_id,
            "demo",
            "",
            str(Path.cwd()),
            now,
            now,
            None,
            None,
            str(Path.cwd() / "workspace" / "outputs"),
            "[]",
            ProjectStatus.ACTIVE.value,
        ),
    )
    service.task_repo.conn.commit()


def test_settings_service_persists_nested_defaults(tmp_path: Path):
    conn = _conn(tmp_path)
    service = SettingsService(SettingsRepository(conn), Path(__file__).resolve().parents[1] / "config" / "defaults")

    defaults = service.get()
    assert defaults["defaultAlgorithmConfig"]["cutoffElevationDeg"] == 30
    assert "ROTI" in defaults["thresholdPresets"]

    updated = service.update(
        {
            "defaultAlgorithmConfig": {"cutoffElevationDeg": 35},
            "receiverThresholdPresets": {"RX_A": {"ROTI": 0.45, "AATR": 0.18}},
        }
    )
    assert updated["defaultAlgorithmConfig"]["cutoffElevationDeg"] == 35
    assert updated["defaultAlgorithmConfig"]["minArcEpochs"] == 10
    assert updated["receiverThresholdPresets"]["RX_A"]["ROTI"] == 0.45

    service_reloaded = SettingsService(SettingsRepository(conn), Path(__file__).resolve().parents[1] / "config" / "defaults")
    reloaded = service_reloaded.get()
    assert reloaded["defaultAlgorithmConfig"]["cutoffElevationDeg"] == 35
    assert reloaded["receiverThresholdPresets"]["RX_A"]["AATR"] == 0.18


def test_template_service_supports_save_load_and_overwrite_strategy(tmp_path: Path):
    conn = _conn(tmp_path)
    service = TemplateService(TemplateRepository(conn))

    first = service.save_template(
        {
            "name": "task_demo",
            "scope": "TASK",
            "overwriteStrategy": "OVERWRITE",
            "payload": {"config": {"chain_level": "FORMAL", "metrics": ["ROTI"]}},
        }
    )
    assert first.success is True
    first_id = first.data["id"]

    reject = service.save_template(
        {
            "name": "task_demo",
            "scope": "TASK",
            "overwriteStrategy": "REJECT",
            "payload": {"config": {"chain_level": "EXPERIMENTAL", "metrics": ["AATR"]}},
        }
    )
    assert reject.success is False
    assert reject.error.code == "TEMPLATE_EXISTS"

    overwrite = service.save_template(
        {
            "name": "task_demo",
            "scope": "TASK",
            "overwriteStrategy": "OVERWRITE",
            "payload": {"config": {"chain_level": "EXPERIMENTAL", "metrics": ["AATR"]}},
        }
    )
    assert overwrite.success is True
    assert overwrite.data["id"] == first_id

    create_new = service.save_template(
        {
            "name": "task_demo",
            "scope": "TASK",
            "overwriteStrategy": "CREATE_NEW",
            "payload": {"config": {"chain_level": "DEGRADED", "metrics": ["DIXSG"]}},
        }
    )
    assert create_new.success is True
    assert create_new.data["id"] != first_id

    listed = service.list_templates({"scope": "TASK"})
    assert listed.success is True
    assert len(listed.data) >= 2

    loaded = service.get_template({"templateId": first_id})
    assert loaded.success is True
    assert loaded.data["payload"]["config"]["chain_level"] == "EXPERIMENTAL"

    deleted = service.delete_template({"templateId": first_id})
    assert deleted.success is True


def test_task_create_records_template_and_source_fields(tmp_path: Path):
    service = _task_service(tmp_path)
    _seed_project(service, "proj_1")
    payload = {
        "name": "single_task",
        "taskType": "SINGLE",
        "templateId": "tpl_task_demo",
        "config": {
            "project_id": "proj_1",
            "station_ids": ["ALBH"],
            "date_range": {"start": "2024-03-24", "end": "2024-03-24"},
            "systems": ["GPS"],
            "metrics": ["ROTI"],
            "chain_level": "FORMAL",
            "sampling_mode": "STANDARD_30S",
            "output_path": str(tmp_path / "workspace" / "outputs"),
            "parallelism": 1,
            "enable_intermediate_save": True,
            "enable_intermediate_preview": True,
            "enable_nav_fallback": False,
            "enable_experimental_sigma_phi_f": False,
            "enable_1s_resample": False,
            "parameter_source": "template",
            "threshold_source": "template",
            "source_template_id": "tpl_task_demo",
            "threshold_config": [],
            "algorithm_config": {},
        },
    }

    rsp = service.create_task(payload)
    assert rsp.success is True
    task = rsp.data["task"]
    assert task["created_from_template_id"] == "tpl_task_demo"
    assert task["config"]["parameter_source"] == "template"
    assert task["config"]["threshold_source"] == "template"
    assert task["config"]["source_template_id"] == "tpl_task_demo"
