from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from isd.domain.enums import FileKind
from isd.infrastructure.filesystem.file_scan import FileScanner
from isd.infrastructure.filesystem.product_match import ProductMatcher


def test_input_chain_24084_scan_and_match():
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent

    obs_root = repo_root / "input_o_and_r file" / "24084"
    sp3_root = repo_root / "input_sp3_file" / "24084"
    clk_atx_root = repo_root / "input_clk_and_atx_file" / "24084"
    required = [obs_root, sp3_root, clk_atx_root]
    if not all(path.exists() for path in required):
        pytest.skip("MATLAB sample input directories are not available in this environment.")

    scanner = FileScanner()
    files, stations, issues = scanner.scan_project(
        project_id="proj_24084",
        root_paths=[str(obs_root), str(sp3_root), str(clk_atx_root)],
    )

    assert not issues
    counts = Counter(row.kind.value for row in files)
    assert counts[FileKind.OBS.value] >= 6
    assert counts[FileKind.SP3.value] >= 3
    assert counts[FileKind.CLK.value] >= 1
    assert counts[FileKind.ATX.value] >= 1

    station_codes = {station.station_code for station in stations}
    for expected in {"ALBH", "BAMF", "CHWK", "HOLB", "NANO", "UCLU"}:
        assert expected in station_codes

    matcher = ProductMatcher()
    matcher.assign_match_flags(files)
    dependency = matcher.resolve(files, ["SIGMA_PHI_F"])
    assert "2024-03-24" in dependency
    day = dependency["2024-03-24"]
    assert day["SP3"] == "matched"
    assert day["CLK"] == "matched"
    assert day["ATX"] == "matched"
    assert day["chainLevel"] == "FORMAL"

