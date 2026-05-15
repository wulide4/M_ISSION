from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

THRESHOLDS = {
    "rotiMae": 1e-10,
    "aatrMae": 1e-10,
    "raatrMae": 1e-10,
    "crotMae": 1e-9,
    "dixsgAdixsgMae": 0.2,
    "dixsgCoverageDelta": 0.05,
    "sigmaphiMae": 1e-12,
    "exportSeriesMae": 1e-12,
    "exportGridMae": 1e-12,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _max_valid(values: list[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return max(valid)


def _report_paths_for_dataset(reports_dir: Path, dataset: str) -> dict[str, Path]:
    suffix = str(dataset).strip()
    return {
        "roti_aatr": reports_dir / f"regression_roti_aatr_{suffix}.json",
        "crot_dixsg": reports_dir / f"regression_crot_dixsg_{suffix}.json",
        "sigmaphi": reports_dir / f"regression_sigmaphi_{suffix}.json",
        "export": reports_dir / f"regression_export_{suffix}.json",
    }


def _evaluate_dataset(reports_dir: Path, dataset: str) -> tuple[dict[str, Any], int]:
    report_paths = _report_paths_for_dataset(reports_dir, dataset)
    missing = [name for name, path in report_paths.items() if not path.exists()]
    if missing:
        summary = {
            "dataset": dataset,
            "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "overallStatus": "FAILED",
            "error": f"Missing required reports: {', '.join(missing)}",
            "reportPaths": {k: str(v) for k, v in report_paths.items()},
            "checks": [],
            "failedChecks": [],
        }
        return summary, 1

    roti = _load_json(report_paths["roti_aatr"])
    crot = _load_json(report_paths["crot_dixsg"])
    sigmaphi = _load_json(report_paths["sigmaphi"])
    export = _load_json(report_paths["export"])

    roti_rows = roti.get("rows", [])
    crot_rows = crot.get("rows", [])
    sig_rows = sigmaphi.get("rows", [])
    exp_rows = export.get("series", [])

    max_roti_mae = _max_valid([_safe_float(r.get("roti", {}).get("meanAbsError")) for r in roti_rows])
    max_aatr_mae = _max_valid([_safe_float(r.get("aatr", {}).get("meanAbsError")) for r in roti_rows])
    max_raatr_mae = _max_valid([_safe_float(r.get("raatr", {}).get("meanAbsError")) for r in roti_rows])
    max_crot_mae = _max_valid([_safe_float(r.get("crot", {}).get("meanAbsError")) for r in crot_rows])
    dixsg_adixsg_mae = _safe_float(crot.get("dixsg", {}).get("aDIXSG", {}).get("meanAbsError"))

    ll = crot.get("dixsg", {}).get("LL", {})
    nan_ratio_a = _safe_float(ll.get("nanRatioA"))
    nan_ratio_b = _safe_float(ll.get("nanRatioB"))
    coverage_delta = None
    if nan_ratio_a is not None and nan_ratio_b is not None:
        coverage_delta = abs((1.0 - nan_ratio_a) - (1.0 - nan_ratio_b))

    max_sigmaphi_mae = _max_valid([_safe_float(r.get("sigmaphiL1", {}).get("meanAbsError")) for r in sig_rows])
    max_export_mat_series = _max_valid([_safe_float(r.get("matMae")) for r in exp_rows])
    max_export_parquet_series = _max_valid([_safe_float(r.get("parquetMae")) for r in exp_rows])
    grid = export.get("grid", {})
    mat_values = _safe_float(grid.get("matValuesMae"))
    mat_grid = _safe_float(grid.get("matGridMae"))
    pq_values = _safe_float(grid.get("parquetValuesMae"))
    pq_grid = _safe_float(grid.get("parquetGridMae"))
    export_violations = export.get("violations", []) or []

    checks = [
        {
            "name": "ROTI_MAE",
            "observed": max_roti_mae,
            "threshold": THRESHOLDS["rotiMae"],
            "status": "PASSED" if (max_roti_mae is not None and max_roti_mae <= THRESHOLDS["rotiMae"]) else "FAILED",
        },
        {
            "name": "AATR_MAE",
            "observed": max_aatr_mae,
            "threshold": THRESHOLDS["aatrMae"],
            "status": "PASSED" if (max_aatr_mae is not None and max_aatr_mae <= THRESHOLDS["aatrMae"]) else "FAILED",
        },
        {
            "name": "RAATR_MAE",
            "observed": max_raatr_mae,
            "threshold": THRESHOLDS["raatrMae"],
            "status": "PASSED" if (max_raatr_mae is not None and max_raatr_mae <= THRESHOLDS["raatrMae"]) else "FAILED",
        },
        {
            "name": "CROT_MAE",
            "observed": max_crot_mae,
            "threshold": THRESHOLDS["crotMae"],
            "status": "PASSED" if (max_crot_mae is not None and max_crot_mae <= THRESHOLDS["crotMae"]) else "FAILED",
        },
        {
            "name": "DIXSG_ADIXSG_MAE",
            "observed": dixsg_adixsg_mae,
            "threshold": THRESHOLDS["dixsgAdixsgMae"],
            "status": (
                "PASSED"
                if (dixsg_adixsg_mae is not None and dixsg_adixsg_mae <= THRESHOLDS["dixsgAdixsgMae"])
                else "FAILED"
            ),
        },
        {
            "name": "DIXSG_COVERAGE_DELTA",
            "observed": coverage_delta,
            "threshold": THRESHOLDS["dixsgCoverageDelta"],
            "status": (
                "PASSED"
                if (coverage_delta is not None and coverage_delta <= THRESHOLDS["dixsgCoverageDelta"])
                else "FAILED"
            ),
        },
        {
            "name": "SIGMAPHI_MAE",
            "observed": max_sigmaphi_mae,
            "threshold": THRESHOLDS["sigmaphiMae"],
            "status": (
                "PASSED"
                if (max_sigmaphi_mae is not None and max_sigmaphi_mae <= THRESHOLDS["sigmaphiMae"])
                else "FAILED"
            ),
        },
        {
            "name": "EXPORT_SERIES_MAT_MAE",
            "observed": max_export_mat_series,
            "threshold": THRESHOLDS["exportSeriesMae"],
            "status": (
                "PASSED"
                if (
                    max_export_mat_series is not None
                    and max_export_mat_series <= THRESHOLDS["exportSeriesMae"]
                )
                else "FAILED"
            ),
        },
        {
            "name": "EXPORT_SERIES_PARQUET_MAE",
            "observed": max_export_parquet_series,
            "threshold": THRESHOLDS["exportSeriesMae"],
            "status": (
                "PASSED"
                if (
                    max_export_parquet_series is not None
                    and max_export_parquet_series <= THRESHOLDS["exportSeriesMae"]
                )
                else "FAILED"
            ),
        },
        {
            "name": "EXPORT_GRID_MAT_VALUES_MAE",
            "observed": mat_values,
            "threshold": THRESHOLDS["exportGridMae"],
            "status": "PASSED" if (mat_values is not None and mat_values <= THRESHOLDS["exportGridMae"]) else "FAILED",
        },
        {
            "name": "EXPORT_GRID_MAT_GRID_MAE",
            "observed": mat_grid,
            "threshold": THRESHOLDS["exportGridMae"],
            "status": "PASSED" if (mat_grid is not None and mat_grid <= THRESHOLDS["exportGridMae"]) else "FAILED",
        },
        {
            "name": "EXPORT_GRID_PARQUET_VALUES_MAE",
            "observed": pq_values,
            "threshold": THRESHOLDS["exportGridMae"],
            "status": "PASSED" if (pq_values is not None and pq_values <= THRESHOLDS["exportGridMae"]) else "FAILED",
        },
        {
            "name": "EXPORT_GRID_PARQUET_GRID_MAE",
            "observed": pq_grid,
            "threshold": THRESHOLDS["exportGridMae"],
            "status": "PASSED" if (pq_grid is not None and pq_grid <= THRESHOLDS["exportGridMae"]) else "FAILED",
        },
        {
            "name": "EXPORT_SCRIPT_VIOLATIONS",
            "observed": len(export_violations),
            "threshold": 0,
            "status": "PASSED" if len(export_violations) == 0 else "FAILED",
        },
    ]

    failed = [c["name"] for c in checks if c["status"] != "PASSED"]
    summary = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "dataset": roti.get("dataset") or crot.get("dataset") or sigmaphi.get("dataset") or export.get("dataset") or dataset,
        "overallStatus": "PASSED" if not failed else "FAILED",
        "failedChecks": failed,
        "exportViolations": export_violations,
        "checks": checks,
        "reportPaths": {k: str(v) for k, v in report_paths.items()},
    }
    return summary, (0 if not failed else 1)


def build_summary(reports_dir: Path, dataset: str = "24084") -> tuple[dict[str, Any], int]:
    return _evaluate_dataset(reports_dir, dataset)


def build_matrix_summary(reports_dir: Path, datasets: list[str]) -> tuple[dict[str, Any], int]:
    if not datasets:
        summary = {
            "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "overallStatus": "FAILED",
            "error": "No datasets specified.",
            "datasets": [],
            "datasetSummaries": [],
            "failedDatasets": [],
        }
        return summary, 1

    dataset_summaries: list[dict[str, Any]] = []
    failed_datasets: list[str] = []
    for dataset in datasets:
        ds_summary, _ = _evaluate_dataset(reports_dir, dataset)
        dataset_summaries.append(ds_summary)
        if ds_summary.get("overallStatus") != "PASSED":
            failed_datasets.append(str(ds_summary.get("dataset") or dataset))

    summary = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "overallStatus": "PASSED" if not failed_datasets else "FAILED",
        "datasets": datasets,
        "failedDatasets": failed_datasets,
        "datasetSummaries": dataset_summaries,
    }
    return summary, (0 if not failed_datasets else 1)


def _parse_dataset_list(raw: str) -> list[str]:
    values = [item.strip() for item in str(raw).split(",")]
    return [item for item in values if item]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Step12 consolidated regression summary.")
    parser.add_argument(
        "--reports-dir",
        default="workspace/reports",
        help="Directory containing regression_*.json reports.",
    )
    parser.add_argument(
        "--dataset",
        default="24084",
        help="Single dataset suffix used in regression report file names.",
    )
    parser.add_argument(
        "--datasets",
        default="",
        help="Comma-separated dataset suffixes for matrix summary, e.g. 24084,24085.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output summary JSON path. If omitted, auto-picks single/matrix default path.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    reports_dir = (project_root / args.reports_dir).resolve()

    dataset_list = _parse_dataset_list(args.datasets)
    if dataset_list:
        summary, code = build_matrix_summary(reports_dir, dataset_list)
        default_output = "workspace/reports/regression_step12_summary_matrix.json"
    else:
        summary, code = build_summary(reports_dir, dataset=args.dataset)
        default_output = f"workspace/reports/regression_step12_summary_{args.dataset}.json"

    output_rel = args.output or default_output
    output = (project_root / output_rel).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Summary: {output}")
    print(f"overallStatus={summary.get('overallStatus')}")
    if summary.get("failedChecks"):
        print("failedChecks:", ",".join(summary["failedChecks"]))
    if summary.get("failedDatasets"):
        print("failedDatasets:", ",".join(summary["failedDatasets"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

