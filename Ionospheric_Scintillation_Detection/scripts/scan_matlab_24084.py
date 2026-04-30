from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from isd.application import channels  # noqa: E402
from isd.application.bootstrap import bootstrap  # noqa: E402


def main() -> int:
    sample_root = PROJECT_ROOT / "workspace" / "samples" / "matlab_24084" / "raw"
    repo_root = PROJECT_ROOT.parent
    if sample_root.exists():
        scan_paths = [sample_root]
    else:
        scan_paths = [
            repo_root / "input_o_and_r file" / "24084",
            repo_root / "input_sp3_file" / "24084",
            repo_root / "input_clk_and_atx_file" / "24084",
        ]

    missing = [path for path in scan_paths if not path.exists()]
    if missing:
        print("Missing input paths:")
        for path in missing:
            print(f"  - {path}")
        return 1

    context = bootstrap(PROJECT_ROOT / "src" / "isd")
    project_name = f"matlab_24084_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    create_rsp = context.command_bus.dispatch(
        channels.PROJECT_CREATE,
        {
            "name": project_name,
            "description": "Step-3 scan for MATLAB aligned sample dataset",
            "rootPath": str(scan_paths[0]),
        },
    )
    if not create_rsp.success:
        print(create_rsp.error.message if create_rsp.error else "project create failed")
        return 1

    project_id = create_rsp.data["id"]
    scan_rsp = context.command_bus.dispatch(
        channels.PROJECT_SCAN_FILES,
        {
            "projectId": project_id,
            "paths": [str(path) for path in scan_paths],
            "metrics": ["SIGMA_PHI_F"],
        },
    )
    if not scan_rsp.success:
        print(scan_rsp.error.message if scan_rsp.error else "scan failed")
        return 1

    files = scan_rsp.data.get("files", [])
    stations = scan_rsp.data.get("stations", [])
    dependency = scan_rsp.data.get("dependencySummary", {})
    file_counts = dict(Counter(row["kind"] for row in files))

    out = {
        "projectId": project_id,
        "scanPaths": [str(path) for path in scan_paths],
        "fileCounts": file_counts,
        "stationCount": len(stations),
        "dependencySummary": dependency,
    }

    out_path = PROJECT_ROOT / "workspace" / "samples" / "matlab_24084" / "scan_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Project: {project_id}")
    print(f"Stations: {len(stations)}")
    print(f"File counts: {file_counts}")
    print(f"Summary: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

