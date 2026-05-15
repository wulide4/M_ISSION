from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    print(">>", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)
    return int(proc.returncode), stdout + ("\n" + stderr if stderr else "")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run release freeze checks and emit snapshot summary.")
    parser.add_argument("--project-name", default=f"freeze_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument(
        "--output",
        default="workspace/reports/release_freeze_snapshot.json",
        help="Output snapshot path relative to project root",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    py = sys.executable
    reports_dir = project_root / "workspace" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    status = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "steps": [],
        "overallStatus": "FAILED",
    }

    commands = [
        {
            "name": "step12_gate",
            "cmd": [py, "scripts/run_step12_gate.py"],
        },
        {
            "name": "windows_release_gate",
            "cmd": [py, "scripts/run_windows_release_gate.py"],
        },
        {
            "name": "mvp_demo",
            "cmd": [py, "scripts/run_mvp_demo.py", "--project-name", args.project_name],
        },
    ]

    all_ok = True
    for row in commands:
        code, log = _run(row["cmd"], project_root)
        step_status = "PASSED" if code == 0 else "FAILED"
        status["steps"].append(
            {
                "name": row["name"],
                "status": step_status,
                "exitCode": code,
                "logTail": (log[-4000:] if log else ""),
            }
        )
        if code != 0:
            all_ok = False
            break

    step12_summary = _read_json(reports_dir / "regression_step12_summary_24084.json")
    step12_matrix = _read_json(reports_dir / "regression_step12_summary_matrix.json")
    mvp_summary = _read_json(reports_dir / "mvp_demo_summary.json")
    status["artifacts"] = {
        "step12Summary": step12_summary,
        "step12MatrixSummary": step12_matrix,
        "windowsReleaseGateSummary": _read_json(reports_dir / "windows_release_gate_summary.json"),
        "mvpDemoSummary": mvp_summary,
    }

    if all_ok and step12_summary and step12_summary.get("overallStatus") == "PASSED" and mvp_summary:
        status["overallStatus"] = "PASSED"
    else:
        status["overallStatus"] = "FAILED"

    out_path = (project_root / args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Freeze snapshot: {out_path}")
    print(f"overallStatus={status['overallStatus']}")
    return 0 if status["overallStatus"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
