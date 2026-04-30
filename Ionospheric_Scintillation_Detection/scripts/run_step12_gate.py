from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from regression_dataset import enabled_dataset_ids


def run(cmd: list[str], cwd: Path) -> int:
    print(">>", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd))
    return int(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Step12 gate with multi-dataset regression support.")
    parser.add_argument(
        "--datasets",
        default="",
        help="Comma-separated dataset ids. If omitted, use enabled datasets from config/datasets/regression_datasets.json.",
    )
    parser.add_argument(
        "--reports-dir",
        default="workspace/reports",
        help="Directory for regression reports.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    py = sys.executable

    datasets = [x.strip() for x in args.datasets.split(",") if x.strip()]
    if not datasets:
        datasets = enabled_dataset_ids(project_root)
    if not datasets:
        datasets = ["24084"]

    commands: list[list[str]] = [[py, "-m", "pytest", "-q"]]
    for dataset in datasets:
        commands.extend(
            [
                [py, "scripts/run_roti_aatr_regression_24084.py", "--dataset", dataset, "--reports-dir", args.reports_dir],
                [py, "scripts/run_crot_dixsg_regression_24084.py", "--dataset", dataset, "--reports-dir", args.reports_dir],
                [py, "scripts/run_sigmaphi_regression_24084.py", "--dataset", dataset, "--reports-dir", args.reports_dir],
                [py, "scripts/run_export_regression_24084.py", "--dataset", dataset, "--reports-dir", args.reports_dir],
                [
                    py,
                    "scripts/build_step12_summary.py",
                    "--dataset",
                    dataset,
                    "--reports-dir",
                    args.reports_dir,
                    "--output",
                    f"{args.reports_dir}/regression_step12_summary_{dataset}.json",
                ],
            ]
        )

    commands.append(
        [
            py,
            "scripts/build_step12_summary.py",
            "--datasets",
            ",".join(datasets),
            "--reports-dir",
            args.reports_dir,
            "--output",
            f"{args.reports_dir}/regression_step12_summary_matrix.json",
        ]
    )

    for cmd in commands:
        code = run(cmd, project_root)
        if code != 0:
            print(f"Step12 gate failed at: {' '.join(cmd)}")
            return code

    print("Step12 gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
