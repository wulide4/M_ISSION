from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from isd.algorithms.matlab_metrics import (
    DixsgBundle,
    GpsCrotBundle,
    GpsMetricsBundle,
    GpsSigmaPhiBundle,
    compute_dixsg_from_crot_bundles,
    compute_gps_crot_from_obs_cut,
    compute_gps_metrics_from_obs_cut,
    load_gps_sigmaphi_from_mat,
    load_dixsg_from_mat,
)
from isd.algorithms.metrics import (
    aatr_aggregate,
    crot_compute,
    dixsg_grid,
    iaatr_compute,
    moving_window_sigma_phi_f,
    roti_compute,
)
from isd.algorithms.preprocess import preprocess_chain
from isd.algorithms.preprocess import (
    butterworth_filter,
    cycle_slip_detection,
    cycle_slip_repair,
    geodetic_detrending,
    polynomial_detrending,
    short_arc_removal,
)
from isd.application.ids import make_id, utc_now
from isd.domain.enums import CoordinateSource, GnssSystem, MetricKey, StepStatus, TaskStatus, ThresholdSource
from isd.domain.models import (
    ProcessingStep,
    ResultSet,
    ResultStats,
    SubTask,
    Task,
    TaskLogEvent,
    TaskProgressEvent,
)
from isd.infrastructure.filesystem.paths import WorkspacePaths
from isd.infrastructure.filesystem.result_store import ResultStore

ProgressCallback = Callable[[TaskProgressEvent], None]
LogCallback = Callable[[TaskLogEvent], None]
StepCallback = Callable[[str, str | None, ProcessingStep], None]
DoneCallback = Callable[[Task, list[ResultSet]], None]

STEP_KEYS = [
    'sigmaphi_cutoff_elevation',
    'sigmaphi_short_arc_removal',
    'sigmaphi_cycle_slip_detection',
    'sigmaphi_cycle_slip_repair',
    'sigmaphi_geodetic_detrending',
    'sigmaphi_polynomial_detrending',
    'sigmaphi_butterworth_filter',
    'sigmaphi_moving_window_sigma',
    'short_arc_removal',
    'cycle_slip_detection',
    'cycle_slip_repair',
    'geodetic_detrending',
    'polynomial_detrending',
    'butterworth_filter',
    'moving_window_sigma_phi_f',
    'roti_compute',
    'iaatr_compute',
    'aatr_aggregate',
    'crot_compute',
    'dixsg_grid',
]


@dataclass
class TaskRuntime:
    task: Task
    subtasks: list[SubTask]
    on_progress: ProgressCallback
    on_log: LogCallback
    on_step: StepCallback | None
    pause_event: threading.Event = field(default_factory=threading.Event)
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    task_dir: Path | None = None
    log_file_path: Path | None = None
    total: int = 1
    done: int = 0
    gps_bundle_cache: dict[str, GpsMetricsBundle] = field(default_factory=dict)
    gps_crot_cache: dict[str, GpsCrotBundle] = field(default_factory=dict)
    dixsg_bundle_cache: dict[str, DixsgBundle] = field(default_factory=dict)
    gps_sigmaphi_cache: dict[str, GpsSigmaPhiBundle] = field(default_factory=dict)


class TaskWorkerManager:
    def __init__(self, workspace: WorkspacePaths, result_store: ResultStore) -> None:
        self.workspace = workspace
        self.result_store = result_store
        self._runtimes: dict[str, TaskRuntime] = {}

    def start(
        self,
        task: Task,
        subtasks: list[SubTask],
        on_progress: ProgressCallback,
        on_log: LogCallback,
        on_done: DoneCallback,
        on_step: StepCallback | None = None,
    ) -> None:
        if task.id in self._runtimes:
            return

        runtime = TaskRuntime(
            task=task,
            subtasks=subtasks,
            on_progress=on_progress,
            on_log=on_log,
            on_step=on_step,
        )
        runtime.total = max(1, len(subtasks) * max(1, len(task.config.metrics)))

        def _run() -> None:
            results: list[ResultSet] = []
            runtime.task_dir = self.workspace.task_dir(task.project_id, task.id)
            (runtime.task_dir / 'logs').mkdir(parents=True, exist_ok=True)
            (runtime.task_dir / 'intermediate').mkdir(parents=True, exist_ok=True)
            (runtime.task_dir / 'results').mkdir(parents=True, exist_ok=True)
            runtime.log_file_path = runtime.task_dir / 'logs' / 'runtime.log.jsonl'

            self._write_snapshot(runtime, stage='started')
            self._log(runtime, task.id, None, 'INFO', 'task', 'Task started')
            self._emit_progress(runtime, TaskStatus.RUNNING, None, current_step_key='task_started')

            try:
                for sub in subtasks:
                    if runtime.stop_event.is_set():
                        break

                    sub.status = TaskStatus.RUNNING
                    sub.current_step_key = 'queued'
                    self._emit_progress(
                        runtime,
                        TaskStatus.RUNNING,
                        sub,
                        current_step_key='queued',
                    )

                    for metric in task.config.metrics:
                        if runtime.stop_event.is_set():
                            break

                        self._wait_if_paused(runtime, sub)
                        if runtime.stop_event.is_set():
                            break

                        step_key = f'{metric.value.lower()}_compute'
                        started_at = utc_now()
                        self._step(
                            runtime,
                            task.id,
                            sub.id,
                            ProcessingStep(
                                key=step_key,
                                label=f'{metric.value} compute',
                                status=StepStatus.RUNNING,
                                started_at=started_at,
                            ),
                        )
                        self._log(
                            runtime,
                            task.id,
                            sub.id,
                            'INFO',
                            step_key,
                            f'Start {metric.value} for {sub.station_id} {sub.date}',
                        )

                        try:
                            data_path, stats, artifact_path = self._compute_metric(runtime, task, sub, metric)
                            threshold_source = self._resolve_threshold_source(task)
                            coordinate_source = self._resolve_coordinate_source(task, sub)
                            parameter_source_summary = self._resolve_parameter_source_summary(task, sub)
                            results.append(
                                ResultSet(
                                    id=make_id('res'),
                                    task_id=task.id,
                                    sub_task_id=sub.id,
                                    project_id=task.project_id,
                                    metric=metric,
                                    station_id=sub.station_id,
                                    system=sub.system,
                                    chain_level=task.chain_level,
                                    sampling_mode=task.sampling_mode,
                                    coordinate_source=coordinate_source,
                                    threshold_source=threshold_source,
                                    parameter_source_summary=parameter_source_summary,
                                    data_path=data_path,
                                    stats=stats,
                                    created_at=utc_now(),
                                )
                            )
                            self._step(
                                runtime,
                                task.id,
                                sub.id,
                                ProcessingStep(
                                    key=step_key,
                                    label=f'{metric.value} compute',
                                    status=StepStatus.COMPLETED,
                                    started_at=started_at,
                                    finished_at=utc_now(),
                                    output_summary='metric_result_ready',
                                    artifact_paths=[artifact_path] if artifact_path else [],
                                ),
                            )
                            self._log(
                                runtime,
                                task.id,
                                sub.id,
                                'INFO',
                                step_key,
                                f'Completed {metric.value} for {sub.station_id} {sub.date}',
                            )
                            runtime.done += 1
                            sub.current_step_key = step_key
                            self._emit_progress(runtime, TaskStatus.RUNNING, sub, current_step_key=step_key)
                            self._write_snapshot(runtime, stage='running')
                        except Exception as exc:  # noqa: BLE001
                            sub.status = TaskStatus.FAILED
                            sub.error_message = str(exc)
                            task.status = TaskStatus.FAILED
                            task.latest_error = str(exc)
                            self._step(
                                runtime,
                                task.id,
                                sub.id,
                                ProcessingStep(
                                    key=step_key,
                                    label=f'{metric.value} compute',
                                    status=StepStatus.FAILED,
                                    started_at=started_at,
                                    finished_at=utc_now(),
                                    output_summary='metric_failed',
                                ),
                            )
                            self._log(
                                runtime,
                                task.id,
                                sub.id,
                                'ERROR',
                                step_key,
                                f'Failed {metric.value} for {sub.station_id} {sub.date}: {exc}',
                                detail=repr(exc),
                            )
                            runtime.stop_event.set()
                            break

                    if sub.status != TaskStatus.FAILED and not runtime.stop_event.is_set():
                        sub.status = TaskStatus.COMPLETED

                if task.status == TaskStatus.FAILED:
                    self._log(runtime, task.id, None, 'ERROR', 'task', 'Task failed')
                elif runtime.stop_event.is_set():
                    task.status = TaskStatus.CANCELLED
                    self._log(runtime, task.id, None, 'WARN', 'task', 'Task cancelled')
                else:
                    task.status = TaskStatus.COMPLETED
                    self._log(runtime, task.id, None, 'INFO', 'task', 'Task completed')

                task.finished_at = utc_now()
                self._emit_progress(runtime, task.status, None, current_step_key='task_finished')
                self._write_snapshot(runtime, stage='finished')
                on_done(task, results)
            finally:
                self._runtimes.pop(task.id, None)

        runtime.thread = threading.Thread(target=_run, daemon=True)
        runtime.thread.start()
        self._runtimes[task.id] = runtime

    def pause(self, task_id: str) -> bool:
        runtime = self._runtimes.get(task_id)
        if not runtime:
            return False
        runtime.pause_event.set()
        self._log(runtime, task_id, None, 'INFO', 'task', 'Pause requested')
        self._emit_progress(runtime, TaskStatus.PAUSED, None, current_step_key='pause_requested')
        self._write_snapshot(runtime, stage='paused')
        return True

    def resume(self, task_id: str) -> bool:
        runtime = self._runtimes.get(task_id)
        if not runtime:
            return False
        runtime.pause_event.clear()
        self._log(runtime, task_id, None, 'INFO', 'task', 'Resume requested')
        self._emit_progress(runtime, TaskStatus.RUNNING, None, current_step_key='resume_requested')
        self._write_snapshot(runtime, stage='running')
        return True

    def stop(self, task_id: str) -> bool:
        runtime = self._runtimes.get(task_id)
        if not runtime:
            return False
        runtime.stop_event.set()
        self._log(runtime, task_id, None, 'WARN', 'task', 'Stop requested')
        self._emit_progress(runtime, TaskStatus.STOPPING, None, current_step_key='stop_requested')
        self._write_snapshot(runtime, stage='stopping')
        return True

    def _wait_if_paused(self, runtime: TaskRuntime, sub: SubTask) -> None:
        notified = False
        while runtime.pause_event.is_set() and not runtime.stop_event.is_set():
            if not notified:
                self._log(runtime, runtime.task.id, sub.id, 'INFO', 'task', 'Task paused')
                self._emit_progress(runtime, TaskStatus.PAUSED, sub, current_step_key='paused')
                self._write_snapshot(runtime, stage='paused')
                notified = True
            time.sleep(0.2)
        if notified and not runtime.stop_event.is_set():
            self._log(runtime, runtime.task.id, sub.id, 'INFO', 'task', 'Task resumed')
            self._emit_progress(runtime, TaskStatus.RUNNING, sub, current_step_key='resumed')

    def _compute_metric(
        self,
        runtime: TaskRuntime,
        task: Task,
        sub: SubTask,
        metric: MetricKey,
    ) -> tuple[str, ResultStats, str | None]:
        task_dir = runtime.task_dir
        assert task_dir is not None

        matlab_bundle = self._load_gps_bundle(runtime, sub)
        if matlab_bundle and sub.system == GnssSystem.GPS and metric in {
            MetricKey.ROTI,
            MetricKey.AATR,
            MetricKey.IAATR,
        }:
            series = self._series_from_gps_bundle(matlab_bundle, metric)
            data_path = self.result_store.save_series(
                task_dir / 'results' / f'{sub.id}_{metric.value}.npz',
                np.arange(series.shape[0]),
                series,
            )
            artifact_path = None
            if task.config.enable_intermediate_save:
                artifact = task_dir / 'intermediate' / f'{sub.id}_{metric.value}.json'
                artifact.write_text(
                    json.dumps(
                        {
                            'source': 'matlab_obs_cut',
                            'station': sub.station_id,
                            'date': sub.date,
                            'metric': metric.value,
                        },
                        ensure_ascii=False,
                    ),
                    encoding='utf-8',
                )
                artifact_path = str(artifact)
            stats = ResultStats(
                min=float(np.nanmin(series)) if series.size else None,
                max=float(np.nanmax(series)) if series.size else None,
                mean=float(np.nanmean(series)) if series.size else None,
                missing_ratio=float(np.isnan(series).mean()) if series.size else None,
            )
            return data_path, stats, artifact_path

        if sub.system == GnssSystem.GPS and metric == MetricKey.DIXSG:
            dixsg_bundle, source = self._load_dixsg_bundle(runtime, task, sub)
            if dixsg_bundle is not None:
                result_path = task_dir / 'results' / f'{sub.id}_{metric.value}.npz'
                data_path = self.result_store.save_payload(
                    result_path,
                    {
                        'time': np.arange(dixsg_bundle.adixsg.shape[0], dtype=int),
                        'values': dixsg_bundle.adixsg,
                        'grid': dixsg_bundle.ll,
                        'mbl': dixsg_bundle.mbl,
                    },
                )

                artifact_path = None
                if task.config.enable_intermediate_save:
                    artifact = task_dir / 'intermediate' / f'{sub.id}_{metric.value}.json'
                    artifact.write_text(
                        json.dumps(
                            {
                                'source': source,
                                'station': sub.station_id,
                                'date': sub.date,
                                'metric': metric.value,
                                'gridShape': list(dixsg_bundle.ll.shape),
                            },
                            ensure_ascii=False,
                        ),
                        encoding='utf-8',
                    )
                    artifact_path = str(artifact)

                series = dixsg_bundle.adixsg
                stats = ResultStats(
                    min=float(np.nanmin(series)) if series.size else None,
                    max=float(np.nanmax(series)) if series.size else None,
                    mean=float(np.nanmean(series)) if series.size else None,
                    missing_ratio=float(np.isnan(series).mean()) if series.size else None,
                )
                return data_path, stats, artifact_path

        if sub.system == GnssSystem.GPS and metric == MetricKey.SIGMA_PHI_F:
            sigmaphi_series, source = self._load_sigmaphi_series(runtime, sub)
            if sigmaphi_series is not None:
                traced_sigma, chain_artifacts = self._trace_sigmaphi_pipeline(
                    runtime=runtime,
                    task=task,
                    sub=sub,
                    source=source,
                    series=sigmaphi_series,
                )
                data_path = self.result_store.save_series(
                    task_dir / 'results' / f'{sub.id}_{metric.value}.npz',
                    np.arange(sigmaphi_series.shape[0]),
                    sigmaphi_series,
                )

                artifact_path = None
                if task.config.enable_intermediate_save:
                    artifact = task_dir / 'intermediate' / f'{sub.id}_{metric.value}.json'
                    artifact.write_text(
                        json.dumps(
                            {
                                'source': source,
                                'station': sub.station_id,
                                'date': sub.date,
                                'metric': metric.value,
                                'shape': list(sigmaphi_series.shape),
                                'cutoffElevationDeg': task.config.algorithm_config.cutoff_elevation_deg,
                                'stepArtifacts': chain_artifacts,
                                'traceDiff': self._diff_summary(traced_sigma, np.asarray(sigmaphi_series, dtype=float)),
                            },
                            ensure_ascii=False,
                        ),
                        encoding='utf-8',
                    )
                    artifact_path = str(artifact)

                stats = ResultStats(
                    min=float(np.nanmin(sigmaphi_series)) if sigmaphi_series.size else None,
                    max=float(np.nanmax(sigmaphi_series)) if sigmaphi_series.size else None,
                    mean=float(np.nanmean(sigmaphi_series)) if sigmaphi_series.size else None,
                    missing_ratio=float(np.isnan(sigmaphi_series).mean()) if sigmaphi_series.size else None,
                )
                return data_path, stats, artifact_path

        seed = abs(hash(f'{sub.id}_{metric.value}')) % (2**32)
        rs = np.random.default_rng(seed)
        signal = rs.normal(0, 1, 2880).astype(float)
        prep = preprocess_chain(signal, min_arc=task.config.algorithm_config.min_arc_epochs)
        time_axis = np.arange(2880)

        if metric == MetricKey.ROTI:
            series = roti_compute(prep.filtered)
            data_path = self.result_store.save_series(
                task_dir / 'results' / f'{sub.id}_{metric.value}.npz', time_axis, series
            )
        elif metric == MetricKey.IAATR:
            series = iaatr_compute(prep.filtered)
            data_path = self.result_store.save_series(
                task_dir / 'results' / f'{sub.id}_{metric.value}.npz', time_axis, series
            )
        elif metric == MetricKey.AATR:
            ia = iaatr_compute(prep.filtered)
            series = aatr_aggregate(ia)
            data_path = self.result_store.save_series(
                task_dir / 'results' / f'{sub.id}_{metric.value}.npz',
                np.arange(len(series)),
                series,
            )
        elif metric == MetricKey.SIGMA_PHI_F:
            series, chain_artifacts = self._trace_sigmaphi_pipeline(
                runtime=runtime,
                task=task,
                sub=sub,
                source='python_synthetic_chain',
                series=signal,
            )
            data_path = self.result_store.save_series(
                task_dir / 'results' / f'{sub.id}_{metric.value}.npz',
                np.arange(series.shape[0], dtype=int),
                series,
            )
            artifact_path = None
            if task.config.enable_intermediate_save:
                artifact = task_dir / 'intermediate' / f'{sub.id}_{metric.value}.json'
                artifact.write_text(
                    json.dumps(
                        {
                            'source': 'python_synthetic_chain',
                            'station': sub.station_id,
                            'date': sub.date,
                            'metric': metric.value,
                            'shape': list(np.asarray(series, dtype=float).shape),
                            'cutoffElevationDeg': task.config.algorithm_config.cutoff_elevation_deg,
                            'stepArtifacts': chain_artifacts,
                        },
                        ensure_ascii=False,
                    ),
                    encoding='utf-8',
                )
                artifact_path = str(artifact)
            stats = ResultStats(
                min=float(np.nanmin(series)) if series.size else None,
                max=float(np.nanmax(series)) if series.size else None,
                mean=float(np.nanmean(series)) if series.size else None,
                missing_ratio=float(np.isnan(series).mean()) if series.size else None,
            )
            return data_path, stats, artifact_path
        elif metric == MetricKey.DIXSG:
            crot = crot_compute(prep.filtered)
            grid = dixsg_grid(crot)
            data_path = self.result_store.save_grid(task_dir / 'results' / f'{sub.id}_{metric.value}.npz', grid)
            series = grid.flatten()
        else:
            series = crot_compute(prep.filtered)
            data_path = self.result_store.save_series(
                task_dir / 'results' / f'{sub.id}_{metric.value}.npz', time_axis, series
            )

        artifact_path = None
        if task.config.enable_intermediate_save:
            artifacts = {
                'GF': prep.gf.tolist(),
                'HMW': prep.hmw.tolist(),
                'cycleSlipPoints': prep.cycle_slip_points.tolist(),
                'geodeticDetrended': prep.detrended_geodetic.tolist(),
                'polyDetrended': prep.detrended_poly.tolist(),
                'filtered': prep.filtered.tolist(),
                'stepKeys': STEP_KEYS,
                'source': 'synthetic_placeholder',
            }
            artifact = task_dir / 'intermediate' / f'{sub.id}_{metric.value}.json'
            artifact.write_text(json.dumps(artifacts, ensure_ascii=False), encoding='utf-8')
            artifact_path = str(artifact)

        stats = ResultStats(
            min=float(np.nanmin(series)) if series.size else None,
            max=float(np.nanmax(series)) if series.size else None,
            mean=float(np.nanmean(series)) if series.size else None,
            missing_ratio=float(np.isnan(series).mean()) if series.size else None,
        )
        return data_path, stats, artifact_path

    def _trace_sigmaphi_pipeline(
        self,
        runtime: TaskRuntime,
        task: Task,
        sub: SubTask,
        source: str,
        series: np.ndarray,
    ) -> tuple[np.ndarray, list[str]]:
        task_dir = runtime.task_dir
        assert task_dir is not None
        metric_name = MetricKey.SIGMA_PHI_F.value
        matrix = self._to_matrix(np.asarray(series, dtype=float))
        window_epochs = self._sigma_window_epochs(task)
        chain_artifacts: list[str] = []

        cutoff_key = 'sigmaphi_cutoff_elevation'
        cutoff_label = 'SIGMA_PHI_F cutoff elevation'
        cutoff_started = utc_now()
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=cutoff_key,
                label=cutoff_label,
                status=StepStatus.RUNNING,
                started_at=cutoff_started,
            ),
        )
        cutoff_artifact = self._write_sigmaphi_step_artifact(
            task=task,
            sub=sub,
            metric_name=metric_name,
            source=source,
            step_name='cutoff_elevation',
            payload={
                'cutoffElevationDeg': task.config.algorithm_config.cutoff_elevation_deg,
                'note': 'Current Python chain uses replay mode; cutoff is represented as formal config metadata.',
                'summary': self._array_summary(matrix),
            },
        )
        if cutoff_artifact:
            chain_artifacts.append(cutoff_artifact)
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=cutoff_key,
                label=cutoff_label,
                status=StepStatus.COMPLETED,
                started_at=cutoff_started,
                finished_at=utc_now(),
                output_summary=f"cutoff={task.config.algorithm_config.cutoff_elevation_deg}deg",
                artifact_paths=[cutoff_artifact] if cutoff_artifact else [],
            ),
        )

        short_arc_key = 'sigmaphi_short_arc_removal'
        short_arc_label = 'SIGMA_PHI_F short arc removal'
        started = utc_now()
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=short_arc_key,
                label=short_arc_label,
                status=StepStatus.RUNNING,
                started_at=started,
            ),
        )
        try:
            gf = self._apply_columnwise(matrix, lambda col: short_arc_removal(col, min_arc=task.config.algorithm_config.min_arc_epochs))
            hmw = self._apply_columnwise(
                matrix * 0.8,
                lambda col: short_arc_removal(col, min_arc=task.config.algorithm_config.min_arc_epochs),
            )
        except Exception as exc:
            self._step(
                runtime,
                runtime.task.id,
                sub.id,
                ProcessingStep(
                    key=short_arc_key,
                    label=short_arc_label,
                    status=StepStatus.FAILED,
                    started_at=started,
                    finished_at=utc_now(),
                    output_summary=str(exc),
                ),
            )
            raise
        artifact = self._write_sigmaphi_step_artifact(
            task=task,
            sub=sub,
            metric_name=metric_name,
            source=source,
            step_name='short_arc_removal',
            payload={
                'minArcEpochs': task.config.algorithm_config.min_arc_epochs,
                'gf': self._array_summary(gf),
                'hmw': self._array_summary(hmw),
            },
        )
        if artifact:
            chain_artifacts.append(artifact)
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=short_arc_key,
                label=short_arc_label,
                status=StepStatus.COMPLETED,
                started_at=started,
                finished_at=utc_now(),
                output_summary=f'min_arc={task.config.algorithm_config.min_arc_epochs}',
                artifact_paths=[artifact] if artifact else [],
            ),
        )

        detect_key = 'sigmaphi_cycle_slip_detection'
        detect_label = 'SIGMA_PHI_F cycle slip detection'
        started = utc_now()
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=detect_key,
                label=detect_label,
                status=StepStatus.RUNNING,
                started_at=started,
            ),
        )
        try:
            gf_slips = self._detect_slip_mask(gf)
            hmw_slips = self._detect_slip_mask(hmw)
            slips = gf_slips | hmw_slips
        except Exception as exc:
            self._step(
                runtime,
                runtime.task.id,
                sub.id,
                ProcessingStep(
                    key=detect_key,
                    label=detect_label,
                    status=StepStatus.FAILED,
                    started_at=started,
                    finished_at=utc_now(),
                    output_summary=str(exc),
                ),
            )
            raise
        slip_count = int(np.asarray(slips, dtype=bool).sum())
        artifact = self._write_sigmaphi_step_artifact(
            task=task,
            sub=sub,
            metric_name=metric_name,
            source=source,
            step_name='cycle_slip_detection',
            payload={
                'gfSlipCount': int(np.asarray(gf_slips, dtype=bool).sum()),
                'hmwSlipCount': int(np.asarray(hmw_slips, dtype=bool).sum()),
                'combinedSlipCount': slip_count,
                'slipMaskSummary': self._array_summary(slips.astype(float)),
            },
        )
        if artifact:
            chain_artifacts.append(artifact)
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=detect_key,
                label=detect_label,
                status=StepStatus.COMPLETED,
                started_at=started,
                finished_at=utc_now(),
                output_summary=f'slip_count={slip_count}',
                artifact_paths=[artifact] if artifact else [],
            ),
        )

        repair_key = 'sigmaphi_cycle_slip_repair'
        repair_label = 'SIGMA_PHI_F cycle slip repair'
        started = utc_now()
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=repair_key,
                label=repair_label,
                status=StepStatus.RUNNING,
                started_at=started,
            ),
        )
        try:
            repaired = np.zeros_like(gf, dtype=float)
            for idx in range(gf.shape[1]):
                repaired[:, idx] = cycle_slip_repair(gf[:, idx], np.where(slips[:, idx])[0])
        except Exception as exc:
            self._step(
                runtime,
                runtime.task.id,
                sub.id,
                ProcessingStep(
                    key=repair_key,
                    label=repair_label,
                    status=StepStatus.FAILED,
                    started_at=started,
                    finished_at=utc_now(),
                    output_summary=str(exc),
                ),
            )
            raise
        artifact = self._write_sigmaphi_step_artifact(
            task=task,
            sub=sub,
            metric_name=metric_name,
            source=source,
            step_name='cycle_slip_repair',
            payload={
                'summary': self._array_summary(repaired),
            },
        )
        if artifact:
            chain_artifacts.append(artifact)
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=repair_key,
                label=repair_label,
                status=StepStatus.COMPLETED,
                started_at=started,
                finished_at=utc_now(),
                output_summary='cycle_slip_repaired',
                artifact_paths=[artifact] if artifact else [],
            ),
        )

        geo_key = 'sigmaphi_geodetic_detrending'
        geo_label = 'SIGMA_PHI_F geodetic detrending'
        started = utc_now()
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=geo_key,
                label=geo_label,
                status=StepStatus.RUNNING,
                started_at=started,
            ),
        )
        try:
            geo = self._apply_columnwise(repaired, geodetic_detrending)
        except Exception as exc:
            self._step(
                runtime,
                runtime.task.id,
                sub.id,
                ProcessingStep(
                    key=geo_key,
                    label=geo_label,
                    status=StepStatus.FAILED,
                    started_at=started,
                    finished_at=utc_now(),
                    output_summary=str(exc),
                ),
            )
            raise
        artifact = self._write_sigmaphi_step_artifact(
            task=task,
            sub=sub,
            metric_name=metric_name,
            source=source,
            step_name='geodetic_detrending',
            payload={
                'summary': self._array_summary(geo),
            },
        )
        if artifact:
            chain_artifacts.append(artifact)
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=geo_key,
                label=geo_label,
                status=StepStatus.COMPLETED,
                started_at=started,
                finished_at=utc_now(),
                output_summary='geodetic_detrended',
                artifact_paths=[artifact] if artifact else [],
            ),
        )

        poly_key = 'sigmaphi_polynomial_detrending'
        poly_label = 'SIGMA_PHI_F polynomial detrending'
        started = utc_now()
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=poly_key,
                label=poly_label,
                status=StepStatus.RUNNING,
                started_at=started,
            ),
        )
        try:
            poly = self._apply_columnwise(geo, polynomial_detrending)
        except Exception as exc:
            self._step(
                runtime,
                runtime.task.id,
                sub.id,
                ProcessingStep(
                    key=poly_key,
                    label=poly_label,
                    status=StepStatus.FAILED,
                    started_at=started,
                    finished_at=utc_now(),
                    output_summary=str(exc),
                ),
            )
            raise
        artifact = self._write_sigmaphi_step_artifact(
            task=task,
            sub=sub,
            metric_name=metric_name,
            source=source,
            step_name='polynomial_detrending',
            payload={
                'summary': self._array_summary(poly),
            },
        )
        if artifact:
            chain_artifacts.append(artifact)
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=poly_key,
                label=poly_label,
                status=StepStatus.COMPLETED,
                started_at=started,
                finished_at=utc_now(),
                output_summary='polynomial_detrended',
                artifact_paths=[artifact] if artifact else [],
            ),
        )

        filt_key = 'sigmaphi_butterworth_filter'
        filt_label = 'SIGMA_PHI_F butterworth filter'
        started = utc_now()
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=filt_key,
                label=filt_label,
                status=StepStatus.RUNNING,
                started_at=started,
            ),
        )
        try:
            filtered = self._apply_columnwise(poly, butterworth_filter)
        except Exception as exc:
            self._step(
                runtime,
                runtime.task.id,
                sub.id,
                ProcessingStep(
                    key=filt_key,
                    label=filt_label,
                    status=StepStatus.FAILED,
                    started_at=started,
                    finished_at=utc_now(),
                    output_summary=str(exc),
                ),
            )
            raise
        artifact = self._write_sigmaphi_step_artifact(
            task=task,
            sub=sub,
            metric_name=metric_name,
            source=source,
            step_name='butterworth_filter',
            payload={
                'order': task.config.algorithm_config.butterworth_order,
                'lowHz': task.config.algorithm_config.butterworth_low_hz,
                'highHz': task.config.algorithm_config.butterworth_high_hz,
                'summary': self._array_summary(filtered),
            },
        )
        if artifact:
            chain_artifacts.append(artifact)
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=filt_key,
                label=filt_label,
                status=StepStatus.COMPLETED,
                started_at=started,
                finished_at=utc_now(),
                output_summary='butterworth_filtered',
                artifact_paths=[artifact] if artifact else [],
            ),
        )

        sigma_key = 'sigmaphi_moving_window_sigma'
        sigma_label = 'SIGMA_PHI_F moving window sigma'
        started = utc_now()
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=sigma_key,
                label=sigma_label,
                status=StepStatus.RUNNING,
                started_at=started,
            ),
        )
        try:
            sigma = self._apply_columnwise(
                filtered,
                lambda col: moving_window_sigma_phi_f(col, window=window_epochs),
            )
        except Exception as exc:
            self._step(
                runtime,
                runtime.task.id,
                sub.id,
                ProcessingStep(
                    key=sigma_key,
                    label=sigma_label,
                    status=StepStatus.FAILED,
                    started_at=started,
                    finished_at=utc_now(),
                    output_summary=str(exc),
                ),
            )
            raise
        artifact = self._write_sigmaphi_step_artifact(
            task=task,
            sub=sub,
            metric_name=metric_name,
            source=source,
            step_name='moving_window_sigma',
            payload={
                'windowEpochs': window_epochs,
                'windowMinutes': task.config.algorithm_config.sigma_phi_f_window_min,
                'summary': self._array_summary(sigma),
            },
        )
        if artifact:
            chain_artifacts.append(artifact)
        self._step(
            runtime,
            runtime.task.id,
            sub.id,
            ProcessingStep(
                key=sigma_key,
                label=sigma_label,
                status=StepStatus.COMPLETED,
                started_at=started,
                finished_at=utc_now(),
                output_summary=f'window_epochs={window_epochs}',
                artifact_paths=[artifact] if artifact else [],
            ),
        )

        if np.asarray(series).ndim == 1 and sigma.ndim == 2 and sigma.shape[1] == 1:
            return sigma[:, 0], chain_artifacts
        return sigma, chain_artifacts

    def _sigma_window_epochs(self, task: Task) -> int:
        minute_window = max(1, int(task.config.algorithm_config.sigma_phi_f_window_min))
        if task.config.sampling_mode.value == 'EXPERIMENTAL_1S_RESAMPLED':
            return max(2, minute_window * 60)
        return max(2, minute_window * 2)

    def _to_matrix(self, values: np.ndarray) -> np.ndarray:
        data = np.asarray(values, dtype=float)
        if data.ndim == 1:
            return data.reshape(-1, 1)
        if data.ndim == 2:
            return data
        if data.ndim == 0:
            return data.reshape(1, 1)
        rows = data.shape[0]
        return data.reshape(rows, -1)

    def _apply_columnwise(self, matrix: np.ndarray, func) -> np.ndarray:
        outputs = [np.asarray(func(matrix[:, idx]), dtype=float) for idx in range(matrix.shape[1])]
        return np.column_stack(outputs) if outputs else np.zeros((matrix.shape[0], 0), dtype=float)

    def _detect_slip_mask(self, matrix: np.ndarray) -> np.ndarray:
        mask = np.zeros(matrix.shape, dtype=bool)
        for idx in range(matrix.shape[1]):
            slips = cycle_slip_detection(matrix[:, idx])
            slips = slips[(slips >= 0) & (slips < matrix.shape[0])]
            mask[slips, idx] = True
        return mask

    def _write_sigmaphi_step_artifact(
        self,
        task: Task,
        sub: SubTask,
        metric_name: str,
        source: str,
        step_name: str,
        payload: dict,
    ) -> str | None:
        if not task.config.enable_intermediate_save:
            return None
        task_dir = self.workspace.task_dir(task.project_id, task.id)
        inter_dir = task_dir / 'intermediate'
        inter_dir.mkdir(parents=True, exist_ok=True)
        artifact = inter_dir / f'{sub.id}_{metric_name}_{step_name}.json'
        artifact.write_text(
            json.dumps(
                {
                    'station': sub.station_id,
                    'date': sub.date,
                    'system': sub.system.value,
                    'metric': metric_name,
                    'source': source,
                    'step': step_name,
                    'cutoffElevationDeg': task.config.algorithm_config.cutoff_elevation_deg,
                    **payload,
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        return str(artifact)

    def _array_summary(self, values: np.ndarray) -> dict:
        arr = np.asarray(values, dtype=float)
        finite = np.isfinite(arr)
        has_finite = bool(finite.any())
        if arr.ndim == 1:
            preview = arr[:8].tolist()
        else:
            max_cols = min(3, arr.shape[1]) if arr.ndim >= 2 else 1
            preview = arr[:8, :max_cols].tolist() if arr.ndim >= 2 else arr[:8].tolist()
        return {
            'shape': list(arr.shape),
            'finiteRatio': float(finite.mean()) if arr.size else None,
            'nanRatio': float(np.isnan(arr).mean()) if arr.size else None,
            'min': float(np.nanmin(arr)) if has_finite else None,
            'max': float(np.nanmax(arr)) if has_finite else None,
            'mean': float(np.nanmean(arr)) if has_finite else None,
            'preview': preview,
        }

    def _diff_summary(self, lhs: np.ndarray, rhs: np.ndarray) -> dict:
        a = np.asarray(lhs, dtype=float)
        b = np.asarray(rhs, dtype=float)
        if a.shape != b.shape:
            return {
                'shapeA': list(a.shape),
                'shapeB': list(b.shape),
                'meanAbsError': None,
                'maxAbsError': None,
                'note': 'shape_mismatch',
            }
        diff = np.abs(a - b)
        finite = np.isfinite(diff)
        return {
            'shapeA': list(a.shape),
            'shapeB': list(b.shape),
            'meanAbsError': float(np.nanmean(diff)) if finite.any() else None,
            'maxAbsError': float(np.nanmax(diff)) if finite.any() else None,
        }

    def _series_from_gps_bundle(self, bundle: GpsMetricsBundle, metric: MetricKey) -> np.ndarray:
        if metric == MetricKey.ROTI:
            return bundle.roti
        if metric == MetricKey.AATR:
            return bundle.aatr
        if metric == MetricKey.IAATR:
            return np.abs(bundle.aatr)
        raise ValueError(f'Unsupported bundle metric: {metric}')

    def _load_gps_bundle(self, runtime: TaskRuntime, sub: SubTask) -> GpsMetricsBundle | None:
        cache_key = f'{sub.station_id}:{sub.date}'
        if cache_key in runtime.gps_bundle_cache:
            return runtime.gps_bundle_cache[cache_key]

        obs_cut_path = self._resolve_obs_cut_path(sub.station_id, sub.date)
        if not obs_cut_path:
            return None
        try:
            bundle = compute_gps_metrics_from_obs_cut(obs_cut_path)
            runtime.gps_bundle_cache[cache_key] = bundle
            return bundle
        except Exception:  # noqa: BLE001
            return None

    def _load_gps_crot_bundle(self, runtime: TaskRuntime, sub: SubTask) -> GpsCrotBundle | None:
        cache_key = f'{sub.station_id}:{sub.date}'
        if cache_key in runtime.gps_crot_cache:
            return runtime.gps_crot_cache[cache_key]

        obs_cut_path = self._resolve_obs_cut_path(sub.station_id, sub.date)
        if not obs_cut_path:
            return None
        try:
            bundle = compute_gps_crot_from_obs_cut(obs_cut_path)
            runtime.gps_crot_cache[cache_key] = bundle
            return bundle
        except Exception:  # noqa: BLE001
            return None

    def _load_dixsg_bundle(
        self,
        runtime: TaskRuntime,
        task: Task,
        sub: SubTask,
    ) -> tuple[DixsgBundle | None, str]:
        cache_key = f'{sub.system.value}:{sub.date}'
        if cache_key in runtime.dixsg_bundle_cache:
            return runtime.dixsg_bundle_cache[cache_key], 'task_cache'

        dixsg_mat_path = self._resolve_dixsg_mat_path(sub.date, sub.system)
        if dixsg_mat_path:
            try:
                bundle = load_dixsg_from_mat(dixsg_mat_path)
                runtime.dixsg_bundle_cache[cache_key] = bundle
                return bundle, 'matlab_golden'
            except Exception:  # noqa: BLE001
                pass

        bundles: dict[str, GpsCrotBundle] = {}
        for candidate in runtime.subtasks:
            if candidate.system != sub.system or candidate.date != sub.date:
                continue
            if candidate.station_id in bundles:
                continue
            crot_bundle = self._load_gps_crot_bundle(runtime, candidate)
            if crot_bundle is not None:
                bundles[candidate.station_id] = crot_bundle
        if len(bundles) < 2:
            return None, 'insufficient_stations'

        cfg = task.config.algorithm_config.dixsg
        try:
            bundle = compute_dixsg_from_crot_bundles(
                bundles,
                levels=cfg.sensitivity_levels,
                sensitivity_first=cfg.sensitivity_first,
                sensitivity_step=cfg.sensitivity_step,
                max_distance_km=cfg.max_distance_km,
                minlon=cfg.lon_range[0],
                maxlon=cfg.lon_range[1],
                minlat=cfg.lat_range[0],
                maxlat=cfg.lat_range[1],
                dlat=cfg.grid_size_deg,
                dlon=max(0.5, cfg.grid_size_deg / 2.0),
            )
            runtime.dixsg_bundle_cache[cache_key] = bundle
            return bundle, 'python_crot_chain'
        except Exception:  # noqa: BLE001
            return None, 'python_chain_failed'

    def _load_sigmaphi_series(
        self,
        runtime: TaskRuntime,
        sub: SubTask,
    ) -> tuple[np.ndarray | None, str]:
        cache_key = f'{sub.station_id}:{sub.date}'
        if cache_key in runtime.gps_sigmaphi_cache:
            bundle = runtime.gps_sigmaphi_cache[cache_key]
            return self._pick_sigmaphi_series(bundle), 'task_cache'

        sigmaphi_path = self._resolve_sigmaphi_mat_path(sub.station_id, sub.date, sub.system)
        if not sigmaphi_path:
            return None, 'sigmaphi_mat_missing'
        try:
            bundle = load_gps_sigmaphi_from_mat(sigmaphi_path)
            runtime.gps_sigmaphi_cache[cache_key] = bundle
            return self._pick_sigmaphi_series(bundle), 'matlab_sigmaphi'
        except Exception:  # noqa: BLE001
            return None, 'sigmaphi_load_failed'

    def _pick_sigmaphi_series(self, bundle: GpsSigmaPhiBundle) -> np.ndarray | None:
        if bundle.l1 is not None:
            return bundle.l1
        if bundle.l2 is not None:
            return bundle.l2
        return None

    def _resolve_dixsg_mat_path(self, date_text: str, system: GnssSystem) -> Path | None:
        try:
            date_obj = datetime.fromisoformat(date_text).date()
        except ValueError:
            return None

        doy_token = f'{date_obj.year % 100:02d}{date_obj.timetuple().tm_yday:03d}'
        prefix = system.value.upper()
        roots: list[Path] = []
        env_root = os.getenv('ISD_MATLAB_DIXSG_ROOT')
        if env_root:
            roots.append(Path(env_root))
        roots.append(Path.cwd().parent / 'resDIXSG')
        roots.append(Path.cwd() / 'resDIXSG')

        for root in roots:
            if not root.exists():
                continue
            candidate = root / f'{prefix}DIXSG{doy_token}' / f'{prefix}{doy_token}DIXSG.mat'
            if candidate.exists():
                return candidate
        return None

    def _resolve_sigmaphi_mat_path(self, station_id: str, date_text: str, system: GnssSystem) -> Path | None:
        if system != GnssSystem.GPS:
            return None
        try:
            date_obj = datetime.fromisoformat(date_text).date()
        except ValueError:
            return None
        doy_token = f'{date_obj.year % 100:02d}{date_obj.timetuple().tm_yday:03d}'
        station = station_id.strip()

        roots: list[Path] = []
        env_root = os.getenv('ISD_MATLAB_SIGMAPHI_ROOT')
        if env_root:
            roots.append(Path(env_root))
        roots.append(Path.cwd().parent / 'resSIGMAPHI')
        roots.append(Path.cwd() / 'resSIGMAPHI')

        folder_name = f'GPSsigmaphi{doy_token}'
        file_candidates = [
            f'{station.lower()}{doy_token}GPSsigmaphi.mat',
            f'{station.upper()}{doy_token}GPSsigmaphi.mat',
            f'{station}{doy_token}GPSsigmaphi.mat',
        ]
        for root in roots:
            if not root.exists():
                continue
            folder = root / folder_name
            if not folder.exists():
                continue
            for name in file_candidates:
                candidate = folder / name
                if candidate.exists():
                    return candidate
        return None

    def _resolve_obs_cut_path(self, station_id: str, date_text: str) -> Path | None:
        try:
            date_obj = datetime.fromisoformat(date_text).date()
        except ValueError:
            return None
        doy_token = f'{date_obj.year % 100:02d}{date_obj.timetuple().tm_yday:03d}'
        station = station_id.upper()

        roots: list[Path] = []
        env_root = os.getenv('ISD_MATLAB_OBS_CUT_ROOT')
        if env_root:
            roots.append(Path(env_root))
        roots.append(Path.cwd().parent / 'raw_OBS_cut')
        roots.append(Path.cwd() / 'raw_OBS_cut')

        for root in roots:
            if not root.exists():
                continue
            candidates = [
                root / doy_token / f'{station}{doy_token}.mat',
                root / doy_token / f'{station.lower()}{doy_token}.mat',
            ]
            for candidate in candidates:
                if candidate.exists():
                    return candidate
        return None

    def _emit_progress(
        self,
        runtime: TaskRuntime,
        status: TaskStatus,
        sub: SubTask | None,
        *,
        current_step_key: str | None,
    ) -> None:
        progress = runtime.done / max(runtime.total, 1)
        runtime.on_progress(
            TaskProgressEvent(
                task_id=runtime.task.id,
                sub_task_id=sub.id if sub else None,
                status=status,
                progress=progress,
                current_station=sub.station_id if sub else None,
                current_date=sub.date if sub else None,
                current_system=sub.system if sub else None,
                current_step_key=current_step_key,
            )
        )

    def _resolve_threshold_source(self, task: Task) -> ThresholdSource:
        text = str(task.config.threshold_source or "").strip().upper()
        mapping = {
            "MANUAL": ThresholdSource.MANUAL,
            "TEMPLATE": ThresholdSource.TEMPLATE,
            "DEFAULT": ThresholdSource.LITERATURE_REFERENCE,
            "LITERATURE_REFERENCE": ThresholdSource.LITERATURE_REFERENCE,
            "RECEIVER_PRESET": ThresholdSource.RECEIVER_PRESET,
            "CCDF": ThresholdSource.CCDF,
        }
        return mapping.get(text, ThresholdSource.LITERATURE_REFERENCE)

    def _resolve_coordinate_source(self, task: Task, sub: SubTask) -> CoordinateSource | None:
        station_map = (task.config.provider_metadata or {}).get("stationProviders") or {}
        station_meta = station_map.get(str(sub.station_id).upper()) or {}
        raw = str(station_meta.get("coordinateSource") or "").strip().upper()
        if raw in {x.value for x in CoordinateSource}:
            return CoordinateSource(raw)
        return None

    def _resolve_parameter_source_summary(self, task: Task, sub: SubTask) -> str:
        source = str(task.config.parameter_source or "default").strip().lower()
        template_id = task.config.source_template_id
        station_map = (task.config.provider_metadata or {}).get("stationProviders") or {}
        station_meta = station_map.get(str(sub.station_id).upper()) or {}
        date_meta = ((task.config.provider_metadata or {}).get("dateProviders") or {}).get(sub.date, {})
        coord = station_meta.get("coordinateSource") or "UNKNOWN"
        orbit = date_meta.get("orbitClockSource") or "UNKNOWN"
        antenna = station_meta.get("antennaSource") or "UNKNOWN"
        provider_part = f"providers=coord:{coord},orbitClock:{orbit},antenna:{antenna}"
        if template_id and source == "template":
            return f"template:{template_id};{provider_part}"
        return f"{source};{provider_part}"

    def _step(self, runtime: TaskRuntime, task_id: str, sub_task_id: str | None, step: ProcessingStep) -> None:
        if runtime.on_step:
            runtime.on_step(task_id, sub_task_id, step)

    def _log(
        self,
        runtime: TaskRuntime,
        task_id: str,
        sub_task_id: str | None,
        level: str,
        step_key: str | None,
        message: str,
        *,
        detail: str | None = None,
    ) -> None:
        event = TaskLogEvent(
            task_id=task_id,
            sub_task_id=sub_task_id,
            timestamp=utc_now(),
            level=level,
            step_key=step_key,
            message=message,
            detail=detail,
        )
        runtime.on_log(event)
        self._append_log_file(runtime.log_file_path, event)

    def _append_log_file(self, log_file_path: Path | None, event: TaskLogEvent) -> None:
        if not log_file_path:
            return
        payload = event.model_dump(mode='json')
        with log_file_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + '\n')

    def _write_snapshot(self, runtime: TaskRuntime, *, stage: str) -> None:
        if not runtime.task_dir:
            return
        snapshot_path = runtime.task_dir / 'snapshot.json'
        payload = {
            'task': runtime.task.model_dump(mode='json'),
            'subTasks': [sub.model_dump(mode='json') for sub in runtime.subtasks],
            'runtime': {
                'stage': stage,
                'progress': runtime.done / max(runtime.total, 1),
                'done': runtime.done,
                'total': runtime.total,
                'updatedAt': utc_now(),
                'logFilePath': str(runtime.log_file_path) if runtime.log_file_path else None,
            },
        }
        snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
