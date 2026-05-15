from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from .enums import (
    ApiLogLevel,
    ChainLevel,
    CoordinateSource,
    EventDetectionSupport,
    FileKind,
    GnssSystem,
    MetricKey,
    PppFallbackStrategy,
    PppStatus,
    ProjectStatus,
    SamplingMode,
    StepStatus,
    TaskStatus,
    TaskType,
    TemplateScope,
    ThresholdSource,
    ValidationLevel,
    ValidationStatus,
)


class DateRange(BaseModel):
    start: str
    end: str


class Project(BaseModel):
    id: str
    name: str
    description: str | None = None
    root_path: str
    created_at: str
    updated_at: str
    data_range: DateRange | None = None
    default_output_path: str
    tags: list[str] = Field(default_factory=list)
    status: ProjectStatus


class Station(BaseModel):
    id: str
    project_id: str
    station_code: str
    latitude: float | None = None
    longitude: float | None = None
    height: float | None = None
    systems: list[GnssSystem] = Field(default_factory=list)
    time_coverage: DateRange | None = None
    coordinate_source: CoordinateSource = CoordinateSource.RINEX_APPROX
    receiver_model: str | None = None
    receiver_manufacturer: str | None = None
    firmware_version: str | None = None
    antenna_model: str | None = None
    antenna_calibration_source: str | None = None
    is_scintillation_reference_station: bool = False
    ppp_status: PppStatus = PppStatus.NOT_STARTED
    ppp_log_path: str | None = None
    validation_summary: str | None = None


class ProjectFile(BaseModel):
    id: str
    project_id: str
    station_id: str | None = None
    kind: FileKind
    file_path: str
    file_name: str
    rinex_version: str | None = None
    sampling_interval_sec: int | None = None
    systems: list[GnssSystem] | None = None
    file_date: str | None = None
    matched: bool = False
    validation_status: ValidationStatus = ValidationStatus.WARNING
    issues: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] | None = None


class MetricSupportProfile(BaseModel):
    metric: MetricKey
    systems: list[GnssSystem]
    chain_level: ChainLevel
    event_detection_support: EventDetectionSupport
    region_mode_support: bool


class ThresholdConfig(BaseModel):
    metric: MetricKey
    value: float
    unit: str
    source: ThresholdSource
    station_id: str | None = None
    receiver_model: str | None = None
    notes: str | None = None


class CycleSlipConfig(BaseModel):
    hmw_sigma_factor: float = 5.0
    window_size: int = 30
    auto_repair: bool = True


class DixsgConfig(BaseModel):
    sensitivity_levels: int = 8
    sensitivity_first: float = 50.0
    sensitivity_step: float = 50.0
    sensitivity_min: float = 0.1
    sensitivity_max: float = 1.0
    max_distance_km: float = 1000.0
    min_distance_km: float = 10.0
    grid_size_deg: float = 1.0
    lon_range: tuple[float, float] = (-180.0, 180.0)
    lat_range: tuple[float, float] = (-90.0, 90.0)


class SigmaPhiFConfig(BaseModel):
    frequency_pairs: dict[GnssSystem, str] = Field(default_factory=dict)


class S4CConfig(BaseModel):
    n_trend: int = 60
    l_stat: int = 60


class AlgorithmConfig(BaseModel):
    cutoff_elevation_deg: float = 30.0
    min_arc_epochs: int = 10
    roti_window_min: int = 5
    sigma_phi_f_window_min: int = 5
    butterworth_order: int = 6
    butterworth_low_hz: float = 0.001
    butterworth_high_hz: float = 0.015
    force_polynomial_detrend: bool = True
    polynomial_detrend_override: bool = False
    ppp_fallback_strategy: PppFallbackStrategy = PppFallbackStrategy.ALLOW_WARNING
    cycle_slip: CycleSlipConfig = Field(default_factory=CycleSlipConfig)
    dixsg: DixsgConfig = Field(default_factory=DixsgConfig)
    sigma_phi_f: SigmaPhiFConfig = Field(default_factory=SigmaPhiFConfig)
    s4c: S4CConfig = Field(default_factory=S4CConfig)


class TaskConfig(BaseModel):
    project_id: str
    station_ids: list[str]
    date_range: DateRange
    systems: list[GnssSystem]
    metrics: list[MetricKey]
    chain_level: ChainLevel
    sampling_mode: SamplingMode
    output_path: str
    parallelism: int = 1
    enable_intermediate_save: bool = True
    enable_intermediate_preview: bool = True
    enable_nav_fallback: bool = False
    enable_experimental_sigma_phi_f: bool = False
    enable_1s_resample: bool = False
    parameter_source: str = "default"
    threshold_source: str = "default"
    source_template_id: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    receiver_threshold_preset: str | None = None
    threshold_config: list[ThresholdConfig] = Field(default_factory=list)
    algorithm_config: AlgorithmConfig = Field(default_factory=AlgorithmConfig)


class Task(BaseModel):
    id: str
    project_id: str
    name: str
    status: TaskStatus
    task_type: TaskType
    chain_level: ChainLevel
    sampling_mode: SamplingMode
    config: TaskConfig
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    created_from_template_id: str | None = None
    summary: str | None = None
    latest_error: str | None = None
    snapshot_path: str


class SubTask(BaseModel):
    id: str
    task_id: str
    station_id: str
    date: str
    system: GnssSystem
    metric_keys: list[MetricKey]
    status: TaskStatus = TaskStatus.DRAFT
    current_step_key: str | None = None
    duration_ms: int | None = None
    error_message: str | None = None


class ProcessingStep(BaseModel):
    key: str
    label: str
    status: StepStatus
    started_at: str | None = None
    finished_at: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    artifact_paths: list[str] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    id: str
    task_id: str | None = None
    station_id: str | None = None
    metric: MetricKey | None = None
    level: ValidationLevel
    code: str
    message: str
    detail: str | None = None
    blocking: bool = False
    recommendation: str | None = None


class ResultStats(BaseModel):
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    p95: float | None = None
    missing_ratio: float | None = None
    event_count: int | None = None


class ResultSet(BaseModel):
    id: str
    task_id: str
    sub_task_id: str | None = None
    project_id: str
    metric: MetricKey
    station_id: str | None = None
    system: GnssSystem | None = None
    satellite_prn: str | None = None
    satellite_ids: list[str] = Field(default_factory=list)
    chain_level: ChainLevel
    sampling_mode: SamplingMode
    coordinate_source: CoordinateSource | None = None
    receiver_model: str | None = None
    threshold_source: ThresholdSource | None = None
    parameter_source_summary: str
    data_path: str
    preview_image_path: str | None = None
    stats: ResultStats = Field(default_factory=ResultStats)
    created_at: str


class Template(BaseModel):
    id: str
    name: str
    description: str | None = None
    scope: TemplateScope
    is_default: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class TaskProgressEvent(BaseModel):
    task_id: str
    sub_task_id: str | None = None
    status: TaskStatus
    progress: float
    current_station: str | None = None
    current_date: str | None = None
    current_system: GnssSystem | None = None
    current_satellite: str | None = None
    current_step_key: str | None = None


class TaskLogEvent(BaseModel):
    task_id: str
    sub_task_id: str | None = None
    timestamp: str
    level: ApiLogLevel
    step_key: str | None = None
    message: str
    detail: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: str | None = None


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorBody | None = None


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
