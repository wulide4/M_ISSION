from __future__ import annotations

from dataclasses import dataclass

from isd.domain.enums import CoordinateSource
from isd.domain.models import ProjectFile, Station


@dataclass
class CoordinateProviderStatus:
    provider: str
    coordinate_source: CoordinateSource
    available: bool
    formal_ready: bool
    detail: str = ""


@dataclass
class OrbitClockProviderStatus:
    provider: str
    source: str
    available: bool
    formal_ready: bool
    detail: str = ""


@dataclass
class AntennaProviderStatus:
    provider: str
    source: str
    available: bool
    formal_ready: bool
    detail: str = ""


@dataclass
class PreciseCoordinateProvider:
    def resolve(
        self,
        station: Station,
        date: str,
        project_files: list[ProjectFile],
    ) -> CoordinateProviderStatus:
        return CoordinateProviderStatus(
            provider=self.__class__.__name__,
            coordinate_source=CoordinateSource.RINEX_APPROX,
            available=False,
            formal_ready=False,
            detail="not implemented",
        )


@dataclass
class OrbitClockCorrectionProvider:
    def resolve(
        self,
        date: str,
        project_files: list[ProjectFile],
    ) -> OrbitClockProviderStatus:
        return OrbitClockProviderStatus(
            provider=self.__class__.__name__,
            source="MISSING",
            available=False,
            formal_ready=False,
            detail="not implemented",
        )


@dataclass
class AntennaCorrectionProvider:
    def resolve(
        self,
        station: Station,
        project_files: list[ProjectFile],
    ) -> AntennaProviderStatus:
        return AntennaProviderStatus(
            provider=self.__class__.__name__,
            source="MISSING",
            available=False,
            formal_ready=False,
            detail="not implemented",
        )
