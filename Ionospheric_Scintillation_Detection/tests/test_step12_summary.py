from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_step12_summary_pass_case(tmp_path: Path):
    reports = tmp_path / "reports"
    _write(
        reports / "regression_roti_aatr_24084.json",
        {
            "dataset": "24084",
            "rows": [
                {"station": "ALBH", "roti": {"meanAbsError": 0.0}, "aatr": {"meanAbsError": 0.0}, "raatr": {"meanAbsError": 0.0}}
            ],
        },
    )
    _write(
        reports / "regression_crot_dixsg_24084.json",
        {
            "dataset": "24084",
            "rows": [{"station": "ALBH", "crot": {"meanAbsError": 0.0}}],
            "dixsg": {"aDIXSG": {"meanAbsError": 0.1}, "LL": {"nanRatioA": 0.99, "nanRatioB": 0.995}},
        },
    )
    _write(
        reports / "regression_sigmaphi_24084.json",
        {
            "dataset": "24084",
            "rows": [{"station": "ALBH", "sigmaphiL1": {"meanAbsError": 0.0}}],
        },
    )
    _write(
        reports / "regression_export_24084.json",
        {
            "dataset": "24084",
            "series": [{"station": "ALBH", "matMae": 0.0, "parquetMae": 0.0}],
            "grid": {
                "matValuesMae": 0.0,
                "matGridMae": 0.0,
                "parquetValuesMae": 0.0,
                "parquetGridMae": 0.0,
            },
            "violations": [],
        },
    )

    project_root = Path(__file__).resolve().parents[1]
    output = tmp_path / "summary.json"
    cmd = [
        sys.executable,
        str(project_root / "scripts" / "build_step12_summary.py"),
        "--reports-dir",
        str(reports),
        "--output",
        str(output),
    ]
    proc = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["overallStatus"] == "PASSED"
    assert summary["failedChecks"] == []


def test_step12_summary_fail_case(tmp_path: Path):
    reports = tmp_path / "reports"
    _write(
        reports / "regression_roti_aatr_24084.json",
        {
            "dataset": "24084",
            "rows": [
                {"station": "ALBH", "roti": {"meanAbsError": 0.0}, "aatr": {"meanAbsError": 0.0}, "raatr": {"meanAbsError": 1.0}}
            ],
        },
    )
    _write(
        reports / "regression_crot_dixsg_24084.json",
        {
            "dataset": "24084",
            "rows": [{"station": "ALBH", "crot": {"meanAbsError": 0.0}}],
            "dixsg": {"aDIXSG": {"meanAbsError": 0.1}, "LL": {"nanRatioA": 0.99, "nanRatioB": 0.995}},
        },
    )
    _write(
        reports / "regression_sigmaphi_24084.json",
        {
            "dataset": "24084",
            "rows": [{"station": "ALBH", "sigmaphiL1": {"meanAbsError": 0.0}}],
        },
    )
    _write(
        reports / "regression_export_24084.json",
        {
            "dataset": "24084",
            "series": [{"station": "ALBH", "matMae": 0.0, "parquetMae": 0.0}],
            "grid": {
                "matValuesMae": 0.0,
                "matGridMae": 0.0,
                "parquetValuesMae": 0.0,
                "parquetGridMae": 0.0,
            },
            "violations": [],
        },
    )

    project_root = Path(__file__).resolve().parents[1]
    output = tmp_path / "summary.json"
    cmd = [
        sys.executable,
        str(project_root / "scripts" / "build_step12_summary.py"),
        "--reports-dir",
        str(reports),
        "--output",
        str(output),
    ]
    proc = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True)
    assert proc.returncode == 1
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["overallStatus"] == "FAILED"
    assert "RAATR_MAE" in summary["failedChecks"]


def test_step12_summary_matrix_case(tmp_path: Path):
    reports = tmp_path / "reports"
    for dataset in ("24084", "24085"):
        _write(
            reports / f"regression_roti_aatr_{dataset}.json",
            {
                "dataset": dataset,
                "rows": [
                    {
                        "station": "ALBH",
                        "roti": {"meanAbsError": 0.0},
                        "aatr": {"meanAbsError": 0.0},
                        "raatr": {"meanAbsError": 0.0},
                    }
                ],
            },
        )
        _write(
            reports / f"regression_crot_dixsg_{dataset}.json",
            {
                "dataset": dataset,
                "rows": [{"station": "ALBH", "crot": {"meanAbsError": 0.0}}],
                "dixsg": {"aDIXSG": {"meanAbsError": 0.1}, "LL": {"nanRatioA": 0.99, "nanRatioB": 0.995}},
            },
        )
        _write(
            reports / f"regression_sigmaphi_{dataset}.json",
            {
                "dataset": dataset,
                "rows": [{"station": "ALBH", "sigmaphiL1": {"meanAbsError": 0.0}}],
            },
        )
        _write(
            reports / f"regression_export_{dataset}.json",
            {
                "dataset": dataset,
                "series": [{"station": "ALBH", "matMae": 0.0, "parquetMae": 0.0}],
                "grid": {
                    "matValuesMae": 0.0,
                    "matGridMae": 0.0,
                    "parquetValuesMae": 0.0,
                    "parquetGridMae": 0.0,
                },
                "violations": [],
            },
        )

    project_root = Path(__file__).resolve().parents[1]
    output = tmp_path / "summary_matrix.json"
    cmd = [
        sys.executable,
        str(project_root / "scripts" / "build_step12_summary.py"),
        "--reports-dir",
        str(reports),
        "--datasets",
        "24084,24085",
        "--output",
        str(output),
    ]
    proc = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["overallStatus"] == "PASSED"
    assert summary["datasets"] == ["24084", "24085"]
    assert len(summary["datasetSummaries"]) == 2
