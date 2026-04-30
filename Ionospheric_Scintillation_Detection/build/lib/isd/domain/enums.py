from __future__ import annotations

from enum import StrEnum


class GnssSystem(StrEnum):
    BDS = "BDS"
    GPS = "GPS"
    GAL = "GAL"
    GLO = "GLO"


class MetricKey(StrEnum):
    ROTI = "ROTI"
    AATR = "AATR"
    IAATR = "IAATR"
    DIXSG = "DIXSG"
    SIGMA_PHI_F = "SIGMA_PHI_F"


class ChainLevel(StrEnum):
    FORMAL = "FORMAL"
    EXPERIMENTAL = "EXPERIMENTAL"
    DEGRADED = "DEGRADED"


class SamplingMode(StrEnum):
    STANDARD_30S = "STANDARD_30S"
    EXPERIMENTAL_1S_RESAMPLED = "EXPERIMENTAL_1S_RESAMPLED"


class CoordinateSource(StrEnum):
    PRECISE_FILE = "PRECISE_FILE"
    PPP = "PPP"
    RINEX_APPROX = "RINEX_APPROX"


class TaskStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    PARTIAL_COMPLETED = "PARTIAL_COMPLETED"
    CANCELLED = "CANCELLED"


class StepStatus(StrEnum):
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class ValidationLevel(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKING = "BLOCKING"


class ThresholdSource(StrEnum):
    MANUAL = "MANUAL"
    TEMPLATE = "TEMPLATE"
    CCDF = "CCDF"
    RECEIVER_PRESET = "RECEIVER_PRESET"
    LITERATURE_REFERENCE = "LITERATURE_REFERENCE"


class FileKind(StrEnum):
    OBS = "OBS"
    SP3 = "SP3"
    CLK = "CLK"
    ATX = "ATX"
    NAV = "NAV"
    SPACE_WEATHER = "SPACE_WEATHER"


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ValidationStatus(StrEnum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"


class EventDetectionSupport(StrEnum):
    STRONG = "STRONG"
    WEAK = "WEAK"
    DISABLED = "DISABLED"


class PppStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class TaskType(StrEnum):
    SINGLE = "SINGLE"
    BATCH = "BATCH"


class TemplateScope(StrEnum):
    TASK = "TASK"
    BATCH = "BATCH"
    REPORT = "REPORT"
    THRESHOLD = "THRESHOLD"


class PppFallbackStrategy(StrEnum):
    ALLOW_WARNING = "ALLOW_WARNING"
    BLOCK_SIGMA_PHI_F = "BLOCK_SIGMA_PHI_F"


class ApiLogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class GlobalAppState(StrEnum):
    BOOTING = "BOOTING"
    READY = "READY"
    PROJECT_OPENED = "PROJECT_OPENED"
    TASK_RUNNING = "TASK_RUNNING"


class ProjectPageState(StrEnum):
    EMPTY = "EMPTY"
    IMPORTING = "IMPORTING"
    SCANNING = "SCANNING"
    VALIDATED = "VALIDATED"
    PARTIAL_WARNING = "PARTIAL_WARNING"
    READY = "READY"


class DataCalcPageState(StrEnum):
    PRISTINE = "PRISTINE"
    DIRTY = "DIRTY"
    VALIDATING = "VALIDATING"
    READY_TO_RUN = "READY_TO_RUN"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class BatchPageState(StrEnum):
    EMPTY_QUEUE = "EMPTY_QUEUE"
    QUEUE_READY = "QUEUE_READY"
    QUEUE_RUNNING = "QUEUE_RUNNING"
    QUEUE_PAUSED = "QUEUE_PAUSED"
    QUEUE_FAILED = "QUEUE_FAILED"
    QUEUE_COMPLETED = "QUEUE_COMPLETED"
    QUEUE_PARTIAL_COMPLETED = "QUEUE_PARTIAL_COMPLETED"


class VisualizationPageState(StrEnum):
    NO_RESULT = "NO_RESULT"
    LOADING_RESULT = "LOADING_RESULT"
    RESULT_READY = "RESULT_READY"
    FILTER_CHANGING = "FILTER_CHANGING"
    EXPORTING = "EXPORTING"
    ERROR = "ERROR"


class ReportPageState(StrEnum):
    NO_SELECTION = "NO_SELECTION"
    TEMPLATE_SELECTED = "TEMPLATE_SELECTED"
    PREVIEW_LOADING = "PREVIEW_LOADING"
    PREVIEW_READY = "PREVIEW_READY"
    EXPORTING = "EXPORTING"
    EXPORT_SUCCESS = "EXPORT_SUCCESS"
    EXPORT_FAILED = "EXPORT_FAILED"
