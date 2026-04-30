from __future__ import annotations

import argparse
import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_file(bundle: zipfile.ZipFile, base: Path, file_path: Path) -> None:
    if not file_path.exists() or not file_path.is_file():
        return
    try:
        rel = file_path.relative_to(base)
    except ValueError:
        rel = Path(file_path.name)
    bundle.write(file_path, arcname=str(rel))


def _append_latest(bundle: zipfile.ZipFile, base: Path, folder: Path, pattern: str, limit: int = 20) -> None:
    if not folder.exists():
        return
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    for path in files:
        _append_file(bundle, base, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect ISD diagnostics bundle for troubleshooting.")
    parser.add_argument("--workspace", default="workspace", help="Workspace root path.")
    parser.add_argument(
        "--output",
        default="",
        help="Output zip path. Default: <workspace>/reports/diagnostics_<timestamp>.zip",
    )
    parser.add_argument("--include-db", action="store_true", help="Include workspace database file.")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    reports_dir = workspace / "reports"
    logs_dir = workspace / "logs"
    crash_dir = logs_dir / "crash"
    output = (
        Path(args.output).resolve()
        if args.output
        else reports_dir / f"diagnostics_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "generatedAtUtc": _utc_now(),
        "workspace": str(workspace),
        "pythonVersion": sys.version,
        "platform": platform.platform(),
        "included": [],
    }

    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
        meta_file = reports_dir / "release_freeze_snapshot.json"
        _append_file(bundle, workspace, meta_file)
        if meta_file.exists():
            manifest["included"].append(str(meta_file))

        _append_latest(bundle, workspace, reports_dir, "regression_step12_summary*.json", limit=10)
        _append_latest(bundle, workspace, reports_dir, "p0_gate_summary.json", limit=5)
        _append_latest(bundle, workspace, reports_dir, "mvp_demo_summary.json", limit=5)
        _append_latest(bundle, workspace, logs_dir, "*.log", limit=10)
        _append_latest(bundle, workspace, crash_dir, "*.json", limit=30)
        _append_latest(bundle, workspace, workspace / "runtime", "*.json", limit=10)

        if args.include_db:
            db_file = workspace / "isd.sqlite3"
            _append_file(bundle, workspace, db_file)
            if db_file.exists():
                manifest["included"].append(str(db_file))

        manifest_path = workspace / "temp" / "diagnostics_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        _append_file(bundle, workspace, manifest_path)

    print(f"Diagnostics bundle generated: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

