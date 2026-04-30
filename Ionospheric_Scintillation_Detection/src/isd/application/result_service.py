from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from isd.domain.models import ApiResponse, ErrorBody
from isd.infrastructure.filesystem.result_store import ResultStore
from isd.infrastructure.repositories.result_repository import ResultRepository


@dataclass
class ResultService:
    repo: ResultRepository
    store: ResultStore
    workspace_root: Path = field(default_factory=lambda: Path("workspace"))

    def _resolve_data_path(self, data_path: str) -> Path:
        """Resolve a data_path to an absolute path, trying workspace root if relative."""
        p = Path(data_path)
        if p.is_absolute() and p.exists():
            return p
        if p.exists():
            return p
        # Try relative to workspace root
        workspace_candidate = self.workspace_root / p
        if workspace_candidate.exists():
            return workspace_candidate
        # Try workspace_root parent in case the path already includes 'workspace'
        parent_candidate = self.workspace_root.parent / p
        if parent_candidate.exists():
            return parent_candidate
        # Return original path as last resort (will fail with clear error)
        return p

    def list_results(self, payload: dict) -> ApiResponse[list[dict]]:
        rows = self.repo.list_results(payload["projectId"], payload.get("taskId"))
        return ApiResponse(success=True, data=[r.model_dump(mode="json") for r in rows])

    def get_series(self, payload: dict) -> ApiResponse[dict]:
        project_id = payload.get("projectId")
        if not project_id:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="MISSING_PROJECT_ID", message="projectId is required"),
            )

        result_id = payload.get("resultId")
        if not result_id:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="MISSING_RESULT_ID", message="resultId is required"),
            )

        result = self._get_result(result_id, project_id)
        if not result:
            return ApiResponse(success=False, error=ErrorBody(code="RESULT_NOT_FOUND", message="Result not found"))

        resolved_path = self._resolve_data_path(result["data_path"])
        if not resolved_path.exists():
            return ApiResponse(
                success=False,
                error=ErrorBody(code="DATA_FILE_NOT_FOUND", message=f"Data file not found: {result['data_path']}"),
            )

        try:
            data = self.store.load(str(resolved_path))
        except Exception as exc:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="DATA_LOAD_FAILED", message=f"Failed to load data: {exc}"),
            )

        if "values" not in data:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="SERIES_NOT_AVAILABLE", message="Current result does not contain series values"),
            )

        values = np.asarray(data["values"], dtype=float)
        if values.ndim == 0:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="SERIES_FORMAT_INVALID", message="Series values shape is invalid"),
            )

        time_axis = np.asarray(data.get("time", np.arange(values.shape[0], dtype=float)), dtype=float)
        if time_axis.shape[0] != values.shape[0]:
            time_axis = np.arange(values.shape[0], dtype=float)

        out = {k: np.asarray(v).tolist() for k, v in data.items()}
        out["time"] = time_axis.tolist()
        out["values"] = values.tolist()
        out["seriesLength"] = int(values.shape[0])
        return ApiResponse(success=True, data=out)

    def get_grid(self, payload: dict) -> ApiResponse[dict]:
        project_id = payload.get("projectId")
        if not project_id:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="MISSING_PROJECT_ID", message="projectId is required"),
            )

        result_id = payload.get("resultId")
        if not result_id:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="MISSING_RESULT_ID", message="resultId is required"),
            )

        result = self._get_result(result_id, project_id)
        if not result:
            return ApiResponse(success=False, error=ErrorBody(code="RESULT_NOT_FOUND", message="Result not found"))

        resolved_path = self._resolve_data_path(result["data_path"])
        if not resolved_path.exists():
            return ApiResponse(
                success=False,
                error=ErrorBody(code="DATA_FILE_NOT_FOUND", message=f"Data file not found: {result['data_path']}"),
            )

        try:
            data = self.store.load(str(resolved_path))
        except Exception as exc:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="DATA_LOAD_FAILED", message=f"Failed to load data: {exc}"),
            )

        if "grid" not in data:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="GRID_NOT_AVAILABLE", message="Current result does not contain grid values"),
            )

        grid = np.asarray(data["grid"], dtype=float)
        if grid.ndim == 0:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="GRID_FORMAT_INVALID", message="Grid shape is invalid"),
            )

        total = int(grid.size)
        valid = int(np.isfinite(grid).sum())
        coverage = float(valid / total) if total > 0 else 0.0
        response_data = {
            "grid": grid.tolist(),
            "shape": list(grid.shape),
            "validCount": valid,
            "totalCount": total,
            "coverage": coverage,
        }
        # Pass through coordinate metadata if present
        for key in ("lat_range", "lon_range"):
            val = data.get(key)
            if val is not None:
                response_data[key] = val
        return ApiResponse(success=True, data=response_data)

    def get_intermediate(self, payload: dict) -> ApiResponse[dict]:
        task_id = payload["taskId"]
        project_id = payload.get("projectId")
        sub_id = payload.get("subTaskId")
        step_key = payload.get("stepKey", "ROTI")

        bases: list[Path] = []
        if project_id:
            bases.append(Path("workspace") / "projects" / project_id / "tasks" / task_id / "intermediate")
        else:
            projects_root = Path("workspace") / "projects"
            if projects_root.exists():
                for project_root in projects_root.iterdir():
                    if project_root.is_dir():
                        bases.append(project_root / "tasks" / task_id / "intermediate")

        patterns: list[str] = []
        if sub_id and step_key:
            patterns.extend(
                [
                    f"{sub_id}_{step_key}.json",
                    f"{sub_id}_{step_key}.csv",
                    f"{sub_id}_{step_key}.png",
                    f"{sub_id}_{step_key}.npz",
                ]
            )
        if sub_id:
            patterns.extend([f"{sub_id}_*.json", f"{sub_id}_*.csv", f"{sub_id}_*.png", f"{sub_id}_*.npz"])
        if not patterns:
            patterns.extend(["*.json", "*.csv", "*.png", "*.npz"])

        candidates: list[Path] = []
        for base in bases:
            if not base.exists():
                continue
            for pattern in patterns:
                candidates.extend(base.rglob(pattern))

        unique = {c.resolve(): c for c in candidates}
        ordered = sorted(unique.values(), key=lambda p: p.name)

        if not ordered:
            return ApiResponse(
                success=True,
                data={
                    "step": step_key,
                    "files": [],
                    "note": "No intermediate artifacts found for current selection.",
                },
            )

        return ApiResponse(
            success=True,
            data={
                "step": step_key,
                "files": [self._file_meta(p) for p in ordered],
            },
        )

    def export_result(self, payload: dict) -> ApiResponse[dict]:
        output_path = payload.get("outputPath")
        if not output_path:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="MISSING_OUTPUT_PATH", message="outputPath is required"),
            )

        data_path = payload.get("dataPath")
        if not data_path:
            result_id = payload.get("resultId")
            project_id = payload.get("projectId")
            if not result_id or not project_id:
                return ApiResponse(
                    success=False,
                    error=ErrorBody(
                        code="MISSING_RESULT_REFERENCE",
                        message="Either dataPath or (resultId + projectId) is required",
                    ),
                )
            result = self._get_result(result_id, project_id)
            if not result:
                return ApiResponse(
                    success=False,
                    error=ErrorBody(code="RESULT_NOT_FOUND", message="Result not found"),
                )
            data_path = result["data_path"]

        resolved = self._resolve_data_path(data_path)
        if not resolved.exists():
            return ApiResponse(
                success=False,
                error=ErrorBody(code="DATA_FILE_NOT_FOUND", message=f"Data file not found: {data_path}"),
            )

        try:
            exported_path = self.store.export(str(resolved), output_path)
        except Exception as exc:  # noqa: BLE001
            return ApiResponse(
                success=False,
                error=ErrorBody(code="EXPORT_FAILED", message=str(exc)),
            )
        return ApiResponse(success=True, data={"outputPath": exported_path})

    def _get_result(self, result_id: str, project_id: str):
        rows = self.repo.list_results(project_id)
        for r in rows:
            if r.id == result_id:
                return r.model_dump(mode="json")
        return None

    def _file_meta(self, path: Path) -> dict[str, Any]:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            file_type = "CSV"
        elif suffix == ".png":
            file_type = "PNG"
        elif suffix == ".npz":
            file_type = "NPZ"
        else:
            file_type = "JSON"
        return {"filePath": str(path), "fileType": file_type, "label": path.name}
