from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_STATIONS = ["ALBH", "BAMF", "CHWK", "HOLB", "NANO", "UCLU"]
REGISTRY_RELATIVE_PATH = Path("config") / "datasets" / "regression_datasets.json"


@dataclass(frozen=True)
class RegressionDataset:
    id: str
    dataset_id: str
    label: str
    doy: str
    date: str
    enabled: bool
    manifest: str | None
    stations: list[str]


def _default_dataset(dataset_id: str = "24084") -> RegressionDataset:
    return RegressionDataset(
        id=dataset_id,
        dataset_id=f"matlab_{dataset_id}",
        label=f"MATLAB baseline DOY {dataset_id}",
        doy=dataset_id,
        date="",
        enabled=True,
        manifest=f"config/datasets/matlab_{dataset_id}_manifest.json",
        stations=DEFAULT_STATIONS.copy(),
    )


def load_dataset_registry(project_root: Path) -> list[RegressionDataset]:
    registry_path = (project_root / REGISTRY_RELATIVE_PATH).resolve()
    if not registry_path.exists():
        return [_default_dataset()]

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    rows = payload.get("datasets", [])
    datasets: list[RegressionDataset] = []
    for row in rows:
        raw_id = str(row.get("id") or row.get("doy") or "").strip()
        if not raw_id:
            continue
        stations = [str(x).upper() for x in (row.get("stations") or []) if str(x).strip()]
        datasets.append(
            RegressionDataset(
                id=raw_id,
                dataset_id=str(row.get("datasetId") or f"matlab_{raw_id}"),
                label=str(row.get("label") or f"MATLAB baseline DOY {raw_id}"),
                doy=str(row.get("doy") or raw_id),
                date=str(row.get("date") or ""),
                enabled=bool(row.get("enabled", False)),
                manifest=str(row.get("manifest")) if row.get("manifest") else None,
                stations=stations or DEFAULT_STATIONS.copy(),
            )
        )
    return datasets or [_default_dataset()]


def get_dataset(project_root: Path, dataset_id: str) -> RegressionDataset:
    wanted = str(dataset_id).strip()
    for dataset in load_dataset_registry(project_root):
        if dataset.id == wanted:
            return dataset
    return _default_dataset(wanted)


def enabled_dataset_ids(project_root: Path) -> list[str]:
    return [row.id for row in load_dataset_registry(project_root) if row.enabled]


def resolve_station_list(repo_root: Path, dataset: RegressionDataset) -> list[str]:
    obs_root = repo_root / "raw_OBS_cut" / dataset.doy
    if not obs_root.exists():
        return dataset.stations
    from_files: set[str] = set()
    for path in obs_root.glob("*.mat"):
        stem = path.stem
        if len(stem) >= 4 and stem[:4].isalnum():
            from_files.add(stem[:4].upper())
    if from_files:
        return sorted(from_files)
    return dataset.stations


def report_suffix(dataset: RegressionDataset) -> str:
    return dataset.id

