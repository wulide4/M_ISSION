from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from isd.algorithms.matlab_metrics import compute_gps_metrics_from_obs_cut
from regression_dataset import get_dataset, report_suffix, resolve_station_list


def load_single_var(path: Path) -> np.ndarray:
    data = loadmat(path)
    keys = [k for k in data.keys() if not k.startswith("__")]
    if not keys:
        raise ValueError(f"No data variable found in {path}")
    return np.asarray(data[keys[0]], dtype=float)


def diff_stats(a: np.ndarray, b: np.ndarray) -> dict:
    d = np.abs(a - b)
    return {
        "shapeA": list(a.shape),
        "shapeB": list(b.shape),
        "meanAbsError": float(np.nanmean(d)),
        "maxAbsError": float(np.nanmax(d)),
        "nanRatioA": float(np.isnan(a).mean()),
        "nanRatioB": float(np.isnan(b).mean()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ROTI/AATR MATLAB regression for one dataset.")
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

    report = {
        "dataset": dataset_token,
        "doy": dataset.doy,
        "datasetId": dataset.dataset_id,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "rows": [],
    }

    for station in stations:
        obs_cut = repo_root / "raw_OBS_cut" / dataset.doy / f"{station}{dataset.doy}.mat"
        if not obs_cut.exists():
            continue
        bundle = compute_gps_metrics_from_obs_cut(obs_cut)

        roti_gold = load_single_var(
            repo_root / "resROTI" / f"GPSROTI{dataset.doy}" / f"{station}{dataset.doy}GPSROTI.mat"
        )
        aatr_gold = load_single_var(
            repo_root / "resAATR" / f"GPSAATR{dataset.doy}" / f"{station}{dataset.doy}GPSAATR.mat"
        )
        raatr_gold = load_single_var(
            repo_root / "resRMSAATR" / f"GPSRMSAATR{dataset.doy}" / f"{station}{dataset.doy}GPSRMSAATR.mat"
        )

        row = {
            "station": station,
            "roti": diff_stats(bundle.roti, roti_gold),
            "aatr": diff_stats(bundle.aatr, aatr_gold),
            "raatr": diff_stats(bundle.raatr, raatr_gold),
        }
        report["rows"].append(row)
        print(
            station,
            f"ROTI mae={row['roti']['meanAbsError']:.3e}",
            f"AATR mae={row['aatr']['meanAbsError']:.3e}",
            f"RAATR mae={row['raatr']['meanAbsError']:.3e}",
        )

    report_path = out_dir / f"regression_roti_aatr_{dataset_token}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")
    if not report["rows"]:
        print("No station rows were generated for this dataset.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
