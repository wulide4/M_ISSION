from __future__ import annotations

from pathlib import Path

from isd.application.project_service import ProjectService
from isd.infrastructure.db.sqlite import Database
from isd.infrastructure.filesystem.file_scan import FileScanner
from isd.infrastructure.filesystem.paths import WorkspacePaths
from isd.infrastructure.filesystem.product_match import ProductMatcher
from isd.infrastructure.repositories.project_file_repository import ProjectFileRepository
from isd.infrastructure.repositories.project_repository import ProjectRepository
from isd.infrastructure.repositories.station_repository import StationRepository


class _DummyProjectRepo:
    def list_all(self):
        return []


def _full_service(tmp_path: Path) -> ProjectService:
    workspace = WorkspacePaths(tmp_path / "workspace")
    workspace.ensure()
    db = Database(tmp_path / "workspace" / "isd.sqlite3")
    migrations = (
        Path(__file__).resolve().parents[1] / "src" / "isd" / "infrastructure" / "db" / "migrations"
    )
    db.init(migrations)
    conn = db.connect()
    return ProjectService(
        workspace=workspace,
        project_repo=ProjectRepository(conn),
        station_repo=StationRepository(conn),
        file_repo=ProjectFileRepository(conn),
        scanner=FileScanner(),
        matcher=ProductMatcher(),
    )


def test_project_service_list_projects_accepts_payload():
    service = ProjectService(
        workspace=None,  # type: ignore[arg-type]
        project_repo=_DummyProjectRepo(),  # type: ignore[arg-type]
        station_repo=None,  # type: ignore[arg-type]
        file_repo=None,  # type: ignore[arg-type]
        scanner=None,  # type: ignore[arg-type]
        matcher=None,  # type: ignore[arg-type]
    )
    rsp = service.list_projects({})
    assert rsp.success is True
    assert rsp.data == []


def test_project_service_delete_project(tmp_path: Path):
    workspace = WorkspacePaths(tmp_path / "workspace")
    workspace.ensure()
    db = Database(tmp_path / "workspace" / "isd.sqlite3")
    migrations = (
        Path(__file__).resolve().parents[1] / "src" / "isd" / "infrastructure" / "db" / "migrations"
    )
    db.init(migrations)
    conn = db.connect()
    project_repo = ProjectRepository(conn)

    service = ProjectService(
        workspace=workspace,
        project_repo=project_repo,
        station_repo=None,  # type: ignore[arg-type]
        file_repo=None,  # type: ignore[arg-type]
        scanner=None,  # type: ignore[arg-type]
        matcher=None,  # type: ignore[arg-type]
    )

    data_root = tmp_path / "sample_data"
    data_root.mkdir(parents=True, exist_ok=True)
    create_rsp = service.create_project(
        {"name": "to_delete", "description": "", "rootPath": str(data_root)}
    )
    assert create_rsp.success is True
    project_id = create_rsp.data["id"]
    assert workspace.project_dir(project_id).exists()

    delete_rsp = service.delete_project({"projectId": project_id})
    assert delete_rsp.success is True
    assert project_repo.get(project_id) is None
    assert not workspace.project_dir(project_id).exists()


def test_project_service_create_project_rejects_file_path(tmp_path: Path):
    service = _full_service(tmp_path)
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_text("x", encoding="utf-8")
    rsp = service.create_project({"name": "bad", "description": "", "rootPath": str(file_path)})
    assert rsp.success is False
    assert rsp.error is not None
    assert rsp.error.code == "INVALID_ROOT_PATH_TYPE"


def test_project_service_rescan_replaces_previous_records(tmp_path: Path):
    service = _full_service(tmp_path)
    data_root = tmp_path / "sample_data"
    data_root.mkdir(parents=True, exist_ok=True)
    obs_path = data_root / "abcd0840.24o"
    obs_path.write_text(
        (
            "     3.03           O                   RINEX VERSION / TYPE\n"
            "ABCD                                                MARKER NAME\n"
            "    30.0000                                          INTERVAL\n"
            "G    4 C1C L1C D1C S1C                               SYS / # / OBS TYPES\n"
            "                                                            END OF HEADER\n"
        ),
        encoding="utf-8",
    )
    create_rsp = service.create_project({"name": "scan_proj", "description": "", "rootPath": str(data_root)})
    assert create_rsp.success is True
    project_id = create_rsp.data["id"]

    scan1 = service.scan_project_files({"projectId": project_id, "metrics": ["SIGMA_PHI_F"]})
    assert scan1.success is True
    assert len(scan1.data["files"]) >= 1
    assert scan1.data["summary"]["fileCount"] >= 1

    obs_path.unlink()
    scan2 = service.scan_project_files({"projectId": project_id, "metrics": ["SIGMA_PHI_F"]})
    assert scan2.success is True
    assert scan2.data["summary"]["fileCount"] == 0
    assert scan2.data["summary"]["projectState"] == "EMPTY"
