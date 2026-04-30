from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat

from isd.algorithms.matlab_metrics import compute_gps_metrics_from_obs_cut

STATIONS = ["ALBH", "BAMF", "CHWK", "HOLB", "NANO", "UCLU"]


def _load_single_var(path: Path) -> np.ndarray:
    data = loadmat(path)
    keys = [k for k in data.keys() if not k.startswith("__")]
    if not keys:
        raise ValueError(f"No data variable in {path}")
    return np.asarray(data[keys[0]], dtype=float)


def test_roti_aatr_regression_against_matlab_24084():
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    obs_root = repo_root / "raw_OBS_cut" / "24084"
    if not obs_root.exists():
        pytest.skip("raw_OBS_cut/24084 not found")

    for station in STATIONS:
        obs_path = obs_root / f"{station}24084.mat"
        if not obs_path.exists():
            pytest.skip(f"missing obs cut for station {station}")

        bundle = compute_gps_metrics_from_obs_cut(obs_path)
        roti_gold = _load_single_var(repo_root / "resROTI" / "GPSROTI24084" / f"{station}24084GPSROTI.mat")
        aatr_gold = _load_single_var(repo_root / "resAATR" / "GPSAATR24084" / f"{station}24084GPSAATR.mat")
        raatr_gold = _load_single_var(
            repo_root / "resRMSAATR" / "GPSRMSAATR24084" / f"{station}24084GPSRMSAATR.mat"
        )

        roti_mae = float(np.nanmean(np.abs(bundle.roti - roti_gold)))
        aatr_mae = float(np.nanmean(np.abs(bundle.aatr - aatr_gold)))
        raatr_mae = float(np.nanmean(np.abs(bundle.raatr - raatr_gold)))

        assert bundle.roti.shape == roti_gold.shape
        assert bundle.aatr.shape == aatr_gold.shape
        assert bundle.raatr.shape == raatr_gold.shape
        assert roti_mae < 1e-10
        assert aatr_mae < 1e-10
        assert raatr_mae < 1e-10

