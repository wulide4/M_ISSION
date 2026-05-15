from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from isd.algorithms.matlab_metrics import (
    compute_dixsg_from_crot_bundles,
    compute_gps_crot_from_obs_cut,
    load_dixsg_from_mat,
    load_gps_crot_from_mat,
)

STATIONS = ["ALBH", "BAMF", "CHWK", "HOLB", "NANO", "UCLU"]


def test_crot_regression_against_matlab_24084():
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    obs_root = repo_root / "raw_OBS_cut" / "24084"
    crot_root = repo_root / "ivcROT" / "GPScROT24084"
    if not obs_root.exists() or not crot_root.exists():
        pytest.skip("raw_OBS_cut/24084 or ivcROT/GPScROT24084 not found")

    for station in STATIONS:
        obs_path = obs_root / f"{station}24084.mat"
        crot_gold_path = crot_root / f"{station}24084GPS_B_L_cROT.mat"
        if not obs_path.exists() or not crot_gold_path.exists():
            pytest.skip(f"missing cROT baseline data for station {station}")

        computed = compute_gps_crot_from_obs_cut(obs_path)
        golden = load_gps_crot_from_mat(crot_gold_path)

        c_mae = float(np.nanmean(np.abs(computed.crot - golden.crot)))
        b_mae = float(np.nanmean(np.abs(computed.b - golden.b)))
        l_mae = float(np.nanmean(np.abs(computed.l - golden.l)))

        assert computed.crot.shape == golden.crot.shape
        assert computed.b.shape == golden.b.shape
        assert computed.l.shape == golden.l.shape
        assert c_mae < 1e-9
        assert b_mae < 1e-12
        assert l_mae < 1e-12


def test_dixsg_regression_against_matlab_24084():
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    obs_root = repo_root / "raw_OBS_cut" / "24084"
    dixsg_gold_path = repo_root / "resDIXSG" / "GPSDIXSG24084" / "GPS24084DIXSG.mat"
    if not obs_root.exists() or not dixsg_gold_path.exists():
        pytest.skip("raw_OBS_cut/24084 or DIXSG baseline not found")

    bundles = {}
    for station in STATIONS:
        obs_path = obs_root / f"{station}24084.mat"
        if not obs_path.exists():
            pytest.skip(f"missing obs cut for station {station}")
        bundles[station] = compute_gps_crot_from_obs_cut(obs_path)

    computed = compute_dixsg_from_crot_bundles(bundles)
    golden = load_dixsg_from_mat(dixsg_gold_path)

    adixsg_mae = float(np.nanmean(np.abs(computed.adixsg - golden.adixsg)))
    coverage_delta = float(abs(np.isfinite(computed.ll).mean() - np.isfinite(golden.ll).mean()))
    computed_hourly_coverage = np.isfinite(computed.ll).reshape(24, -1).mean(axis=1)
    golden_hourly_coverage = np.isfinite(golden.ll).reshape(24, -1).mean(axis=1)
    hourly_coverage_mae = float(np.mean(np.abs(computed_hourly_coverage - golden_hourly_coverage)))

    assert computed.adixsg.shape == golden.adixsg.shape
    assert computed.ll.shape == golden.ll.shape
    assert adixsg_mae < 0.2
    assert coverage_delta < 0.05
    assert hourly_coverage_mae < 0.001
