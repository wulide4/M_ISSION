from __future__ import annotations

import numpy as np


def roti_compute(filtered: np.ndarray, window: int = 10) -> np.ndarray:
    d = np.diff(filtered, prepend=filtered[0])
    out = np.full_like(filtered, np.nan, dtype=float)
    for i in range(window, len(filtered)):
        out[i] = np.std(d[i - window : i])
    return out


def iaatr_compute(filtered: np.ndarray) -> np.ndarray:
    return np.abs(np.diff(filtered, prepend=filtered[0]))


def aatr_aggregate(iaatr: np.ndarray, hourly_size: int = 120) -> np.ndarray:
    blocks = len(iaatr) // hourly_size
    out = np.zeros(blocks)
    for i in range(blocks):
        seg = iaatr[i * hourly_size : (i + 1) * hourly_size]
        out[i] = np.sqrt(np.nanmean(seg**2))
    return out


def moving_window_sigma_phi_f(filtered: np.ndarray, window: int = 10) -> np.ndarray:
    out = np.full_like(filtered, np.nan, dtype=float)
    for i in range(window, len(filtered)):
        out[i] = np.std(filtered[i - window : i], ddof=0)
    return out


def crot_compute(filtered: np.ndarray, geometry: np.ndarray | None = None) -> np.ndarray:
    d = np.abs(np.diff(filtered, prepend=filtered[0]))
    if geometry is None:
        geometry = np.ones_like(d)
    geometry = np.where(geometry == 0, 1.0, geometry)
    return d / geometry


def dixsg_grid(crot: np.ndarray, levels: int = 5, lat_bins: int = 18, lon_bins: int = 36) -> np.ndarray:
    grid = np.zeros((lat_bins, lon_bins), dtype=float)
    if len(crot) == 0:
        return grid
    chunks = np.array_split(crot, lat_bins * lon_bins)
    idx = 0
    for i in range(lat_bins):
        for j in range(lon_bins):
            seg = chunks[idx]
            idx += 1
            if seg.size == 0:
                continue
            grid[i, j] = np.clip(np.nanmean(seg) * levels, 0, 1)
    return grid
