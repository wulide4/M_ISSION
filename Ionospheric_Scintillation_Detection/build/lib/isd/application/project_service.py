from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from isd.application.ids import make_id, utc_now
from isd.domain.enums import ProjectStatus
from isd.domain.models import ApiResponse, ErrorBody, Project
from isd.infrastructure.filesystem.file_scan import FileScanner
from isd.infrastructure.filesystem.paths import WorkspacePaths
from isd.infrastructure.filesystem.product_match import ProductMatcher
from isd.infrastructure.repositories.project_file_repository import ProjectFileRepository
from isd.infrastructure.repositories.project_repository import ProjectRepository
from isd.infrastructure.repositories.station_repository import StationRepository


@dataclass
class ProjectService:
    workspace: WorkspacePaths
    project_repo: ProjectRepository
    station_repo: StationRepository
    file_repo: ProjectFileRepository
    scanner: FileScanner
    matcher: ProductMatcher

    def create_project(self, payload: dict) -> ApiResponse[Project]:
        root_path = Path(payload["rootPath"]).resolve()
        if not root_path.exists():
            return ApiResponse(
                success=False,
                error=ErrorBody(code="INVALID_ROOT_PATH", message=f"Path does not exist: {root_path}"),
            )
        if not root_path.is_dir():
            return ApiResponse(
                success=False,
                error=ErrorBody(code="INVALID_ROOT_PATH_TYPE", message=f"Path is not a directory: {root_path}"),
            )
        try:
            next(root_path.iterdir(), None)
        except PermissionError:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="ROOT_PATH_NOT_READABLE", message=f"Path is not readable: {root_path}"),
            )

        project_id = make_id("proj")
        created = utc_now()
        project = Project(
            id=project_id,
            name=payload["name"],
            description=payload.get("description"),
            root_path=str(root_path),
            created_at=created,
            updated_at=created,
            default_output_path=str((self.workspace.project_dir(project_id) / "reports").resolve()),
            tags=[],
            status=ProjectStatus.ACTIVE,
        )
        self.project_repo.upsert(project)

        pdir = self.workspace.project_dir(project_id)
        for d in [
            "raw/obs",
            "raw/sp3",
            "raw/clk",
            "raw/atx",
            "raw/nav",
            "raw/space_weather",
            "derived/metadata",
            "derived/ppp",
            "derived/validation",
            "tasks",
            "reports",
        ]:
            (pdir / d).mkdir(parents=True, exist_ok=True)
        (pdir / "project.json").write_text(
            json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return ApiResponse(success=True, data=project.model_dump(mode="json"))

    def list_projects(self, payload: dict | None = None) -> ApiResponse[list[Project]]:
        _ = payload
        rows: list[dict] = []
        for project in self.project_repo.list_all():
            row = project.model_dump(mode="json")
            row["rootPathExists"] = Path(project.root_path).exists()
            row["workspacePathExists"] = self.workspace.project_dir(project.id).exists()
            rows.append(row)
        return ApiResponse(success=True, data=rows)

    def open_project(self, payload: dict) -> ApiResponse[Project]:
        project = self.project_repo.get(payload["projectId"])
        if not project:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="PROJECT_NOT_FOUND", message="Project not found"),
            )
        return ApiResponse(success=True, data=project.model_dump(mode="json"))

    def delete_project(self, payload: dict) -> ApiResponse[dict]:
        project_id = payload.get("projectId")
        if not project_id:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="INVALID_PROJECT_ID", message="projectId is required"),
            )
        project = self.project_repo.get(project_id)
        if not project:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="PROJECT_NOT_FOUND", message="Project not found"),
            )

        self.project_repo.delete(project_id)

        project_dir = self.workspace.project_dir(project_id)
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)

        return ApiResponse(success=True, data={"projectId": project_id, "deleted": True})

    def scan_project_files(self, payload: dict) -> ApiResponse[dict]:
        project_id = payload["projectId"]
        metrics = payload.get("metrics", [])
        if payload.get("paths"):
            paths = payload["paths"]
        else:
            project = self.project_repo.get(project_id)
            if not project:
                return ApiResponse(
                    success=False,
                    error=ErrorBody(code="PROJECT_NOT_FOUND", message="Project not found"),
                )
            paths = [project.root_path]
        files, stations, issues = self.scanner.scan_project(project_id, paths)
        self.matcher.assign_match_flags(files)
        dependency_summary = self.matcher.resolve(files, metrics)
        self.file_repo.replace_for_project(project_id, files)
        self.station_repo.replace_for_project(project_id, stations)
        summary = self._build_scan_summary(files, stations, issues, dependency_summary)
        return ApiResponse(
            success=True,
            data={
                "files": [f.model_dump(mode="json") for f in files],
                "stations": [s.model_dump(mode="json") for s in stations],
                "issues": [i.model_dump(mode="json") for i in issues],
                "dependencySummary": dependency_summary,
                "summary": summary,
            },
        )

    def get_stations(self, payload: dict) -> ApiResponse[list[dict]]:
        stations = self.station_repo.list_by_project(payload["projectId"])
        return ApiResponse(success=True, data=[s.model_dump(mode="json") for s in stations])

    def resolve_product_matching(self, payload: dict) -> ApiResponse[dict]:
        files = self.file_repo.list_by_project(payload["projectId"])
        metrics = payload.get("metrics", [])
        result = self.matcher.resolve(files, metrics)
        return ApiResponse(success=True, data=result)

    def _build_scan_summary(
        self,
        files: list,
        stations: list,
        issues: list,
        dependency_summary: dict,
    ) -> dict:
        valid_files = sum(1 for f in files if str(f.validation_status.value) == "VALID")
        warning_files = sum(1 for f in files if str(f.validation_status.value) == "WARNING")
        invalid_files = sum(1 for f in files if str(f.validation_status.value) == "INVALID")
        matched_files = sum(1 for f in files if bool(f.matched))
        ready_days = sum(1 for row in dependency_summary.values() if str(row.get("status")) == "ready")

        state = "EMPTY"
        if files:
            state = "VALIDATED" if (invalid_files == 0 and len(issues) == 0) else "PARTIAL_WARNING"
            if invalid_files > 0:
                state = "PARTIAL_WARNING"
        return {
            "projectState": state,
            "fileCount": len(files),
            "stationCount": len(stations),
            "matchedFileCount": matched_files,
            "validFileCount": valid_files,
            "warningFileCount": warning_files,
            "invalidFileCount": invalid_files,
            "scanIssueCount": len(issues),
            "readyDateCount": ready_days,
            "dependencyDateCount": len(dependency_summary),
        }
