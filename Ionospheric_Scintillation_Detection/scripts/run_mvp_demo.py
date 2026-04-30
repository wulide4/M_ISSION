from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from isd.application import channels
from isd.application.bootstrap import bootstrap

TERMINAL_STATUS = {"COMPLETED", "FAILED", "CANCELLED", "PARTIAL_COMPLETED"}


def _detect_scan_paths(project_root: Path) -> list[Path]:
    sample_root = project_root / "workspace" / "samples" / "matlab_24084" / "raw"
    if sample_root.exists():
        return [sample_root]

    repo_root = project_root.parent
    paths = [
        repo_root / "input_o_and_r file" / "24084",
        repo_root / "input_sp3_file" / "24084",
        repo_root / "input_clk_and_atx_file" / "24084",
    ]
    return [p for p in paths if p.exists()]


def _pick_date(scan_data: dict) -> str:
    files = scan_data.get("files") or []
    obs_dates = sorted(
        {
            f.get("file_date")
            for f in files
            if f.get("file_date") and str(f.get("kind", "")).upper() == "OBS"
        }
    )
    if obs_dates:
        return obs_dates[0]
    dep = scan_data.get("dependencySummary") or {}
    if dep:
        return sorted(dep.keys())[0]
    dates = sorted({f.get("file_date") for f in files if f.get("file_date")})
    return dates[0] if dates else "2024-03-24"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local MVP end-to-end demo pipeline.")
    parser.add_argument("--project-name", default=f"mvp_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    context = bootstrap(project_root / "src" / "isd")
    scan_paths = _detect_scan_paths(project_root)
    if not scan_paths:
        print("No scan input paths found for MVP demo.")
        return 1

    create_rsp = context.command_bus.dispatch(
        channels.PROJECT_CREATE,
        {"name": args.project_name, "description": "MVP demo run", "rootPath": str(scan_paths[0])},
    )
    if not create_rsp.success:
        print(create_rsp.error.message if create_rsp.error else "project:create failed")
        return 1
    project_id = create_rsp.data["id"]

    scan_rsp = context.command_bus.dispatch(
        channels.PROJECT_SCAN_FILES,
        {
            "projectId": project_id,
            "paths": [str(p) for p in scan_paths],
            "metrics": ["ROTI"],
        },
    )
    if not scan_rsp.success:
        print(scan_rsp.error.message if scan_rsp.error else "project:scanFiles failed")
        return 1
    scan_data = scan_rsp.data or {}

    stations = sorted({row.get("station_code") for row in scan_data.get("stations", []) if row.get("station_code")})
    if not stations:
        print("No stations found after scan.")
        return 1
    run_stations = stations[: min(6, len(stations))]
    run_date = _pick_date(scan_data)

    task_config = {
        "project_id": project_id,
        "station_ids": run_stations,
        "date_range": {"start": run_date, "end": run_date},
        "systems": ["GPS"],
        "metrics": ["ROTI"],
        "chain_level": "FORMAL",
        "sampling_mode": "STANDARD_30S",
        "output_path": str(project_root / "workspace" / "outputs"),
        "parallelism": 1,
        "enable_intermediate_save": True,
        "enable_intermediate_preview": True,
        "enable_nav_fallback": False,
        "enable_experimental_sigma_phi_f": False,
        "enable_1s_resample": False,
        "threshold_config": [],
        "algorithm_config": {},
    }

    validate_rsp = context.command_bus.dispatch(channels.TASK_VALIDATE, {"config": task_config})
    if not validate_rsp.success or not validate_rsp.data.get("canRun"):
        issues = (validate_rsp.data or {}).get("issues", []) if validate_rsp.success else []
        print("task:validate failed", issues)
        return 1

    create_task_rsp = context.command_bus.dispatch(
        channels.TASK_CREATE,
        {"name": "mvp_demo_task", "taskType": "SINGLE", "config": task_config},
    )
    if not create_task_rsp.success:
        print(create_task_rsp.error.message if create_task_rsp.error else "task:create failed")
        return 1
    task_id = create_task_rsp.data["task"]["id"]

    start_rsp = context.command_bus.dispatch(channels.TASK_START, {"taskId": task_id})
    if not start_rsp.success:
        print(start_rsp.error.message if start_rsp.error else "task:start failed")
        return 1

    deadline = time.time() + args.timeout_sec
    task_status = "RUNNING"
    while time.time() < deadline:
        get_rsp = context.command_bus.dispatch(channels.TASK_GET, {"taskId": task_id})
        if get_rsp.success:
            task_status = get_rsp.data["task"]["status"]
            if task_status in TERMINAL_STATUS:
                break
        time.sleep(0.5)
    if task_status != "COMPLETED":
        print("Task did not complete successfully:", task_status)
        return 1

    results_rsp = context.command_bus.dispatch(channels.RESULT_LIST, {"projectId": project_id, "taskId": task_id})
    if not results_rsp.success or not results_rsp.data:
        print("No results generated.")
        return 1
    results = results_rsp.data

    first_result = results[0]
    export_dir = project_root / "workspace" / "reports"
    export_dir.mkdir(parents=True, exist_ok=True)
    mat_path = export_dir / f"mvp_demo_{task_id}_first.mat"
    parquet_path = export_dir / f"mvp_demo_{task_id}_first.parquet"

    for path in (mat_path, parquet_path):
        export_rsp = context.command_bus.dispatch(
            channels.RESULT_EXPORT,
            {"projectId": project_id, "resultId": first_result["id"], "outputPath": str(path)},
        )
        if not export_rsp.success:
            print(export_rsp.error.message if export_rsp.error else f"result:export failed for {path}")
            return 1

    used_ids = [row["id"] for row in results[: min(8, len(results))]]
    report_path = export_dir / f"mvp_demo_{task_id}_report.txt"
    report_rsp = context.command_bus.dispatch(
        channels.REPORT_EXPORT,
        {
            "projectId": project_id,
            "templateId": "default_template",
            "resultIds": used_ids,
            "options": {"title": "MVP Demo Report", "includeParameterSnapshot": True, "includeLogSummary": True},
            "outputPath": str(report_path),
        },
    )
    if not report_rsp.success:
        print(report_rsp.error.message if report_rsp.error else "report:export failed")
        return 1

    summary = {
        "projectId": project_id,
        "taskId": task_id,
        "taskStatus": task_status,
        "stationCount": len(run_stations),
        "runDate": run_date,
        "resultCount": len(results),
        "firstResultId": first_result["id"],
        "exports": {"mat": str(mat_path), "parquet": str(parquet_path), "report": str(report_path)},
        "riskFlags": validate_rsp.data.get("riskFlags", []),
    }
    summary_path = export_dir / "mvp_demo_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
