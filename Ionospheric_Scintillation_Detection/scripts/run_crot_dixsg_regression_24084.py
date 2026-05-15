from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from isd.algorithms.matlab_metrics import (
    compute_dixsg_from_crot_bundles,
    compute_gps_crot_from_obs_cut,
    load_dixsg_from_mat,
    load_gps_crot_from_mat,
)
from regression_dataset import get_dataset, report_suffix, resolve_station_list


def diff_stats(a: np.ndarray, b: np.ndarray) -> dict:
    d = np.abs(a - b)
    finite = np.isfinite(d)
    mae = float(np.nanmean(d)) if finite.any() else None
    max_err = float(np.nanmax(d)) if finite.any() else None
    return {
        "shapeA": list(a.shape),
        "shapeB": list(b.shape),
        "meanAbsError": mae,
        "maxAbsError": max_err,
        "nanRatioA": float(np.isnan(a).mean()),
        "nanRatioB": float(np.isnan(b).mean()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cROT/DIXSG MATLAB regression for one dataset.")
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

    obs_root = repo_root / "raw_OBS_cut" / dataset.doy
    crot_root = repo_root / "ivcROT" / f"GPScROT{dataset.doy}"
    dixsg_path = repo_root / "resDIXSG" / f"GPSDIXSG{dataset.doy}" / f"GPS{dataset.doy}DIXSG.mat"
    if not obs_root.exists() or not crot_root.exists() or not dixsg_path.exists():
        print(f"Regression inputs not found for dataset {dataset_token}.")
        return 1

    report = {
        "dataset": dataset_token,
        "doy": dataset.doy,
        "datasetId": dataset.dataset_id,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "rows": [],
    }

    crot_bundles = {}
    for station in stations:
        obs_cut = obs_root / f"{station}{dataset.doy}.mat"
        crot_gold_path = crot_root / f"{station}{dataset.doy}GPS_B_L_cROT.mat"
        if not obs_cut.exists() or not crot_gold_path.exists():
            continue

        computed = compute_gps_crot_from_obs_cut(obs_cut)
        golden = load_gps_crot_from_mat(crot_gold_path)
        crot_bundles[station] = computed

        row = {
            "station": station,
            "crot": diff_stats(computed.crot, golden.crot),
            "ippB": diff_stats(computed.b, golden.b),
            "ippL": diff_stats(computed.l, golden.l),
        }
        report["rows"].append(row)
        print(station, f"cROT mae={row['crot']['meanAbsError']:.3e}")

    if len(crot_bundles) >= 2:
        computed_dixsg = compute_dixsg_from_crot_bundles(crot_bundles)
        golden_dixsg = load_dixsg_from_mat(dixsg_path)
        report["dixsg"] = {
            "aDIXSG": diff_stats(computed_dixsg.adixsg, golden_dixsg.adixsg),
            "LL": diff_stats(computed_dixsg.ll, golden_dixsg.ll),
        }
        print(f"DIXSG aDIXSG mae={report['dixsg']['aDIXSG']['meanAbsError']:.3e}")

    report_path = out_dir / f"regression_crot_dixsg_{dataset_token}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
