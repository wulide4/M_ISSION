from __future__ import annotations

import argparse
import json
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
    merged = stdout + ("\n" + stderr if stderr else "")
    return int(proc.returncode), merged


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run unified P0 quality gate (pytest + step12 + windows release + mvp demo)."
    )
    parser.add_argument(
        "--project-name",
        default=f"p0_gate_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        help="Project name used by mvp demo step.",
    )
    parser.add_argument(
        "--output",
        default="workspace/reports/p0_gate_summary.json",
        help="Output summary path relative to project root.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    py = sys.executable

    steps = [
        {"name": "pytest", "cmd": [py, "-m", "pytest", "-q"]},
        {"name": "step12_gate", "cmd": [py, "scripts/run_step12_gate.py"]},
        {"name": "windows_release_gate", "cmd": [py, "scripts/run_windows_release_gate.py"]},
        {
            "name": "mvp_demo",
            "cmd": [py, "scripts/run_mvp_demo.py", "--project-name", args.project_name],
        },
    ]

    summary: dict[str, Any] = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "overallStatus": "FAILED",
        "steps": [],
    }

    all_passed = True
    for step in steps:
        code, logs = _run(step["cmd"], project_root)
        step_status = "PASSED" if code == 0 else "FAILED"
        summary["steps"].append(
            {
                "name": step["name"],
                "status": step_status,
                "exitCode": code,
                "logTail": _tail(logs),
            }
        )
        if code != 0:
            all_passed = False
            break

    summary["overallStatus"] = "PASSED" if all_passed else "FAILED"

    out_path = (project_root / args.output).resolve()
    _write_summary(out_path, summary)
    print(f"P0 gate summary: {out_path}")
    print(f"overallStatus={summary['overallStatus']}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
