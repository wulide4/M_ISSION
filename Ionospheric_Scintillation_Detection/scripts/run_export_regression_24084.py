from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from isd.algorithms.matlab_metrics import compute_gps_metrics_from_obs_cut, load_dixsg_from_mat
from isd.infrastructure.filesystem.result_store import ResultStore
from regression_dataset import get_dataset, report_suffix, resolve_station_list
SERIES_MAE_THRESHOLD = 1e-12
GRID_MAE_THRESHOLD = 1e-12


def mae(a: np.ndarray, b: np.ndarray) -> float:
    diff = np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))
    finite = np.isfinite(diff)
    if not finite.any():
        return 0.0
    return float(np.nanmean(diff))


def finite_values(arr: np.ndarray) -> np.ndarray:
    x = np.asarray(arr, dtype=float).ravel()
    return x[np.isfinite(x)]


def _series_from_frame(frame: pd.DataFrame) -> np.ndarray:
    if "value" in frame.columns:
        return frame["value"].to_numpy(dtype=float)
    value_cols = sorted([c for c in frame.columns if c.startswith("value_")])
    if not value_cols:
        raise ValueError("Parquet series frame has no value columns")
    values = frame[value_cols].to_numpy(dtype=float)
    if values.shape[1] == 1:
        return values[:, 0]
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Run export-format regression for one dataset.")
    parser.add_argument("--dataset", default="24084", help="Dataset id (usually DOY token, e.g. 24084).")
    parser.add_argument("--reports-dir", default="workspace/reports", help="Report output directory.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    dataset = get_dataset(project_root, args.dataset)
    dataset_token = report_suffix(dataset)

    out_dir = (project_root / args.reports_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    export_dir = out_dir / f"regression_export_{dataset_token}"
    export_dir.mkdir(parents=True, exist_ok=True)
    stations = resolve_station_list(repo_root, dataset)

    obs_root = repo_root / "raw_OBS_cut" / dataset.doy
    dixsg_path = repo_root / "resDIXSG" / f"GPSDIXSG{dataset.doy}" / f"GPS{dataset.doy}DIXSG.mat"
    if not obs_root.exists() or not dixsg_path.exists():
        print(f"Regression inputs not found for export regression dataset {dataset_token}.")
        return 1

    store = ResultStore()
    violations: list[str] = []
    report = {
        "dataset": dataset_token,
        "doy": dataset.doy,
        "datasetId": dataset.dataset_id,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "series": [],
        "grid": {},
        "thresholds": {
            "seriesMae": SERIES_MAE_THRESHOLD,
            "gridMae": GRID_MAE_THRESHOLD,
        },
    }

    for station in stations:
        obs_cut = obs_root / f"{station}{dataset.doy}.mat"
        if not obs_cut.exists():
            continue
        bundle = compute_gps_metrics_from_obs_cut(obs_cut)
        src_values = np.asarray(bundle.roti, dtype=float)
        src_time = np.arange(src_values.shape[0], dtype=int)

        src_path = export_dir / f"{station}_ROTI.npz"
        mat_path = export_dir / f"{station}_ROTI.mat"
        parquet_path = export_dir / f"{station}_ROTI.parquet"

        store.save_series(src_path, src_time, src_values)
        store.export(str(src_path), str(mat_path))
        store.export(str(src_path), str(parquet_path))

        mat_payload = store.load(str(mat_path))
        mat_mae = mae(np.asarray(mat_payload["values"]).ravel(), src_values.ravel())

        frame = pd.read_parquet(parquet_path)
        pq_values = _series_from_frame(frame)
        parquet_mae = mae(np.asarray(pq_values).ravel(), src_values.ravel())

        row = {
            "station": station,
            "matMae": mat_mae,
            "parquetMae": parquet_mae,
            "shape": list(src_values.shape),
        }
        report["series"].append(row)
        print(station, f"mat_mae={mat_mae:.3e}", f"parquet_mae={parquet_mae:.3e}")

        if mat_mae > SERIES_MAE_THRESHOLD:
            violations.append(f"{station}:MAT:mae={mat_mae}")
        if parquet_mae > SERIES_MAE_THRESHOLD:
            violations.append(f"{station}:PARQUET:mae={parquet_mae}")

    dixsg = load_dixsg_from_mat(dixsg_path)
    src_payload = {
        "time": np.arange(dixsg.adixsg.shape[0], dtype=int),
        "values": dixsg.adixsg,
        "grid": dixsg.ll,
        "mbl": dixsg.mbl,
    }
    src_path = export_dir / f"GPS{dataset.doy}_DIXSG.npz"
    mat_path = export_dir / f"GPS{dataset.doy}_DIXSG.mat"
    parquet_path = export_dir / f"GPS{dataset.doy}_DIXSG.parquet"

    store.save_payload(src_path, src_payload)
    store.export(str(src_path), str(mat_path))
    store.export(str(src_path), str(parquet_path))

    mat_payload = store.load(str(mat_path))
    values_mae = mae(np.asarray(mat_payload["values"]).ravel(), np.asarray(dixsg.adixsg).ravel())
    grid_mae = mae(np.asarray(mat_payload["grid"]).ravel(), np.asarray(dixsg.ll).ravel())

    pq_frame = pd.read_parquet(parquet_path)
    pq_values = pq_frame["values"].dropna().to_numpy(dtype=float)
    pq_grid = pq_frame["grid"].dropna().to_numpy(dtype=float)
    pq_values_mae = mae(pq_values, finite_values(dixsg.adixsg))
    pq_grid_mae = mae(pq_grid, finite_values(dixsg.ll))

    report["grid"] = {
        "matValuesMae": values_mae,
        "matGridMae": grid_mae,
        "parquetValuesMae": pq_values_mae,
        "parquetGridMae": pq_grid_mae,
        "gridShape": list(np.asarray(dixsg.ll).shape),
    }
    print(
        "DIXSG",
        f"mat_values_mae={values_mae:.3e}",
        f"mat_grid_mae={grid_mae:.3e}",
        f"parquet_values_mae={pq_values_mae:.3e}",
        f"parquet_grid_mae={pq_grid_mae:.3e}",
    )

    if values_mae > GRID_MAE_THRESHOLD:
        violations.append(f"DIXSG:MAT:values:mae={values_mae}")
    if grid_mae > GRID_MAE_THRESHOLD:
        violations.append(f"DIXSG:MAT:grid:mae={grid_mae}")
    if pq_values_mae > GRID_MAE_THRESHOLD:
        violations.append(f"DIXSG:PARQUET:values:mae={pq_values_mae}")
    if pq_grid_mae > GRID_MAE_THRESHOLD:
        violations.append(f"DIXSG:PARQUET:grid:mae={pq_grid_mae}")

    report["violations"] = violations
    report_path = out_dir / f"regression_export_{dataset_token}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")

    if violations:
        print("Export regression failed:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("Export regression passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
