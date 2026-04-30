from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PreprocessArtifacts:
    gf: np.ndarray
    hmw: np.ndarray
    cycle_slip_points: np.ndarray
    detrended_geodetic: np.ndarray
    detrended_poly: np.ndarray
    filtered: np.ndarray


def short_arc_removal(series: np.ndarray, min_arc: int = 10) -> np.ndarray:
    out = series.copy()
    valid = ~np.isnan(out)
    n = len(out)
    i = 0
    while i < n:
        if not valid[i]:
            i += 1
            continue
        j = i
        while j < n and valid[j]:
            j += 1
        if (j - i) < min_arc:
            out[i:j] = np.nan
        i = j
    return out


def cycle_slip_detection(gf: np.ndarray, threshold: float = 2.5) -> np.ndarray:
    diff = np.abs(np.diff(np.nan_to_num(gf, nan=0.0), prepend=0.0))
    return np.where(diff > threshold)[0]


def cycle_slip_repair(series: np.ndarray, slips: np.ndarray) -> np.ndarray:
    out = series.copy()
    for idx in slips:
        out[idx:] = out[idx:] - (out[idx] - out[idx - 1] if idx > 0 else 0)
    return out


def geodetic_detrending(series: np.ndarray) -> np.ndarray:
    x = np.arange(len(series))
    y = np.nan_to_num(series, nan=np.nanmean(series))
    coef = np.polyfit(x, y, 1)
    return y - np.polyval(coef, x)


def polynomial_detrending(series: np.ndarray) -> np.ndarray:
    x = np.arange(len(series))
    y = np.nan_to_num(series, nan=np.nanmean(series))
    coef = np.polyfit(x, y, 3)
    return y - np.polyval(coef, x)


def butterworth_filter(series: np.ndarray) -> np.ndarray:
    kernel = np.ones(7) / 7
    return np.convolve(np.nan_to_num(series, nan=0.0), kernel, mode="same")


def preprocess_chain(signal: np.ndarray, min_arc: int = 10) -> PreprocessArtifacts:
    gf = short_arc_removal(signal, min_arc=min_arc)
    hmw = short_arc_removal(signal * 0.8, min_arc=min_arc)
    slips = cycle_slip_detection(gf)
    repaired = cycle_slip_repair(gf, slips)
    geo = geodetic_detrending(repaired)
    poly = polynomial_detrending(geo)
    filt = butterworth_filter(poly)
    return PreprocessArtifacts(
        gf=gf,
        hmw=hmw,
        cycle_slip_points=slips,
        detrended_geodetic=geo,
        detrended_poly=poly,
        filtered=filt,
    )
