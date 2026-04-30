from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _prepare_minimal_project(tmp_path: Path, ok: bool = True) -> Path:
    project = tmp_path / "project"
    _write_text(
        project / "pyproject.toml",
        """
[project]
name = "ionospheric_scintillation_detection"
version = "0.1.0"
""".strip(),
    )
    _write_text(project / "src" / "isd" / "__init__.py", '__version__ = "0.1.0"\n')

    for rel in (
        "docs/release_notes_v0_1_mvp.md",
        "docs/known_limitations.md",
        "docs/rollback_plan.md",
        "docs/mvp_acceptance_checklist.md",
        "docs/next_phase_plan_checklist.md",
        "docs/development_progress.md",
    ):
        _write_text(project / rel, "# ok\n")

    reports = project / "workspace" / "reports"
    _write(reports / "release_freeze_snapshot.json", {"overallStatus": "PASSED" if ok else "FAILED"})
    _write(reports / "regression_step12_summary_matrix.json", {"overallStatus": "PASSED" if ok else "FAILED"})
    _write(reports / "regression_step12_summary_24084.json", {"overallStatus": "PASSED" if ok else "FAILED"})

    release_dir = project / "workspace" / "releases" / "windows" / "isd-v0.1.0-test"
    _write_text(release_dir / "release_manifest.json", "{}\n")
    _write_text(release_dir / "README_WINDOWS_RELEASE.txt", "ok\n")
    _write(
        reports / "windows_release_gate_summary.json",
        {
            "overallStatus": "PASSED" if ok else "FAILED",
            "steps": [{"name": "release_layout_check", "releaseDir": str(release_dir)}],
        },
    )

    mat = reports / "demo.mat"
    parquet = reports / "demo.parquet"
    report = reports / "demo.txt"
    _write_text(mat, "mat\n")
    _write_text(parquet, "parquet\n")
    _write_text(report, "report\n")
    _write(
        reports / "mvp_demo_summary.json",
        {
            "taskStatus": "COMPLETED" if ok else "FAILED",
            "exports": {"mat": str(mat), "parquet": str(parquet), "report": str(report)},
        },
    )
    return project


def test_step12_closeout_pass_case(tmp_path: Path):
    project = _prepare_minimal_project(tmp_path, ok=True)
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "run_step12_closeout.py"),
        "--project-root",
        str(project),
        "--skip-release-freeze",
        "--skip-version-check",
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    summary = json.loads((project / "workspace" / "reports" / "step12_closeout_summary.json").read_text(encoding="utf-8"))
    assert summary["overallStatus"] == "PASSED"
    assert Path(summary["paths"]["freezeArchiveZip"]).exists()
    assert (project / "workspace" / "reports" / "mvp_acceptance_signoff.json").exists()


def test_step12_closeout_fail_case(tmp_path: Path):
    project = _prepare_minimal_project(tmp_path, ok=False)
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "run_step12_closeout.py"),
        "--project-root",
        str(project),
        "--skip-release-freeze",
        "--skip-version-check",
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    assert proc.returncode == 1

    summary = json.loads((project / "workspace" / "reports" / "step12_closeout_summary.json").read_text(encoding="utf-8"))
    assert summary["overallStatus"] == "FAILED"

