from pathlib import Path

from isd.domain.enums import GnssSystem, ValidationStatus
from isd.infrastructure.filesystem.file_scan import FileScanner
from isd.infrastructure.filesystem.rinex_parser import RinexParser


def test_rinex_parser_header(tmp_path: Path):
    content = """     3.03           OBSERVATION DATA    M (MIXED)           RINEX VERSION / TYPE\nABCD                                                    MARKER NAME\n   4321234.0000   1234567.0000   4321000.0000          APPROX POSITION XYZ\n    30                                                  INTERVAL\nG   12 C1C L1C C2W L2W                                  SYS / # / OBS TYPES\n                                                            END OF HEADER\n"""
    f = tmp_path / "abcd0010.24o"
    f.write_text(content, encoding="utf-8")

    hdr = RinexParser().parse_header(f)
    assert hdr.station_code == "ABCD"
    assert hdr.interval_sec == 30
    assert "GPS" in (hdr.systems or [])


def test_file_scanner_ignores_unsupported_systems(tmp_path: Path):
    content = """     3.03           OBSERVATION DATA    M (MIXED)           RINEX VERSION / TYPE\nABCD                                                    MARKER NAME\n   4321234.0000   1234567.0000   4321000.0000          APPROX POSITION XYZ\n    30                                                  INTERVAL\nG   12 C1C L1C C2W L2W                                  SYS / # / OBS TYPES\nS   06 C1C L1C                                          SYS / # / OBS TYPES\n                                                            END OF HEADER\n"""
    f = tmp_path / "abcd0840.24o"
    f.write_text(content, encoding="utf-8")

    scanner = FileScanner()
    files, stations, issues = scanner.scan_project("proj_x", [str(tmp_path)])

    assert not issues
    assert len(files) == 1
    file_row = files[0]
    assert file_row.validation_status == ValidationStatus.WARNING
    assert "OBS_UNSUPPORTED_SYSTEMS" in file_row.issues
    assert file_row.metadata_json is not None
    assert file_row.metadata_json.get("unsupportedSystems") == ["SBAS"]
    assert file_row.systems == [GnssSystem.GPS]

    assert len(stations) == 1
    assert stations[0].systems == [GnssSystem.GPS]


def test_file_scanner_extracts_date_for_station_code_with_digit(tmp_path: Path):
    content = """     3.03           OBSERVATION DATA    M (MIXED)           RINEX VERSION / TYPE\nYEL2                                                    MARKER NAME\n   4321234.0000   1234567.0000   4321000.0000          APPROX POSITION XYZ\n    30                                                  INTERVAL\nG   12 C1C L1C C2W L2W                                  SYS / # / OBS TYPES\n                                                            END OF HEADER\n"""
    f = tmp_path / "yel20840.24o"
    f.write_text(content, encoding="utf-8")

    scanner = FileScanner()
    files, stations, issues = scanner.scan_project("proj_yel2", [str(tmp_path)])

    assert not issues
    assert len(files) == 1
    assert files[0].station_id == "YEL2"
    assert files[0].file_date == "2024-03-24"
    assert len(stations) == 1
    assert stations[0].station_code == "YEL2"
