from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_obs_file(path: Path) -> bool:
    lower = path.name.lower()
    return path.suffix.lower() in {".rnx", ".obs"} or bool(re.search(r"\.\d{2}o$", lower))


def station_from_name(path: Path) -> str | None:
    stem = path.stem
    if len(stem) < 4:
        return None
    code = stem[:4].upper()
    return code if code.isalnum() else None


def collect_entries(category: str, role: str, root: Path, predicate=None) -> list[dict]:
    entries: list[dict] = []
    if not root.exists():
        return entries
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if predicate and not predicate(path):
            continue
        entries.append(
            {
                "category": category,
                "role": role,
                "path": str(path.resolve()),
                "sizeBytes": path.stat().st_size,
                "mtimeUtc": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                "sha256": sha256_file(path),
                "station": station_from_name(path) if category == "input_obs" else None,
            }
        )
    return entries


def infer_date_from_doy_token(doy_token: str) -> str:
    text = str(doy_token).strip()
    if len(text) != 5 or not text.isdigit():
        return ""
    yy = int(text[:2])
    ddd = int(text[2:])
    year = 2000 + yy
    dt = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=ddd - 1)
    return dt.date().isoformat()


def build_manifest(project_root: Path, *, dataset_id: str, doy: str, date_text: str | None = None) -> dict:
    repo_root = project_root.parent
    date_iso = date_text or infer_date_from_doy_token(doy)
    inputs = [
        ("input_obs", "input", repo_root / "input_o_and_r file" / doy, is_obs_file),
        ("input_sp3", "input", repo_root / "input_sp3_file" / doy, lambda p: p.suffix.lower() == ".sp3"),
        ("input_clk", "input", repo_root / "input_clk_and_atx_file" / doy, lambda p: p.suffix.lower() == ".clk"),
        ("input_atx", "input", repo_root / "input_clk_and_atx_file" / doy, lambda p: p.suffix.lower() == ".atx"),
    ]
    goldens = [
        ("golden_roti", "golden_output", repo_root / "resROTI" / f"GPSROTI{doy}"),
        ("golden_aatr", "golden_output", repo_root / "resAATR" / f"GPSAATR{doy}"),
        ("golden_rmsaatr", "golden_output", repo_root / "resRMSAATR" / f"GPSRMSAATR{doy}"),
        ("golden_crot", "golden_output", repo_root / "ivcROT" / f"GPScROT{doy}"),
        ("golden_dixsg", "golden_output", repo_root / "resDIXSG" / f"GPSDIXSG{doy}"),
        ("golden_sigmaphi", "golden_output", repo_root / "resSIGMAPHI" / f"GPSsigmaphi{doy}"),
    ]

    entries: list[dict] = []
    for category, role, root, *predicate in inputs:
        pred = predicate[0] if predicate else None
        entries.extend(collect_entries(category, role, root, pred))
    for category, role, root in goldens:
        entries.extend(collect_entries(category, role, root))

    counts = Counter(entry["category"] for entry in entries)
    stations = sorted({entry["station"] for entry in entries if entry.get("station")})

    return {
        "datasetId": dataset_id,
        "datasetLabel": f"MATLAB sample baseline aligned with DOY {doy}",
        "doy": doy,
        "date": date_iso,
        "status": "ready" if entries else "planned",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "repoRoot": str(repo_root.resolve()),
        "projectRoot": str(project_root.resolve()),
        "stations": stations,
        "counts": dict(counts),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build manifest for MATLAB-aligned sample dataset.")
    parser.add_argument(
        "--dataset-id",
        default="matlab_24084",
        help="Manifest dataset id.",
    )
    parser.add_argument(
        "--doy",
        default="24084",
        help="DOY token used in source folder names, e.g. 24084.",
    )
    parser.add_argument(
        "--date",
        default="",
        help="Absolute date (YYYY-MM-DD). If omitted, inferred from --doy.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output path relative to project root.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    output_rel = args.output or f"config/datasets/{args.dataset_id}_manifest.json"
    output_path = (project_root / output_rel).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(
        project_root,
        dataset_id=str(args.dataset_id),
        doy=str(args.doy),
        date_text=(str(args.date).strip() or None),
    )
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifest written: {output_path}")
    print(f"Entries: {len(manifest['entries'])}, Stations: {len(manifest['stations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
