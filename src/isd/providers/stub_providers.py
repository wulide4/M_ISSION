from __future__ import annotations

from dataclasses import dataclass

from isd.domain.enums import CoordinateSource, FileKind, PppStatus
from isd.domain.models import ProjectFile, Station
from isd.providers.interfaces import (
    AntennaCorrectionProvider,
    AntennaProviderStatus,
    CoordinateProviderStatus,
    OrbitClockCorrectionProvider,
    OrbitClockProviderStatus,
    PreciseCoordinateProvider,
)


def _file_matches_date(row: ProjectFile, date: str) -> bool:
    return (row.file_date is None) or (row.file_date == date)


@dataclass
class BasicPreciseCoordinateProvider(PreciseCoordinateProvider):
    def resolve(
        self,
        station: Station,
        date: str,
        project_files: list[ProjectFile],
    ) -> CoordinateProviderStatus:
        has_obs = any(
            row.kind == FileKind.OBS and row.station_id == station.station_code and _file_matches_date(row, date)
            for row in project_files
        )
        if not has_obs:
            return CoordinateProviderStatus(
                provider=self.__class__.__name__,
                coordinate_source=CoordinateSource.RINEX_APPROX,
                available=False,
                formal_ready=False,
                detail="obs missing for station/date",
            )

        if station.coordinate_source == CoordinateSource.PRECISE_FILE:
            return CoordinateProviderStatus(
                provider=self.__class__.__name__,
                coordinate_source=CoordinateSource.PRECISE_FILE,
                available=True,
                formal_ready=True,
                detail="precise coordinate file metadata",
            )

        if station.coordinate_source == CoordinateSource.RINEX_APPROX:
            return CoordinateProviderStatus(
                provider=self.__class__.__name__,
                coordinate_source=CoordinateSource.RINEX_APPROX,
                available=True,
                formal_ready=False,
                detail="rinex approximate coordinates",
            )

        if station.coordinate_source == CoordinateSource.PPP or station.ppp_status == PppStatus.SUCCESS:
            return CoordinateProviderStatus(
                provider=self.__class__.__name__,
                coordinate_source=CoordinateSource.PPP,
                available=True,
                formal_ready=True,
                detail="ppp solved coordinates",
            )

        return CoordinateProviderStatus(
            provider=self.__class__.__name__,
            coordinate_source=CoordinateSource.RINEX_APPROX,
            available=True,
            formal_ready=False,
            detail="rinex approximate coordinates",
        )


@dataclass
class BasicOrbitClockCorrectionProvider(OrbitClockCorrectionProvider):
    def resolve(
        self,
        date: str,
        project_files: list[ProjectFile],
    ) -> OrbitClockProviderStatus:
        has_sp3 = any(row.kind == FileKind.SP3 and _file_matches_date(row, date) for row in project_files)
        has_clk = any(row.kind == FileKind.CLK and _file_matches_date(row, date) for row in project_files)
        if has_sp3 and has_clk:
            return OrbitClockProviderStatus(
                provider=self.__class__.__name__,
                source="SP3_CLK",
                available=True,
                formal_ready=True,
                detail="both SP3 and CLK available",
            )

        has_nav = any(row.kind == FileKind.NAV and _file_matches_date(row, date) for row in project_files)
        if has_nav:
            return OrbitClockProviderStatus(
                provider=self.__class__.__name__,
                source="NAV_FALLBACK",
                available=True,
                formal_ready=False,
                detail="fall back to NAV broadcast orbit/clock",
            )

        missing = []
        if not has_sp3:
            missing.append("SP3")
        if not has_clk:
            missing.append("CLK")
        return OrbitClockProviderStatus(
            provider=self.__class__.__name__,
            source="MISSING",
            available=False,
            formal_ready=False,
            detail="missing:" + ",".join(missing),
        )


@dataclass
class BasicAntennaCorrectionProvider(AntennaCorrectionProvider):
    def resolve(
        self,
        station: Station,
        project_files: list[ProjectFile],
    ) -> AntennaProviderStatus:
        has_atx = any(row.kind == FileKind.ATX for row in project_files)
        if has_atx:
            return AntennaProviderStatus(
                provider=self.__class__.__name__,
                source="ATX_FILE",
                available=True,
                formal_ready=True,
                detail="global atx file available",
            )

        if station.antenna_calibration_source:
            return AntennaProviderStatus(
                provider=self.__class__.__name__,
                source="STATION_METADATA",
                available=True,
                formal_ready=False,
                detail="using station metadata antenna calibration",
            )

        return AntennaProviderStatus(
            provider=self.__class__.__name__,
            source="MISSING",
            available=False,
            formal_ready=False,
            detail="atx and station metadata missing",
        )
