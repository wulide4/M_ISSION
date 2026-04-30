from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    print(">>", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if output.strip():
        print(output)
    return int(proc.returncode), output


def _latest_release(output_root: Path) -> Path | None:
    if not output_root.exists():
        return None
    dirs = sorted([p for p in output_root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[0] if dirs else None


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    py = sys.executable
    steps: list[dict] = []

    commands = [
        {"name": "version_sync", "cmd": [py, "scripts/check_version_sync.py"]},
        {"name": "windows_release_build", "cmd": [py, "scripts/build_windows_release.py", "--skip-wheel"]},
    ]

    ok = True
    for row in commands:
        code, output = _run(row["cmd"], project_root)
        steps.append({"name": row["name"], "exitCode": code, "status": "PASSED" if code == 0 else "FAILED"})
        if code != 0:
            ok = False
            break

    release_root = project_root / "workspace" / "releases" / "windows"
    latest = _latest_release(release_root)
    required_files = [
        "install_and_launch.bat",
        "launch_isd.bat",
        "upgrade_isd.bat",
        "collect_diagnostics.bat",
        "rollback_workspace.bat",
        "release_manifest.json",
        "requirements-win.txt",
        "tools/collect_diagnostics.py",
        "tools/rollback_workspace.py",
        "tools/check_version_sync.py",
        "tools/versioning.py",
    ]
    missing: list[str] = []
    if latest:
        for rel in required_files:
            if not (latest / rel).exists():
                missing.append(rel)
    else:
        missing = required_files.copy()

    if missing:
        ok = False
    steps.append(
        {
            "name": "release_layout_check",
            "status": "PASSED" if not missing else "FAILED",
            "missingFiles": missing,
            "releaseDir": str(latest) if latest else None,
        }
    )

    summary = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "overallStatus": "PASSED" if ok else "FAILED",
        "steps": steps,
    }
    out = project_root / "workspace" / "reports" / "windows_release_gate_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Summary: {out}")
    print(f"overallStatus={summary['overallStatus']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
