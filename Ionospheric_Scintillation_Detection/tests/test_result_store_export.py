from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from isd.infrastructure.filesystem.result_store import ResultStore


def test_save_series_writes_npz_and_parquet(tmp_path: Path):
    store = ResultStore()
    path = tmp_path / "results" / "series.npz"
    time = np.arange(5, dtype=int)
    values = np.array([[1.0, 2.0], [2.0, 3.0], [3.0, np.nan], [4.0, 5.0], [5.0, 6.0]])

    saved = store.save_series(path, time, values)

    assert Path(saved).exists()
    parquet_path = path.with_suffix(".parquet")
    assert parquet_path.exists()

    loaded_npz = store.load(saved)
    np.testing.assert_array_equal(loaded_npz["time"], time)
    np.testing.assert_allclose(loaded_npz["values"], values, equal_nan=True)

    frame = pd.read_parquet(parquet_path)
    assert list(frame.columns) == ["time", "value_000", "value_001"]
    assert len(frame) == 5


def test_save_grid_writes_npz_and_parquet(tmp_path: Path):
    store = ResultStore()
    path = tmp_path / "results" / "grid.npz"
    grid = np.arange(12, dtype=float).reshape(3, 4)

    saved = store.save_grid(path, grid)

    assert Path(saved).exists()
    parquet_path = path.with_suffix(".parquet")
    assert parquet_path.exists()

    loaded_npz = store.load(saved)
    np.testing.assert_array_equal(loaded_npz["grid"], grid)

    frame = pd.read_parquet(parquet_path)
    assert list(frame.columns) == ["dim0", "dim1", "value"]
    assert len(frame) == 12


def test_export_npz_to_mat_parquet_and_json(tmp_path: Path):
    store = ResultStore()
    src = tmp_path / "results" / "series.npz"
    time = np.arange(4, dtype=int)
    values = np.array([1.0, 2.0, 3.0, 4.0], dtype=float)
    store.save_series(src, time, values)

    mat_path = tmp_path / "exports" / "series.mat"
    parquet_path = tmp_path / "exports" / "series.parquet"
    json_path = tmp_path / "exports" / "series.json"

    store.export(str(src), str(mat_path))
    store.export(str(src), str(parquet_path))
    store.export(str(src), str(json_path))

    assert mat_path.exists()
    assert parquet_path.exists()
    assert json_path.exists()

    mat_payload = store.load(str(mat_path))
    np.testing.assert_array_equal(mat_payload["time"].ravel(), time)
    np.testing.assert_allclose(mat_payload["values"].ravel(), values, equal_nan=True)

    parquet_payload = store.load(str(parquet_path))
    assert "time" in parquet_payload
    assert "value" in parquet_payload
    np.testing.assert_array_equal(parquet_payload["time"], time)


def test_save_payload_writes_npz_and_parquet(tmp_path: Path):
    store = ResultStore()
    path = tmp_path / "results" / "dixsg_like.npz"
    payload = {
        "time": np.arange(3, dtype=int),
        "values": np.array([0.1, 0.2, 0.3], dtype=float),
        "grid": np.arange(12, dtype=float).reshape(3, 4),
        "mbl": np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float),
    }

    saved = store.save_payload(path, payload)

    assert Path(saved).exists()
    assert path.with_suffix(".parquet").exists()
    loaded_npz = store.load(saved)
    assert set(loaded_npz.keys()) == {"time", "values", "grid", "mbl"}

    frame = pd.read_parquet(path.with_suffix(".parquet"))
    assert "row" in frame.columns
    assert "time" in frame.columns
    assert "grid" in frame.columns
