from __future__ import annotations

import sys
from enum import Enum

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    class StrEnum(str, Enum):
        """Backport of StrEnum for Python < 3.11"""
        def __str__(self) -> str:
            return self.value


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
    S4C = "S4C"


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


