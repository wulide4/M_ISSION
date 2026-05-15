from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from versioning import read_package_version, read_pyproject_version, validate_semver


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    print(">>", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if output.strip():
        print(output)
    return int(proc.returncode), output


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_path(project_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (project_root / path).resolve()


def _copy_if_exists(src: Path, dst: Path, missing: list[str]) -> None:
    if not src.exists():
        missing.append(str(src))
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _build_checks(
    project_root: Path,
    release_snapshot: dict[str, Any] | None,
    step12_matrix: dict[str, Any] | None,
    windows_summary: dict[str, Any] | None,
    mvp_summary: dict[str, Any] | None,
    version_sync_ok: bool,
) -> list[dict[str, Any]]:
    docs_required = [
        project_root / "docs" / "release_notes_v0_1_mvp.md",
        project_root / "docs" / "known_limitations.md",
        project_root / "docs" / "rollback_plan.md",
        project_root / "docs" / "mvp_acceptance_checklist.md",
    ]
    docs_missing = [str(p) for p in docs_required if not p.exists()]

    mvp_exports_exist = True
    export_paths: list[str] = []
    if mvp_summary:
        exports = mvp_summary.get("exports", {})
        for key in ("mat", "parquet", "report"):
            raw = str(exports.get(key, "")).strip()
            if not raw:
                mvp_exports_exist = False
                export_paths.append(raw)
                continue
            path = Path(raw)
            if not path.is_absolute():
                path = (project_root / path).resolve()
            export_paths.append(str(path))
            if not path.exists():
                mvp_exports_exist = False
    else:
        mvp_exports_exist = False

    return [
        {
            "name": "release_freeze_snapshot_passed",
            "status": bool(release_snapshot and release_snapshot.get("overallStatus") == "PASSED"),
            "detail": "workspace/reports/release_freeze_snapshot.json overallStatus == PASSED",
        },
        {
            "name": "step12_matrix_passed",
            "status": bool(step12_matrix and step12_matrix.get("overallStatus") == "PASSED"),
            "detail": "workspace/reports/regression_step12_summary_matrix.json overallStatus == PASSED",
        },
        {
            "name": "windows_release_gate_passed",
            "status": bool(windows_summary and windows_summary.get("overallStatus") == "PASSED"),
            "detail": "workspace/reports/windows_release_gate_summary.json overallStatus == PASSED",
        },
        {
            "name": "mvp_demo_completed",
            "status": bool(mvp_summary and mvp_summary.get("taskStatus") == "COMPLETED"),
            "detail": "workspace/reports/mvp_demo_summary.json taskStatus == COMPLETED",
        },
        {
            "name": "mvp_demo_exports_exist",
            "status": mvp_exports_exist,
            "detail": f"Demo export files exist: {export_paths}",
        },
        {
            "name": "version_sync_passed",
            "status": version_sync_ok,
            "detail": "pyproject.toml version equals src/isd/__init__.py __version__ and semver valid",
        },
        {
            "name": "required_docs_present",
            "status": len(docs_missing) == 0,
            "detail": "Required docs present for freeze: release notes / limitations / rollback / acceptance checklist",
            "missing": docs_missing,
        },
    ]


def _write_signoff_markdown(
    path: Path,
    signed_by: str,
    freeze_id: str,
    version: str,
    checks: list[dict[str, Any]],
    overall_status: str,
) -> None:
    lines = [
        "# ISD MVP Freeze Sign-off",
        "",
        f"- Generated at (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"- Signed by: {signed_by}",
        f"- Freeze id: {freeze_id}",
        f"- Version: {version}",
        f"- Overall status: {overall_status}",
        "",
        "## Acceptance Checks",
    ]
    for row in checks:
        mark = "x" if row.get("status") else " "
        lines.append(f"- [{mark}] {row.get('name')}: {row.get('detail')}")
        missing = row.get("missing", [])
        if missing:
            lines.append(f"  - missing: {', '.join(missing)}")
    lines.append("")
    lines.append("## Manual Confirmation")
    lines.append("- [ ] UI walk-through reviewed")
    lines.append("- [ ] Freeze decision acknowledged by project owner")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run final Step12 acceptance closeout and build freeze archive.")
    parser.add_argument("--project-root", default="", help="Project root path. Defaults to script parent root.")
    parser.add_argument("--project-name", default=f"closeout_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument("--signed-by", default="engineering_auto")
    parser.add_argument(
        "--output",
        default="workspace/reports/step12_closeout_summary.json",
        help="Output JSON path (absolute or relative to project root).",
    )
    parser.add_argument(
        "--freeze-root",
        default="workspace/releases/freeze",
        help="Freeze output directory (absolute or relative to project root).",
    )
    parser.add_argument("--skip-release-freeze", action="store_true")
    parser.add_argument("--skip-version-check", action="store_true")
    args = parser.parse_args()

    project_root = (
        _resolve_path(Path(__file__).resolve().parents[1], args.project_root)
        if args.project_root
        else Path(__file__).resolve().parents[1]
    )
    reports_dir = project_root / "workspace" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    steps: list[dict[str, Any]] = []
    all_steps_ok = True

    if not args.skip_release_freeze:
        code, output = _run(
            [py, "scripts/run_release_freeze.py", "--project-name", args.project_name],
            project_root,
        )
        steps.append(
            {
                "name": "run_release_freeze",
                "status": "PASSED" if code == 0 else "FAILED",
                "exitCode": code,
                "logTail": output[-4000:],
            }
        )
        if code != 0:
            all_steps_ok = False

    if not args.skip_version_check:
        code, output = _run([py, "scripts/check_version_sync.py"], project_root)
        steps.append(
            {
                "name": "check_version_sync",
                "status": "PASSED" if code == 0 else "FAILED",
                "exitCode": code,
                "logTail": output[-2000:],
            }
        )
        if code != 0:
            all_steps_ok = False

    pyproject_version = read_pyproject_version(project_root)
    package_version = read_package_version(project_root)
    version_sync_ok = bool(
        pyproject_version
        and package_version
        and pyproject_version == package_version
        and validate_semver(pyproject_version)
    )
    version = pyproject_version or package_version or "0.0.0"

    release_snapshot = _read_json(reports_dir / "release_freeze_snapshot.json")
    step12_matrix = _read_json(reports_dir / "regression_step12_summary_matrix.json")
    windows_summary = _read_json(reports_dir / "windows_release_gate_summary.json")
    mvp_summary = _read_json(reports_dir / "mvp_demo_summary.json")

    checks = _build_checks(
        project_root=project_root,
        release_snapshot=release_snapshot,
        step12_matrix=step12_matrix,
        windows_summary=windows_summary,
        mvp_summary=mvp_summary,
        version_sync_ok=version_sync_ok,
    )
    checks_ok = all(bool(row.get("status")) for row in checks)
    overall_status = "PASSED" if all_steps_ok and checks_ok else "FAILED"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    freeze_id = f"isd-freeze-v{version}-{stamp}"
    freeze_root = _resolve_path(project_root, args.freeze_root)
    freeze_dir = freeze_root / freeze_id
    freeze_dir.mkdir(parents=True, exist_ok=True)

    signoff_json = reports_dir / "mvp_acceptance_signoff.json"
    signoff_md = reports_dir / "mvp_acceptance_signoff.md"
    signoff_payload = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "signedBy": args.signed_by,
        "freezeId": freeze_id,
        "version": version,
        "overallStatus": overall_status,
        "checks": checks,
    }
    signoff_json.write_text(json.dumps(signoff_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_signoff_markdown(
        path=signoff_md,
        signed_by=args.signed_by,
        freeze_id=freeze_id,
        version=version,
        checks=checks,
        overall_status=overall_status,
    )

    missing_files: list[str] = []
    docs_targets = [
        "docs/release_notes_v0_1_mvp.md",
        "docs/known_limitations.md",
        "docs/rollback_plan.md",
        "docs/mvp_acceptance_checklist.md",
        "docs/next_phase_plan_checklist.md",
        "docs/development_progress.md",
    ]
    report_targets = [
        "workspace/reports/release_freeze_snapshot.json",
        "workspace/reports/regression_step12_summary_matrix.json",
        "workspace/reports/regression_step12_summary_24084.json",
        "workspace/reports/windows_release_gate_summary.json",
        "workspace/reports/mvp_demo_summary.json",
        "workspace/reports/mvp_acceptance_signoff.json",
        "workspace/reports/mvp_acceptance_signoff.md",
    ]

    for rel in docs_targets:
        src = project_root / rel
        dst = freeze_dir / rel
        _copy_if_exists(src, dst, missing_files)
    for rel in report_targets:
        src = project_root / rel
        dst = freeze_dir / rel
        _copy_if_exists(src, dst, missing_files)

    if mvp_summary:
        for key in ("mat", "parquet", "report"):
            raw = str(mvp_summary.get("exports", {}).get(key, "")).strip()
            if not raw:
                missing_files.append(f"mvp_export:{key}:<empty>")
                continue
            src = Path(raw)
            dst = freeze_dir / "workspace" / "reports" / "exports" / src.name
            _copy_if_exists(src, dst, missing_files)

    release_dir = None
    if windows_summary:
        for step in windows_summary.get("steps", []):
            if step.get("name") == "release_layout_check":
                raw = str(step.get("releaseDir", "")).strip()
                if raw:
                    release_dir = Path(raw)
                break
    if release_dir:
        for rel in ("release_manifest.json", "README_WINDOWS_RELEASE.txt"):
            _copy_if_exists(
                release_dir / rel,
                freeze_dir / "workspace" / "releases" / "windows" / release_dir.name / rel,
                missing_files,
            )

    manifest = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "freezeId": freeze_id,
        "version": version,
        "signedBy": args.signed_by,
        "overallStatus": overall_status,
        "checks": checks,
        "steps": steps,
        "missingFiles": missing_files,
    }
    freeze_manifest_path = freeze_dir / "freeze_manifest.json"
    freeze_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    archive_path = shutil.make_archive(str(freeze_dir), "zip", root_dir=str(freeze_dir))

    summary = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "overallStatus": overall_status,
        "freezeId": freeze_id,
        "version": version,
        "signedBy": args.signed_by,
        "checks": checks,
        "steps": steps,
        "paths": {
            "freezeDir": str(freeze_dir),
            "freezeManifest": str(freeze_manifest_path),
            "freezeArchiveZip": str(Path(archive_path)),
            "signoffJson": str(signoff_json),
            "signoffMarkdown": str(signoff_md),
        },
        "missingFiles": missing_files,
    }

    out_path = _resolve_path(project_root, args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Step12 closeout summary: {out_path}")
    print(f"overallStatus={overall_status}")
    return 0 if overall_status == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
