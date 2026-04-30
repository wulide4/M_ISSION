from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from isd.application.ids import make_id
from isd.domain.enums import (
    CoordinateSource,
    FileKind,
    GnssSystem,
    PppStatus,
    ValidationLevel,
    ValidationStatus,
)
from isd.domain.models import DateRange, ProjectFile, Station, ValidationIssue
from isd.infrastructure.filesystem.rinex_parser import RinexParser

_EXT_TO_KIND = {
    '.sp3': FileKind.SP3,
    '.clk': FileKind.CLK,
    '.atx': FileKind.ATX,
    '.nav': FileKind.NAV,
    '.csv': FileKind.SPACE_WEATHER,
    '.txt': FileKind.SPACE_WEATHER,
}


class FileScanner:
    def __init__(self) -> None:
        self.rinex_parser = RinexParser()

    def scan_project(
        self,
        project_id: str,
        root_paths: list[str],
    ) -> tuple[list[ProjectFile], list[Station], list[ValidationIssue]]:
        files: list[ProjectFile] = []
        stations_by_code: dict[str, Station] = {}
        issues: list[ValidationIssue] = []

        for root in [Path(path) for path in root_paths]:
            if not root.exists():
                issues.append(
                    ValidationIssue(
                        id=make_id('issue'),
                        level=ValidationLevel.WARNING,
                        code='SCAN_PATH_MISSING',
                        message=f'Path does not exist: {root}',
                        blocking=False,
                    )
                )
                continue

            for path in root.rglob('*'):
                if not path.is_file():
                    continue
                project_file = self._build_project_file(project_id, path)
                if not project_file:
                    continue

                files.append(project_file)
                if project_file.station_id:
                    self._upsert_station(project_id, project_file, stations_by_code)

        return files, list(stations_by_code.values()), issues

    def _upsert_station(
        self,
        project_id: str,
        project_file: ProjectFile,
        stations_by_code: dict[str, Station],
    ) -> None:
        assert project_file.station_id
        station_code = project_file.station_id
        metadata = project_file.metadata_json or {}
        approx_xyz = metadata.get('approxXYZ') if isinstance(metadata, dict) else None

        if station_code not in stations_by_code:
            latitude = None
            longitude = None
            height = None
            if isinstance(approx_xyz, (list, tuple)) and len(approx_xyz) >= 3:
                try:
                    latitude = float(approx_xyz[0])
                    longitude = float(approx_xyz[1])
                    height = float(approx_xyz[2])
                except (TypeError, ValueError):
                    latitude = None
                    longitude = None
                    height = None

            stations_by_code[station_code] = Station(
                id=f"{project_id}:{station_code}",
                project_id=project_id,
                station_code=station_code,
                latitude=latitude,
                longitude=longitude,
                height=height,
                systems=project_file.systems or [],
                coordinate_source=CoordinateSource.RINEX_APPROX,
                receiver_model=str(metadata.get('receiverModel') or '') or None,
                receiver_manufacturer=str(metadata.get('receiverManufacturer') or '') or None,
                firmware_version=str(metadata.get('firmwareVersion') or '') or None,
                antenna_model=str(metadata.get('antennaModel') or '') or None,
                ppp_status=PppStatus.NOT_STARTED,
                time_coverage=(
                    DateRange(start=project_file.file_date, end=project_file.file_date)
                    if project_file.file_date
                    else None
                ),
            )
            return

        station = stations_by_code[station_code]
        current_systems = {sys.value for sys in station.systems}
        for sys in project_file.systems or []:
            if sys.value not in current_systems:
                station.systems.append(sys)
                current_systems.add(sys.value)

        if project_file.file_date:
            if station.time_coverage is None:
                station.time_coverage = DateRange(start=project_file.file_date, end=project_file.file_date)
            else:
                station.time_coverage.start = min(station.time_coverage.start, project_file.file_date)
                station.time_coverage.end = max(station.time_coverage.end, project_file.file_date)

        if not station.receiver_model:
            station.receiver_model = str(metadata.get('receiverModel') or '') or None
        if not station.receiver_manufacturer:
            station.receiver_manufacturer = str(metadata.get('receiverManufacturer') or '') or None
        if not station.firmware_version:
            station.firmware_version = str(metadata.get('firmwareVersion') or '') or None
        if not station.antenna_model:
            station.antenna_model = str(metadata.get('antennaModel') or '') or None

    def _build_project_file(self, project_id: str, path: Path) -> ProjectFile | None:
        lower_name = path.name.lower()
        suffix = path.suffix.lower()

        kind: FileKind | None = None
        if suffix in {'.rnx', '.obs'} or re.search(r'\.\d{2}o$', lower_name):
            kind = FileKind.OBS
        elif suffix in _EXT_TO_KIND:
            kind = _EXT_TO_KIND[suffix]
        elif 'space_weather' in lower_name:
            kind = FileKind.SPACE_WEATHER

        if not kind:
            return None

        station_id = None
        rinex_version = None
        sampling_interval = None
        systems = None
        metadata: dict[str, object] = {}
        issues: list[str] = []
        validation_status = ValidationStatus.VALID

        if kind == FileKind.OBS:
            header = self.rinex_parser.parse_header(path)
            station_id = header.station_code
            rinex_version = header.rinex_version
            sampling_interval = header.interval_sec
            systems, unsupported_systems = self._normalize_systems(header.systems)
            metadata = {
                'receiverModel': header.receiver_model,
                'receiverManufacturer': header.receiver_manufacturer,
                'firmwareVersion': header.firmware_version,
                'antennaModel': header.antenna_model,
                'approxXYZ': header.approx_xyz,
                'unsupportedSystems': unsupported_systems,
            }
            if not systems:
                issues.append('OBS_SYSTEMS_MISSING')
                validation_status = ValidationStatus.WARNING
            if unsupported_systems:
                issues.append('OBS_UNSUPPORTED_SYSTEMS')
                validation_status = ValidationStatus.WARNING

        return ProjectFile(
            id=make_id('file'),
            project_id=project_id,
            station_id=station_id,
            kind=kind,
            file_path=str(path.resolve()),
            file_name=path.name,
            rinex_version=rinex_version,
            sampling_interval_sec=sampling_interval,
            systems=systems,
            file_date=self._extract_date(path.name),
            matched=False,
            validation_status=validation_status,
            issues=issues,
            metadata_json=metadata,
        )

    def _normalize_systems(
        self,
        systems: list[str] | None,
    ) -> tuple[list[GnssSystem] | None, list[str]]:
        if not systems:
            return None, []

        normalized: list[GnssSystem] = []
        unsupported: list[str] = []
        seen: set[str] = set()
        for raw in systems:
            value = str(raw).strip().upper()
            if not value:
                continue
            try:
                system = GnssSystem(value)
            except ValueError:
                if value not in seen:
                    unsupported.append(value)
                    seen.add(value)
                continue
            if system.value not in seen:
                normalized.append(system)
                seen.add(system.value)
        return (normalized or None), unsupported

    def _extract_date(self, name: str) -> str | None:
        lower_name = name.lower()

        match = re.search(r'(20\d{2})(\d{3})', lower_name)
        if match:
            year = int(match.group(1))
            doy = int(match.group(2))
            return self._from_year_doy(year, doy)

        # RINEX2 classic name: ssssdddf.yy{o|d|n}, e.g. yel20840.24o
        match = re.search(r'^[a-z0-9]{4}(\d{3})0\.(\d{2})[odn](?:\.(?:gz|z))?$', lower_name)
        if match:
            doy = int(match.group(1))
            yy = int(match.group(2))
            year = 2000 + yy
            return self._from_year_doy(year, doy)

        match = re.search(r'(?<!\d)(\d{3})0\.(\d{2})[odn]', lower_name)
        if match:
            doy = int(match.group(1))
            yy = int(match.group(2))
            year = 2000 + yy
            return self._from_year_doy(year, doy)

        match = re.search(r'(?<!\d)(\d{2})(\d{3})(?!\d)', lower_name)
        if match:
            yy = int(match.group(1))
            doy = int(match.group(2))
            year = 2000 + yy
            return self._from_year_doy(year, doy)

        return None

    def _from_year_doy(self, year: int, doy: int) -> str | None:
        if year < 2000 or year > 2099:
            return None
        if doy < 1 or doy > 366:
            return None
        dt = date(year, 1, 1) + timedelta(days=doy - 1)
        return dt.isoformat()
