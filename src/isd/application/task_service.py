from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import threading
from typing import Callable

from isd.application.ids import iter_dates, make_id, utc_now
from isd.application.risk_flags import derive_task_risk_flags
from isd.domain.enums import (
    ChainLevel,
    CoordinateSource,
    FileKind,
    GnssSystem,
    MetricKey,
    PppFallbackStrategy,
    PppStatus,
    SamplingMode,
    TaskStatus,
    TaskType,
    ValidationLevel,
)
from isd.domain.models import (
    ApiResponse,
    ErrorBody,
    ProcessingStep,
    SubTask,
    Task,
    TaskConfig,
    TaskLogEvent,
    TaskProgressEvent,
    ValidationIssue,
)
from isd.infrastructure.filesystem.paths import WorkspacePaths
from isd.infrastructure.repositories.project_file_repository import ProjectFileRepository
from isd.infrastructure.repositories.settings_repository import SettingsRepository
from isd.infrastructure.repositories.station_repository import StationRepository
from isd.infrastructure.repositories.task_repository import TaskRepository
from isd.infrastructure.repositories.validation_repository import ValidationIssueRepository
from isd.infrastructure.repositories.result_repository import ResultRepository
from isd.infrastructure.repositories.task_log_repository import TaskLogRepository
from isd.infrastructure.repositories.task_step_repository import TaskStepRepository
from isd.providers.interfaces import (
    AntennaCorrectionProvider,
    OrbitClockCorrectionProvider,
    OrbitClockProviderStatus,
    CoordinateProviderStatus,
    PreciseCoordinateProvider,
)
from isd.providers.stub_providers import (
    BasicAntennaCorrectionProvider,
    BasicOrbitClockCorrectionProvider,
    BasicPreciseCoordinateProvider,
)
from isd.workers.task_worker import TaskWorkerManager

DEFAULT_SYSTEM_SETTINGS = {
    "enableNonGpsSigmaPhiF": False,
    "enableExperimental1sResample": True,
    "enableNavDegradedMode": False,
    "rinexApproxSigmaPhiFPolicy": "WARNING",
}


@dataclass
class TaskService:
    workspace: WorkspacePaths
    task_repo: TaskRepository
    station_repo: StationRepository
    project_file_repo: ProjectFileRepository
    validation_repo: ValidationIssueRepository
    result_repo: ResultRepository
    task_log_repo: TaskLogRepository
    task_step_repo: TaskStepRepository
    worker: TaskWorkerManager
    settings_repo: SettingsRepository | None = None
    coordinate_provider: PreciseCoordinateProvider = field(default_factory=BasicPreciseCoordinateProvider)
    orbit_clock_provider: OrbitClockCorrectionProvider = field(default_factory=BasicOrbitClockCorrectionProvider)
    antenna_provider: AntennaCorrectionProvider = field(default_factory=BasicAntennaCorrectionProvider)
    progress_listeners: list[Callable[[TaskProgressEvent], None]] = field(default_factory=list)
    log_listeners: list[Callable[[TaskLogEvent], None]] = field(default_factory=list)
    logs: dict[str, list[TaskLogEvent]] = field(default_factory=dict)
    repo_lock: threading.Lock = field(default_factory=threading.Lock)

    def add_progress_listener(self, cb: Callable[[TaskProgressEvent], None]) -> None:
        self.progress_listeners.append(cb)

    def add_log_listener(self, cb: Callable[[TaskLogEvent], None]) -> None:
        self.log_listeners.append(cb)

    def validate_task(self, payload: dict) -> ApiResponse[dict]:
        config = TaskConfig.model_validate(payload["config"])
        issues: list[ValidationIssue] = []
        system_settings = self._load_system_settings()
        allow_non_gps_sigma = bool(system_settings.get("enableNonGpsSigmaPhiF", False))
        allow_experimental_1s = bool(system_settings.get("enableExperimental1sResample", False))
        allow_nav_degraded_mode = bool(system_settings.get("enableNavDegradedMode", False))
        rinex_policy = str(system_settings.get("rinexApproxSigmaPhiFPolicy", "WARNING")).upper().strip()
        with self.repo_lock:
            stations = self.station_repo.list_by_project(config.project_id)
            files = self.project_file_repo.list_by_project(config.project_id)
        kind_set = {f.kind for f in files}
        has_nav = FileKind.NAV in kind_set

        if not config.project_id.strip():
            issues.append(self._issue("PROJECT_ID_REQUIRED", "project_id is required", True))
        if not config.station_ids:
            issues.append(self._issue("STATION_IDS_REQUIRED", "At least one station is required", True))
        if not config.systems:
            issues.append(self._issue("SYSTEMS_REQUIRED", "At least one GNSS system is required", True))
        if not config.metrics:
            issues.append(self._issue("METRICS_REQUIRED", "At least one metric is required", True))

        station_map = {s.station_code.upper(): s for s in stations}
        selected_codes = [x.upper() for x in config.station_ids]
        selected_stations = [station_map[x] for x in selected_codes if x in station_map]
        missing_stations = sorted({x for x in selected_codes if x not in station_map})
        if missing_stations:
            issues.append(
                self._issue(
                    "STATION_NOT_FOUND",
                    "Some selected stations are missing in project metadata",
                    True,
                    detail=",".join(missing_stations),
                )
            )

        provider_summary = self._build_provider_summary(config, selected_stations, files)
        provider_chain_hint = provider_summary.get("providerChainHint")
        if selected_stations:
            if not provider_summary.get("allCoordinateFormalReady", False):
                issues.append(
                    self._issue(
                        "PROVIDER_COORDINATE_NOT_FORMAL",
                        "Coordinate provider indicates non-formal source for some stations",
                        False,
                        level=ValidationLevel.WARNING,
                    )
                )
            if not provider_summary.get("allAntennaFormalReady", False):
                issues.append(
                    self._issue(
                        "PROVIDER_ANTENNA_NOT_FORMAL",
                        "Antenna correction provider is non-formal for some stations",
                        False,
                        level=ValidationLevel.WARNING,
                    )
                )

        if MetricKey.DIXSG in config.metrics and len(set(selected_codes)) < 2:
            issues.append(self._issue("DIXSG_MULTI_STATION_REQUIRED", "DIXSG requires at least 2 stations", True))

        obs_station_dates = {
            (f.station_id.upper(), f.file_date)
            for f in files
            if f.kind == FileKind.OBS and f.station_id and f.file_date
        }
        missing_obs_pairs: list[str] = []
        for station_code in sorted(set(selected_codes)):
            for day in iter_dates(config.date_range.start, config.date_range.end):
                if (station_code, day) not in obs_station_dates:
                    missing_obs_pairs.append(f"{station_code}@{day}")
        if missing_obs_pairs:
            sample = ",".join(missing_obs_pairs[:8])
            issues.append(
                self._issue(
                    "OBS_DATA_MISSING_FOR_DATE",
                    "OBS data is missing for selected station/date pairs",
                    True,
                    detail=sample,
                )
            )

        if MetricKey.AATR in config.metrics:
            issues.append(
                self._issue(
                    "AATR_EVENT_DETECTION_DISABLED",
                    "AATR should not be used as standard event detection metric",
                    False,
                    level=ValidationLevel.WARNING,
                )
            )

        if MetricKey.IAATR in config.metrics:
            issues.append(
                self._issue(
                    "IAATR_WEAK_SUPPORT",
                    "IAATR is weak-support and for auxiliary analysis",
                    False,
                    level=ValidationLevel.WARNING,
                )
            )

        if config.enable_nav_fallback and not allow_nav_degraded_mode:
            issues.append(
                self._issue(
                    "NAV_FALLBACK_GLOBAL_DISABLED",
                    "NAV fallback requires global degraded-mode switch",
                    True,
                    recommendation="Enable `enableNavDegradedMode` in system settings first.",
                )
            )

        nav_fallback_applied = False
        non_gps_sigma = False
        if MetricKey.SIGMA_PHI_F in config.metrics:
            non_gps_sigma = any(sys != GnssSystem.GPS for sys in config.systems)
            if non_gps_sigma and not allow_non_gps_sigma:
                issues.append(
                    self._issue(
                        "SIGMAPHI_NON_GPS_GLOBAL_DISABLED",
                        "non-GPS sigma-phi-f is globally disabled in system settings",
                        True,
                        recommendation="Enable `enableNonGpsSigmaPhiF` in system settings first.",
                    )
                )
            if non_gps_sigma and not config.enable_experimental_sigma_phi_f:
                issues.append(
                    self._issue(
                        "SIGMAPHI_NON_GPS_EXPERIMENTAL_ONLY",
                        "non-GPS sigma-phi-f requires experimental mode",
                        True,
                    )
                )

            if config.sampling_mode == SamplingMode.EXPERIMENTAL_1S_RESAMPLED and not config.enable_1s_resample:
                issues.append(
                    self._issue(
                        "SAMPLING_1S_RESAMPLE_NOT_ENABLED",
                        "1s data requires experimental resample toggle",
                        True,
                    )
                )
            if config.sampling_mode == SamplingMode.EXPERIMENTAL_1S_RESAMPLED and not allow_experimental_1s:
                issues.append(
                    self._issue(
                        "SAMPLING_1S_GLOBAL_DISABLED",
                        "1s experimental resample is globally disabled in system settings",
                        True,
                        recommendation="Enable `enableExperimental1sResample` in system settings first.",
                    )
                )

            if not provider_summary.get("allAntennaAvailable", False):
                issues.append(
                    self._issue(
                        "SIGMAPHI_NO_ATX_SIMPLIFIED",
                        "ATX not provided; sigma-phi-f will use simplified mode (no geodetic detrending)",
                        False,
                        level=ValidationLevel.WARNING,
                    )
                )

            orbit_formal_ready = bool(provider_summary.get("allOrbitFormalReady", False))
            orbit_available = bool(provider_summary.get("allOrbitAvailable", False))
            sp3_missing = FileKind.SP3 not in kind_set
            clk_missing = FileKind.CLK not in kind_set
            if not orbit_formal_ready:
                if config.enable_nav_fallback and allow_nav_degraded_mode and orbit_available and has_nav:
                    nav_fallback_applied = True
                    issues.append(
                        self._issue(
                            "NAV_FALLBACK_DEGRADED_MODE",
                            "Orbit/clock provider is non-formal, task downgraded to NAV fallback mode",
                            False,
                            level=ValidationLevel.WARNING,
                        )
                    )
                elif not orbit_available and not has_nav:
                    # No orbit/clock/NAV at all: warn but allow simplified mode
                    if sp3_missing and clk_missing:
                        issues.append(
                            self._issue(
                                "SIGMAPHI_SIMPLIFIED_MODE",
                                "SP3/CLK not provided; sigma-phi-f will use simplified mode (no geodetic detrending)",
                                False,
                                level=ValidationLevel.WARNING,
                            )
                        )
                else:
                    if sp3_missing:
                        issues.append(
                            self._issue(
                                "SIGMAPHI_NO_SP3_WARNING",
                                "SP3 not provided; sigma-phi-f will use simplified mode",
                                False,
                                level=ValidationLevel.WARNING,
                            )
                        )
                    if clk_missing:
                        issues.append(
                            self._issue(
                                "SIGMAPHI_NO_CLK_WARNING",
                                "CLK not provided; sigma-phi-f will use simplified mode",
                                False,
                                level=ValidationLevel.WARNING,
                            )
                        )
                    if config.enable_nav_fallback and not has_nav:
                        issues.append(
                            self._issue(
                                "NAV_FALLBACK_NAV_MISSING",
                                "NAV fallback was enabled but NAV file is missing",
                                True,
                            )
                        )
                    if (not config.enable_nav_fallback) and has_nav:
                        issues.append(
                            self._issue(
                                "NAV_AVAILABLE_BUT_FALLBACK_DISABLED",
                                "NAV is available but degraded fallback mode is disabled",
                                False,
                                level=ValidationLevel.WARNING,
                            )
                        )

        out_path = Path(config.output_path)
        try:
            out_path.mkdir(parents=True, exist_ok=True)
            test_file = out_path / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            issues.append(self._issue("OUTPUT_DIR_NOT_WRITABLE", "Output directory not writable", True))

        if MetricKey.SIGMA_PHI_F in config.metrics:
            approx_codes = set(provider_summary.get("approxStations", []))
            approx_stations = [s for s in selected_stations if s.station_code.upper() in approx_codes]
            if approx_stations:
                if rinex_policy in {"BLOCK", "BLOCKING", "ERROR"}:
                    issues.append(
                        self._issue(
                            "RINEX_APPROX_SIGMAPHI_BLOCKED",
                            "RINEX approximate coordinates are blocked for sigma-phi-f by policy",
                            True,
                            recommendation="Use PPP/PRECISE coordinates or change policy to WARNING.",
                        )
                    )
                else:
                    issues.append(
                        self._issue(
                            "RINEX_APPROX_SIGMAPHI_WARNING",
                            "RINEX approximate coordinates degrade sigma-phi-f reliability",
                            False,
                            level=ValidationLevel.WARNING,
                        )
                    )
            ppp_not_ready = [s for s in selected_stations if s.ppp_status != PppStatus.SUCCESS]
            if ppp_not_ready:
                if (
                    config.algorithm_config.ppp_fallback_strategy
                    == PppFallbackStrategy.BLOCK_SIGMA_PHI_F
                ):
                    issues.append(
                        self._issue(
                            "PPP_NOT_READY_SIGMAPHI_BLOCKED",
                            "PPP not finished; sigma-phi-f blocked by strategy",
                            True,
                        )
                    )
                else:
                    issues.append(
                        self._issue(
                            "PPP_NOT_READY_SIGMAPHI_WARNING",
                            "PPP not finished; sigma-phi-f downgraded to warning mode",
                            False,
                            level=ValidationLevel.WARNING,
                        )
                    )

        can_run = all(not i.blocking for i in issues)
        derived_chain = config.chain_level
        if nav_fallback_applied:
            derived_chain = ChainLevel.DEGRADED
        elif (
            can_run
            and MetricKey.SIGMA_PHI_F in config.metrics
            and provider_chain_hint == ChainLevel.DEGRADED.value
            and derived_chain == ChainLevel.FORMAL
        ):
            derived_chain = ChainLevel.DEGRADED
            issues.append(
                self._issue(
                    "CHAIN_LEVEL_FORCED_DEGRADED_BY_PROVIDER",
                    "chain level is forced to DEGRADED by provider dependencies",
                    False,
                    level=ValidationLevel.WARNING,
                )
            )
        elif (
            can_run
            and
            MetricKey.SIGMA_PHI_F in config.metrics
            and provider_chain_hint == ChainLevel.EXPERIMENTAL.value
            and derived_chain == ChainLevel.FORMAL
        ):
            derived_chain = ChainLevel.EXPERIMENTAL
            issues.append(
                self._issue(
                    "CHAIN_LEVEL_FORCED_EXPERIMENTAL_BY_PROVIDER",
                    "chain level is forced to EXPERIMENTAL by provider dependencies",
                    False,
                    level=ValidationLevel.WARNING,
                )
            )
        elif (
            MetricKey.SIGMA_PHI_F in config.metrics
            and (
                (non_gps_sigma and config.enable_experimental_sigma_phi_f)
                or config.sampling_mode == SamplingMode.EXPERIMENTAL_1S_RESAMPLED
            )
            and derived_chain == ChainLevel.FORMAL
        ):
            derived_chain = ChainLevel.EXPERIMENTAL
            issues.append(
                self._issue(
                    "CHAIN_LEVEL_FORCED_EXPERIMENTAL",
                    "chain level is forced to EXPERIMENTAL by current sigma-phi-f settings",
                    False,
                    level=ValidationLevel.WARNING,
                )
            )
        derived_sampling = config.sampling_mode
        risk_flags = derive_task_risk_flags(
            derived_chain_level=derived_chain.value,
            derived_sampling_mode=derived_sampling.value,
            metrics=[m.value for m in config.metrics],
            systems=[s.value for s in config.systems],
            nav_fallback_enabled=nav_fallback_applied,
        )
        return ApiResponse(
            success=True,
            data={
                "canRun": can_run,
                "issues": [i.model_dump(mode="json") for i in issues],
                "derivedChainLevel": derived_chain.value,
                "derivedSamplingMode": derived_sampling.value,
                "riskFlags": risk_flags,
                "providerSummary": provider_summary,
            },
        )

    def create_task(self, payload: dict) -> ApiResponse[dict]:
        config = TaskConfig.model_validate(payload["config"])
        template_id = str(payload.get("templateId") or config.source_template_id or "").strip() or None
        if template_id and not config.source_template_id:
            config.source_template_id = template_id
        with self.repo_lock:
            stations = self.station_repo.list_by_project(config.project_id)
            files = self.project_file_repo.list_by_project(config.project_id)
        station_map = {s.station_code.upper(): s for s in stations}
        selected_stations = [station_map[x.upper()] for x in config.station_ids if x.upper() in station_map]
        config.provider_metadata = self._build_provider_summary(config, selected_stations, files)

        # Auto-set DIXSG grid range based on station coordinates,
        # but only if the user hasn't customized the range.
        # Default global range is (-90,90)/(-180,180) — only override that.
        _DEFAULT_LAT = (-90.0, 90.0)
        _DEFAULT_LON = (-180.0, 180.0)
        user_set_lat = config.algorithm_config.dixsg.lat_range != _DEFAULT_LAT
        user_set_lon = config.algorithm_config.dixsg.lon_range != _DEFAULT_LON

        # Skip stations with ECEF values (|lat| > 90 or |lon| > 180)
        sta_lats = [s.latitude for s in selected_stations
                     if s.latitude is not None and -90 <= s.latitude <= 90]
        sta_lons = [s.longitude for s in selected_stations
                     if s.longitude is not None and -180 <= s.longitude <= 180]
        if sta_lats and sta_lons:
            lat_min, lat_max = min(sta_lats), max(sta_lats)
            lon_min, lon_max = min(sta_lons), max(sta_lons)
            pad_lat = max((lat_max - lat_min) * 0.5, 5.0)
            pad_lon = max((lon_max - lon_min) * 0.5, 5.0)
            if not user_set_lat:
                config.algorithm_config.dixsg.lat_range = (
                    max(-90.0, lat_min - pad_lat),
                    min(90.0, lat_max + pad_lat),
                )
            if not user_set_lon:
                config.algorithm_config.dixsg.lon_range = (
                    max(-180.0, lon_min - pad_lon),
                    min(180.0, lon_max + pad_lon),
                )
        task_id = make_id("task")
        task = Task(
            id=task_id,
            project_id=config.project_id,
            name=payload["name"],
            status=TaskStatus.READY,
            task_type=TaskType(payload.get("taskType", "SINGLE")),
            chain_level=config.chain_level,
            sampling_mode=config.sampling_mode,
            config=config,
            created_at=utc_now(),
            created_from_template_id=template_id,
            snapshot_path=str(self.workspace.task_dir(config.project_id, task_id) / "snapshot.json"),
        )

        subtasks: list[SubTask] = []
        for sid in config.station_ids:
            for d in iter_dates(config.date_range.start, config.date_range.end):
                for sys in config.systems:
                    subtasks.append(
                        SubTask(
                            id=make_id("sub"),
                            task_id=task_id,
                            station_id=sid,
                            date=d,
                            system=sys,
                            metric_keys=config.metrics,
                            status=TaskStatus.READY,
                        )
                    )

        with self.repo_lock:
            self.task_repo.upsert_task(task)
            self.task_repo.replace_subtasks(task_id, subtasks)
        return ApiResponse(
            success=True,
            data={
                "task": task.model_dump(mode="json"),
                "subTasks": [s.model_dump(mode="json") for s in subtasks],
            },
        )

    def start_task(self, payload: dict) -> ApiResponse[dict]:
        with self.repo_lock:
            task = self.task_repo.get_task(payload["taskId"])
        if not task:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="TASK_NOT_FOUND", message="Task not found"),
            )
        if task.status == TaskStatus.RUNNING:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="TASK_ALREADY_RUNNING", message="Task is already running"),
            )
        with self.repo_lock:
            subtasks = self.task_repo.list_subtasks(task.id)
        task.status = TaskStatus.RUNNING
        task.started_at = utc_now()
        task.finished_at = None
        task.latest_error = None
        with self.repo_lock:
            self.task_repo.update_subtasks_for_task(task.id, TaskStatus.READY)
            self.task_repo.upsert_task(task)
        log_file_path = str(self.workspace.task_dir(task.project_id, task.id) / "logs" / "runtime.log.jsonl")

        def on_progress(evt: TaskProgressEvent) -> None:
            with self.repo_lock:
                existing = self.task_repo.get_task(task.id)
                if not existing or existing.status == TaskStatus.CANCELLED:
                    return
                if evt.sub_task_id:
                    db_status = evt.status
                    if evt.current_step_key == 'subtask_completed':
                        db_status = TaskStatus.COMPLETED
                    self.task_repo.update_subtask_status(
                        evt.sub_task_id,
                        db_status,
                        current_step_key=evt.current_step_key,
                    )
            for cb in self.progress_listeners:
                cb(evt)

        def on_log(evt: TaskLogEvent) -> None:
            self.logs.setdefault(task.id, []).append(evt)
            with self.repo_lock:
                existing = self.task_repo.get_task(task.id)
                if existing and existing.status != TaskStatus.CANCELLED:
                    self.task_log_repo.append(evt, log_file_path=log_file_path)
            for cb in self.log_listeners:
                cb(evt)

        def on_step(task_id: str, sub_task_id: str | None, step: ProcessingStep) -> None:
            with self.repo_lock:
                existing = self.task_repo.get_task(task_id)
                if existing and existing.status != TaskStatus.CANCELLED:
                    self.task_step_repo.upsert(task_id, sub_task_id, step)

        def on_done(done_task: Task, results) -> None:
            with self.repo_lock:
                existing = self.task_repo.get_task(task.id)
                if not existing or existing.status == TaskStatus.CANCELLED:
                    return
                done_task.summary = f"results={len(results)}"
                self.task_repo.upsert_task(done_task)
                self.task_repo.replace_subtasks(task.id, subtasks)
                self.result_repo.insert_many(results)

        self.worker.start(
            task,
            subtasks,
            on_progress=on_progress,
            on_log=on_log,
            on_done=on_done,
            on_step=on_step,
        )
        return ApiResponse(success=True, data={"taskId": task.id, "status": TaskStatus.RUNNING.value})

    def pause_task(self, payload: dict) -> ApiResponse[dict]:
        ok = self.worker.pause(payload["taskId"])
        if ok:
            with self.repo_lock:
                task = self.task_repo.get_task(payload["taskId"])
            if task:
                task.status = TaskStatus.PAUSED
                with self.repo_lock:
                    self.task_repo.upsert_task(task)
        return ApiResponse(success=ok, data={"taskId": payload["taskId"], "paused": ok})

    def resume_task(self, payload: dict) -> ApiResponse[dict]:
        ok = self.worker.resume(payload["taskId"])
        if ok:
            with self.repo_lock:
                task = self.task_repo.get_task(payload["taskId"])
            if task:
                task.status = TaskStatus.RUNNING
                with self.repo_lock:
                    self.task_repo.upsert_task(task)
        return ApiResponse(success=ok, data={"taskId": payload["taskId"], "resumed": ok})

    def stop_task(self, payload: dict) -> ApiResponse[dict]:
        ok = self.worker.stop(payload["taskId"])
        if ok:
            with self.repo_lock:
                task = self.task_repo.get_task(payload["taskId"])
            if task:
                task.status = TaskStatus.STOPPING
                with self.repo_lock:
                    self.task_repo.upsert_task(task)
        return ApiResponse(success=ok, data={"taskId": payload["taskId"], "stopped": ok})

    def retry_task(self, payload: dict) -> ApiResponse[dict]:
        with self.repo_lock:
            task = self.task_repo.get_task(payload["taskId"])
        if not task:
            return ApiResponse(success=False, error=ErrorBody(code="TASK_NOT_FOUND", message="Task not found"))
        task_dir = self.workspace.task_dir(task.project_id, task.id)
        if task_dir.exists():
            shutil.rmtree(task_dir)
        with self.repo_lock:
            self.result_repo.delete_by_task(task.id)
            self.task_log_repo.delete_by_task(task.id)
            self.task_step_repo.delete_by_task(task.id)
        self.logs.pop(task.id, None)
        with self.repo_lock:
            self.task_repo.update_subtasks_for_task(task.id, TaskStatus.READY)
        task.status = TaskStatus.READY
        task.latest_error = None
        task.summary = None
        task.finished_at = None
        with self.repo_lock:
            self.task_repo.upsert_task(task)
        return self.start_task({"taskId": task.id})

    def delete_task(self, payload: dict) -> ApiResponse[dict]:
        task_id = payload.get("taskId")
        force = payload.get("force", False)
        if not task_id:
            return ApiResponse(success=False, error=ErrorBody(code="TASK_NOT_FOUND", message="taskId is required"))

        with self.repo_lock:
            task = self.task_repo.get_task(task_id)
        if not task:
            return ApiResponse(success=False, error=ErrorBody(code="TASK_NOT_FOUND", message="Task not found"))

        # 如果正在运行或强制删除，先停止worker
        if task.status == TaskStatus.RUNNING or force:
            self.worker.stop(task_id)
            import time
            # Wait for worker thread to finish without holding repo_lock
            for _ in range(50):
                if task_id not in self.worker._runtimes:
                    break
                runtime = self.worker._runtimes.get(task_id)
                if runtime and runtime.thread:
                    runtime.thread.join(timeout=0.2)
                else:
                    break
            # Ensure removal from runtimes
            self.worker._runtimes.pop(task_id, None)

        task_dir = self.workspace.task_dir(task.project_id, task.id)
        try:
            if task_dir.exists():
                shutil.rmtree(task_dir)
        except Exception:
            pass

        with self.repo_lock:
            # Mark task as cancelled first to prevent worker callbacks from writing
            task = self.task_repo.get_task(task_id)
            if task:
                task.status = TaskStatus.CANCELLED
                self.task_repo.upsert_task(task)
            # task_repo.delete_task handles all related table deletes in FK order
            self.task_repo.delete_task(task_id)
        self.logs.pop(task_id, None)

        # Clean up empty project directory structure left behind
        self._cleanup_empty_project_dirs(task.project_id)

        return ApiResponse(success=True, data={"taskId": task_id})

    def list_tasks(self, payload: dict) -> ApiResponse[list[dict]]:
        with self.repo_lock:
            rows = self.task_repo.list_tasks(payload.get("projectId"))
        return ApiResponse(success=True, data=[x.model_dump(mode="json") for x in rows])

    def get_task(self, payload: dict) -> ApiResponse[dict]:
        with self.repo_lock:
            task = self.task_repo.get_task(payload["taskId"])
        if not task:
            return ApiResponse(success=False, error=ErrorBody(code="TASK_NOT_FOUND", message="Task not found"))
        with self.repo_lock:
            subtasks = self.task_repo.list_subtasks(task.id)
        return ApiResponse(
            success=True,
            data={
                "task": task.model_dump(mode="json"),
                "subTasks": [s.model_dump(mode="json") for s in subtasks],
            },
        )

    def get_logs(self, payload: dict) -> ApiResponse[list[dict]]:
        with self.repo_lock:
            events = self.task_log_repo.list_by_task(payload["taskId"])
        if not events:
            events = self.logs.get(payload["taskId"], [])
        return ApiResponse(success=True, data=[e.model_dump(mode="json") for e in events])

    def _load_system_settings(self) -> dict:
        settings = dict(DEFAULT_SYSTEM_SETTINGS)
        if not self.settings_repo:
            return settings
        loaded = self.settings_repo.get("system", default=None)
        if isinstance(loaded, dict):
            settings.update(loaded)
        return settings

    def _build_provider_summary(self, config: TaskConfig, selected_stations: list, files: list) -> dict:
        dates = list(iter_dates(config.date_range.start, config.date_range.end))
        station_providers: dict[str, dict] = {}
        date_providers: dict[str, dict] = {}
        approx_stations: list[str] = []

        all_coordinate_available = True if selected_stations else False
        all_coordinate_formal = True if selected_stations else False
        all_antenna_available = True if selected_stations else False
        all_antenna_formal = True if selected_stations else False

        for station in selected_stations:
            coord_statuses: list[CoordinateProviderStatus] = [
                self.coordinate_provider.resolve(station, day, files) for day in dates
            ]
            coord_available = all(s.available for s in coord_statuses) if coord_statuses else False
            coord_formal = all(s.formal_ready for s in coord_statuses) if coord_statuses else False
            coordinate_source = self._pick_coordinate_source(coord_statuses)
            if coordinate_source == CoordinateSource.RINEX_APPROX.value:
                approx_stations.append(station.station_code.upper())

            antenna_status = self.antenna_provider.resolve(station, files)
            antenna_available = bool(antenna_status.available)
            antenna_formal = bool(antenna_status.formal_ready)

            station_providers[station.station_code.upper()] = {
                "coordinateSource": coordinate_source,
                "coordinateAvailable": coord_available,
                "coordinateFormalReady": coord_formal,
                "coordinateProvider": self.coordinate_provider.__class__.__name__,
                "coordinateDetail": ";".join(s.detail for s in coord_statuses if s.detail),
                "antennaSource": antenna_status.source,
                "antennaAvailable": antenna_available,
                "antennaFormalReady": antenna_formal,
                "antennaProvider": antenna_status.provider,
                "antennaDetail": antenna_status.detail,
            }

            all_coordinate_available = all_coordinate_available and coord_available
            all_coordinate_formal = all_coordinate_formal and coord_formal
            all_antenna_available = all_antenna_available and antenna_available
            all_antenna_formal = all_antenna_formal and antenna_formal

        all_orbit_available = True if dates else False
        all_orbit_formal = True if dates else False
        for day in dates:
            orbit_status: OrbitClockProviderStatus = self.orbit_clock_provider.resolve(day, files)
            date_providers[day] = {
                "orbitClockSource": orbit_status.source,
                "orbitClockAvailable": orbit_status.available,
                "orbitClockFormalReady": orbit_status.formal_ready,
                "orbitClockProvider": orbit_status.provider,
                "orbitClockDetail": orbit_status.detail,
            }
            all_orbit_available = all_orbit_available and bool(orbit_status.available)
            all_orbit_formal = all_orbit_formal and bool(orbit_status.formal_ready)

        provider_chain_hint = self._derive_provider_chain_hint(
            has_stations=bool(selected_stations),
            has_dates=bool(dates),
            all_coordinate_available=all_coordinate_available,
            all_coordinate_formal=all_coordinate_formal,
            all_orbit_available=all_orbit_available,
            all_orbit_formal=all_orbit_formal,
            all_antenna_available=all_antenna_available,
            all_antenna_formal=all_antenna_formal,
        )

        summary_text = (
            f"coordProvider={self.coordinate_provider.__class__.__name__},"
            f"orbitClockProvider={self.orbit_clock_provider.__class__.__name__},"
            f"antennaProvider={self.antenna_provider.__class__.__name__},"
            f"chainHint={provider_chain_hint}"
        )

        # Build file path index so workers can locate actual RINEX files
        file_paths = [str(f.file_path) for f in files if f.file_path]
        obs_by_station: dict[str, str] = {}
        for f in files:
            if f.kind == FileKind.OBS and f.station_id and f.file_path:
                obs_by_station[f.station_id.upper()] = str(f.file_path)

        for sid, meta in station_providers.items():
            if sid in obs_by_station:
                meta["obsPath"] = obs_by_station[sid]

        # Build SP3 path index by date (with prev+next day for interpolation edges)
        sp3_by_date: dict[str, str] = {}
        for f in files:
            if f.kind == FileKind.SP3 and f.file_date and f.file_path:
                sp3_by_date[f.file_date] = str(f.file_path)
        all_sp3_dates = sorted(sp3_by_date.keys())
        for day in dates:
            prev_path = None
            curr_path = sp3_by_date.get(day)
            next_path = None
            for d in all_sp3_dates:
                if d < day:
                    prev_path = sp3_by_date[d]
                elif d > day and next_path is None:
                    next_path = sp3_by_date[d]
                    break
            sp3_paths = [p for p in [prev_path, curr_path, next_path] if p]
            date_providers[day]["sp3Paths"] = sp3_paths

        # Build CLK path index by date
        clk_by_date: dict[str, str] = {}
        for f in files:
            if f.kind == FileKind.CLK and f.file_date and f.file_path:
                clk_by_date[f.file_date] = str(f.file_path)
        for day in dates:
            clk_path = clk_by_date.get(day)
            if clk_path:
                date_providers[day]["clkPaths"] = [clk_path]

        # Build ATX path (global, not date-specific)
        atx_files = [
            str(f.file_path) for f in files
            if f.kind == FileKind.ATX and f.file_path and Path(f.file_path).exists()
        ]
        if atx_files:
            for day in dates:
                date_providers[day]["atxPath"] = atx_files[0]

        return {
            "stationProviders": station_providers,
            "dateProviders": date_providers,
            "filePaths": file_paths,
            "allCoordinateAvailable": all_coordinate_available,
            "allCoordinateFormalReady": all_coordinate_formal,
            "allOrbitAvailable": all_orbit_available,
            "allOrbitFormalReady": all_orbit_formal,
            "allAntennaAvailable": all_antenna_available,
            "allAntennaFormalReady": all_antenna_formal,
            "approxStations": sorted(set(approx_stations)),
            "providerChainHint": provider_chain_hint,
            "providerSummaryText": summary_text,
        }

    def _pick_coordinate_source(self, statuses: list[CoordinateProviderStatus]) -> str:
        values = {s.coordinate_source.value for s in statuses}
        if CoordinateSource.PRECISE_FILE.value in values:
            return CoordinateSource.PRECISE_FILE.value
        if CoordinateSource.PPP.value in values:
            return CoordinateSource.PPP.value
        return CoordinateSource.RINEX_APPROX.value

    def _derive_provider_chain_hint(
        self,
        *,
        has_stations: bool,
        has_dates: bool,
        all_coordinate_available: bool,
        all_coordinate_formal: bool,
        all_orbit_available: bool,
        all_orbit_formal: bool,
        all_antenna_available: bool,
        all_antenna_formal: bool,
    ) -> str:
        if not has_stations or not has_dates:
            return ChainLevel.EXPERIMENTAL.value
        if all_coordinate_formal and all_orbit_formal and all_antenna_formal:
            return ChainLevel.FORMAL.value
        if all_coordinate_available and all_orbit_available and all_antenna_available:
            return ChainLevel.DEGRADED.value
        return ChainLevel.EXPERIMENTAL.value

    def _issue(
        self,
        code: str,
        message: str,
        blocking: bool,
        *,
        level: ValidationLevel = ValidationLevel.BLOCKING,
        detail: str | None = None,
        recommendation: str | None = None,
    ) -> ValidationIssue:
        return ValidationIssue(
            id=make_id("issue"),
            level=level,
            code=code,
            message=message,
            detail=detail,
            blocking=blocking,
            recommendation=recommendation,
        )

    def _cleanup_empty_project_dirs(self, project_id: str) -> None:
        """Remove empty project directory tree after task deletion."""
        project_dir = self.workspace.project_dir(project_id)
        try:
            if project_dir.exists() and not any(p.is_file() for p in project_dir.rglob("*")):
                shutil.rmtree(project_dir, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass
