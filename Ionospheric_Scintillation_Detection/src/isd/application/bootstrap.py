from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from isd.application import channels
from isd.application.command_bus import CommandBus
from isd.application.project_service import ProjectService
from isd.application.report_service import ReportService
from isd.application.result_service import ResultService
from isd.application.settings_service import SettingsService
from isd.application.template_service import TemplateService
from isd.application.task_service import TaskService
from isd.domain.models import ApiResponse
from isd.infrastructure.db.sqlite import Database
from isd.infrastructure.filesystem.file_scan import FileScanner
from isd.infrastructure.filesystem.paths import WorkspacePaths
from isd.infrastructure.filesystem.product_match import ProductMatcher
from isd.infrastructure.filesystem.result_store import ResultStore
from isd.infrastructure.logging.logger import configure_logging
from isd.infrastructure.repositories.project_file_repository import ProjectFileRepository
from isd.infrastructure.repositories.project_repository import ProjectRepository
from isd.infrastructure.repositories.result_repository import ResultRepository
from isd.infrastructure.repositories.settings_repository import SettingsRepository
from isd.infrastructure.repositories.station_repository import StationRepository
from isd.infrastructure.repositories.task_log_repository import TaskLogRepository
from isd.infrastructure.repositories.task_repository import TaskRepository
from isd.infrastructure.repositories.task_step_repository import TaskStepRepository
from isd.infrastructure.repositories.template_repository import TemplateRepository
from isd.infrastructure.repositories.validation_repository import ValidationIssueRepository
from isd.settings import settings
from isd.workers.task_worker import TaskWorkerManager


@dataclass
class AppContext:
    db: Database
    conn: object
    workspace: WorkspacePaths
    command_bus: CommandBus
    project_service: ProjectService
    task_service: TaskService
    result_service: ResultService
    settings_service: SettingsService
    report_service: ReportService
    template_service: TemplateService


def bootstrap(base_dir: Path) -> AppContext:
    configure_logging(settings.log_dir)

    workspace = WorkspacePaths(settings.workspace_path)
    workspace.ensure()

    db = Database(settings.database_path)
    db.init(base_dir / "infrastructure" / "db" / "migrations")
    conn = db.connect()

    project_repo = ProjectRepository(conn)
    station_repo = StationRepository(conn)
    file_repo = ProjectFileRepository(conn)
    task_repo = TaskRepository(conn)
    task_log_repo = TaskLogRepository(conn)
    task_step_repo = TaskStepRepository(conn)
    result_repo = ResultRepository(conn)
    settings_repo = SettingsRepository(conn)
    template_repo = TemplateRepository(conn)
    validation_repo = ValidationIssueRepository(conn)

    scanner = FileScanner()
    matcher = ProductMatcher()
    result_store = ResultStore()
    worker = TaskWorkerManager(workspace, result_store)

    project_service = ProjectService(workspace, project_repo, station_repo, file_repo, scanner, matcher)
    task_service = TaskService(
        workspace=workspace,
        task_repo=task_repo,
        station_repo=station_repo,
        project_file_repo=file_repo,
        validation_repo=validation_repo,
        result_repo=result_repo,
        task_log_repo=task_log_repo,
        task_step_repo=task_step_repo,
        worker=worker,
        settings_repo=settings_repo,
    )
    result_service = ResultService(result_repo, result_store, workspace_root=workspace.root)
    settings_service = SettingsService(settings_repo, base_dir.parent.parent / "config" / "defaults")
    report_service = ReportService(result_repo=result_repo, template_repo=template_repo)
    template_service = TemplateService(template_repo=template_repo)

    bus = CommandBus()

    bus.register(channels.PROJECT_CREATE, project_service.create_project)
    bus.register(channels.PROJECT_LIST, project_service.list_projects)
    bus.register(channels.PROJECT_OPEN, project_service.open_project)
    bus.register(channels.PROJECT_DELETE, project_service.delete_project)
    bus.register(channels.PROJECT_SCAN_FILES, project_service.scan_project_files)
    bus.register(channels.PROJECT_GET_STATIONS, project_service.get_stations)
    bus.register(channels.PROJECT_UPDATE, lambda p: ApiResponse(success=True, data=p))

    bus.register(channels.TASK_VALIDATE, task_service.validate_task)
    bus.register(channels.TASK_CREATE, task_service.create_task)
    bus.register(channels.TASK_START, task_service.start_task)
    bus.register(channels.TASK_PAUSE, task_service.pause_task)
    bus.register(channels.TASK_RESUME, task_service.resume_task)
    bus.register(channels.TASK_STOP, task_service.stop_task)
    bus.register(channels.TASK_DELETE, task_service.delete_task)
    bus.register(channels.TASK_RETRY, task_service.retry_task)
    bus.register(channels.TASK_LIST, task_service.list_tasks)
    bus.register(channels.TASK_GET, task_service.get_task)
    bus.register(channels.TASK_GET_LOGS, task_service.get_logs)
    bus.register(
        channels.TASK_SUBSCRIBE_PROGRESS,
        lambda _: ApiResponse(success=True, data={"subscribed": True}),
    )

    bus.register(channels.RESULT_LIST, result_service.list_results)
    bus.register(channels.RESULT_GET_SERIES, result_service.get_series)
    bus.register(channels.RESULT_GET_GRID, result_service.get_grid)
    bus.register(channels.RESULT_GET_INTERMEDIATE, result_service.get_intermediate)
    bus.register(channels.RESULT_EXPORT, result_service.export_result)

    bus.register(channels.SETTINGS_GET, lambda _: ApiResponse(success=True, data=settings_service.get()))
    bus.register(
        channels.SETTINGS_UPDATE,
        lambda p: ApiResponse(success=True, data=settings_service.update(p)),
    )
    bus.register(
        channels.SETTINGS_GET_DEFAULTS,
        lambda _: ApiResponse(success=True, data=settings_service.get_defaults()),
    )

    bus.register(
        channels.REPORT_PREVIEW,
        lambda p: ApiResponse(
            success=True,
            data=report_service.preview_report(
                p["templateId"], p.get("resultIds", []), p.get("options", {}), p.get("projectId")
            ),
        ),
    )
    bus.register(
        channels.REPORT_EXPORT,
        lambda p: ApiResponse(
            success=True,
            data=report_service.export_report(
                p["templateId"],
                p.get("resultIds", []),
                p.get("options", {}),
                p["outputPath"],
                p.get("projectId"),
            ),
        ),
    )
    bus.register(
        channels.REPORT_LIST_TEMPLATES,
        lambda _: ApiResponse(success=True, data=report_service.list_templates()),
    )

    bus.register(channels.TEMPLATE_LIST, template_service.list_templates)
    bus.register(channels.TEMPLATE_GET, template_service.get_template)
    bus.register(channels.TEMPLATE_SAVE, template_service.save_template)
    bus.register(channels.TEMPLATE_DELETE, template_service.delete_template)

    return AppContext(
        db=db,
        conn=conn,
        workspace=workspace,
        command_bus=bus,
        project_service=project_service,
        task_service=task_service,
        result_service=result_service,
        settings_service=settings_service,
        report_service=report_service,
        template_service=template_service,
    )
