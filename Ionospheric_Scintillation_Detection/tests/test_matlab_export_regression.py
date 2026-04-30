from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from isd.algorithms.matlab_metrics import compute_gps_metrics_from_obs_cut, load_dixsg_from_mat
from isd.infrastructure.filesystem.result_store import ResultStore


def _mae(a: np.ndarray, b: np.ndarray) -> float:
    d = np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))
    finite = np.isfinite(d)
    if not finite.any():
        return 0.0
    return float(np.nanmean(d))


def _finite_values(arr: np.ndarray) -> np.ndarray:
    x = np.asarray(arr, dtype=float).ravel()
    return x[np.isfinite(x)]


def test_roti_export_mat_and_parquet_regression_24084(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    obs_path = repo_root / "raw_OBS_cut" / "24084" / "ALBH24084.mat"
    if not obs_path.exists():
        pytest.skip("raw_OBS_cut/24084/ALBH24084.mat not found")

    bundle = compute_gps_metrics_from_obs_cut(obs_path)
    values = np.asarray(bundle.roti, dtype=float)
    time = np.arange(values.shape[0], dtype=int)

    store = ResultStore()
    src = tmp_path / "ALBH_ROTI.npz"
    mat = tmp_path / "ALBH_ROTI.mat"
    parquet = tmp_path / "ALBH_ROTI.parquet"

    store.save_series(src, time, values)
    store.export(str(src), str(mat))
    store.export(str(src), str(parquet))

    mat_payload = store.load(str(mat))
    assert _mae(np.asarray(mat_payload["values"]).ravel(), values.ravel()) < 1e-12

    frame = pd.read_parquet(parquet)
    if "value" in frame.columns:
        pq_values = frame["value"].to_numpy(dtype=float)
    else:
        value_cols = sorted([c for c in frame.columns if c.startswith("value_")])
        pq_values = frame[value_cols].to_numpy(dtype=float).ravel()
    assert _mae(pq_values, values.ravel()) < 1e-12


def test_dixsg_export_mat_and_parquet_regression_24084(tmp_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    dixsg_path = repo_root / "resDIXSG" / "GPSDIXSG24084" / "GPS24084DIXSG.mat"
    if not dixsg_path.exists():
        pytest.skip("resDIXSG/GPSDIXSG24084/GPS24084DIXSG.mat not found")

    dixsg = load_dixsg_from_mat(dixsg_path)
    payload = {
        "time": np.arange(dixsg.adixsg.shape[0], dtype=int),
        "values": dixsg.adixsg,
        "grid": dixsg.ll,
        "mbl": dixsg.mbl,
    }

    store = ResultStore()
    src = tmp_path / "GPS24084_DIXSG.npz"
    mat = tmp_path / "GPS24084_DIXSG.mat"
    parquet = tmp_path / "GPS24084_DIXSG.parquet"
    store.save_payload(src, payload)
    store.export(str(src), str(mat))
    store.export(str(src), str(parquet))

    mat_payload = store.load(str(mat))
    assert _mae(np.asarray(mat_payload["values"]).ravel(), np.asarray(dixsg.adixsg).ravel()) < 1e-12
    assert _mae(np.asarray(mat_payload["grid"]).ravel(), np.asarray(dixsg.ll).ravel()) < 1e-12

    frame = pd.read_parquet(parquet)
    pq_values = frame["values"].dropna().to_numpy(dtype=float)
    pq_grid = frame["grid"].dropna().to_numpy(dtype=float)
    assert _mae(pq_values, _finite_values(dixsg.adixsg)) < 1e-12
    assert _mae(pq_grid, _finite_values(dixsg.ll)) < 1e-12
