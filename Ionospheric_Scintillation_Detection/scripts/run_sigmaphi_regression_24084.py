from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from isd.algorithms.matlab_metrics import load_gps_sigmaphi_from_mat
from regression_dataset import get_dataset, report_suffix, resolve_station_list


def diff_stats(a: np.ndarray, b: np.ndarray) -> dict:
    d = np.abs(a - b)
    finite = np.isfinite(d)
    finite_a = np.isfinite(a)
    finite_b = np.isfinite(b)
    return {
        "shapeA": list(a.shape),
        "shapeB": list(b.shape),
        "meanAbsError": float(np.nanmean(d)) if finite.any() else None,
        "maxAbsError": float(np.nanmax(d)) if finite.any() else None,
        "nanRatioA": float(np.isnan(a).mean()),
        "nanRatioB": float(np.isnan(b).mean()),
        "meanA": float(np.nanmean(a)) if finite_a.any() else None,
        "meanB": float(np.nanmean(b)) if finite_b.any() else None,
        "minA": float(np.nanmin(a)) if finite_a.any() else None,
        "maxA": float(np.nanmax(a)) if finite_a.any() else None,
        "minB": float(np.nanmin(b)) if finite_b.any() else None,
        "maxB": float(np.nanmax(b)) if finite_b.any() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SIGMA_PHI_F MATLAB regression for one dataset.")
    parser.add_argument("--dataset", default="24084", help="Dataset id (usually DOY token, e.g. 24084).")
    parser.add_argument("--reports-dir", default="workspace/reports", help="Report output directory.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    dataset = get_dataset(project_root, args.dataset)
    dataset_token = report_suffix(dataset)

    out_dir = (project_root / args.reports_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stations = resolve_station_list(repo_root, dataset)

    sigmaphi_root = repo_root / "resSIGMAPHI" / f"GPSsigmaphi{dataset.doy}"
    if not sigmaphi_root.exists():
        print(f"resSIGMAPHI/GPSsigmaphi{dataset.doy} not found")
        return 1

    report = {
        "dataset": dataset_token,
        "doy": dataset.doy,
        "datasetId": dataset.dataset_id,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "rows": [],
    }

    for station in stations:
        file_path = sigmaphi_root / f"{station.lower()}{dataset.doy}GPSsigmaphi.mat"
        if not file_path.exists():
            continue

        parsed = load_gps_sigmaphi_from_mat(file_path).l1
        if parsed is None:
            continue
        direct = np.asarray(loadmat(file_path, squeeze_me=True, struct_as_record=False)["GPSsigmaphi"].L1, dtype=float)
        row = {
            "station": station,
            "sigmaphiL1": diff_stats(parsed, direct),
        }
        report["rows"].append(row)
        print(station, f"mae={row['sigmaphiL1']['meanAbsError'] or 0.0:.3e}")

    report_path = out_dir / f"regression_sigmaphi_{dataset_token}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
