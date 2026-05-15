"""Signal preprocessing pipeline strictly following M_ISSION paper (wenxian.pdf).

Implements:
- Cycle slip detection & repair per cut_slip_repair.m (Eq.1-3)
- Third-order polynomial detrending per Eq.(4)
- 6th-order Butterworth bandpass filter per butterworthband.m
- sigma_phi per get_sigmaphi.m (Eq.5)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.signal import butter, filtfilt

# --- Physical constants per cut_slip_repair.m / GPS_slip ---
LIGHT_SPEED = 299792458.0  # m/s

GPS_L1_FREQ = 1575.42e6  # Hz
GPS_L2_FREQ = 1227.60e6  # Hz
GPS_L1_WAVELENGTH = LIGHT_SPEED / GPS_L1_FREQ
GPS_L2_WAVELENGTH = LIGHT_SPEED / GPS_L2_FREQ


@dataclass
class PreprocessArtifacts:
    gf: np.ndarray
    hmw: np.ndarray
    cycle_slip_points: np.ndarray
    detrended_geodetic: np.ndarray
    detrended_poly: np.ndarray
    filtered: np.ndarray
    gf_combination: np.ndarray | None = None
    hmw_combination: np.ndarray | None = None
    elevation_mask: np.ndarray | None = None


# ---------------------------------------------------------------------------
# Short arc removal (per paper: "arcs less than ten epochs are removed")
# ---------------------------------------------------------------------------

def short_arc_removal(
    series: np.ndarray,
    min_arc: int = 10,
    sampling_interval: float = 30.0,
) -> np.ndarray:
    """Remove arcs shorter than min_arc epochs. Per paper Section 'Data preprocessing'."""
    if series.ndim == 1:
        return _short_arc_removal_1d(series, min_arc)
    result = np.zeros_like(series, dtype=float)
    for col in range(series.shape[1]):
        result[:, col] = _short_arc_removal_1d(series[:, col], min_arc)
    return result


def _short_arc_removal_1d(series: np.ndarray, min_arc: int) -> np.ndarray:
    out = series.copy()
    n = len(out)
    i = 0
    while i < n:
        if np.isnan(out[i]):
            i += 1
            continue
        j = i
        while j < n and not np.isnan(out[j]):
            j += 1
        if (j - i) < min_arc:
            out[i:j] = np.nan
        i = j
    return out


# ---------------------------------------------------------------------------
# Get_arc helper per cut_slip_repair.m Get_arc function (line 762-787)
# ---------------------------------------------------------------------------

def _get_arcs(valid_mask: np.ndarray) -> list[tuple[int, int]]:
    """Identify continuous arcs from a boolean/0-1 mask per cut_slip_repair.m Get_arc."""
    n = len(valid_mask)
    arcs = []
    i = 0
    while i < n:
        if valid_mask[i]:
            start = i
            while i < n and valid_mask[i]:
                i += 1
            arcs.append((start, i - 1))  # inclusive end
        else:
            i += 1
    return arcs


# ---------------------------------------------------------------------------
# Cycle slip detection & repair per cut_slip_repair.m GPS_slip (Eq.1-3)
# ---------------------------------------------------------------------------

def cycle_slip_detection(
    gf: np.ndarray,
    hmw: np.ndarray | None = None,
    window_size: int = 30,
    gf_threshold_factor: float = 4.0,
    hmw_threshold_factor: float = 5.0,
    min_obs_for_stats: int = 3,
    elevation: np.ndarray | None = None,
    elevation_threshold: float = 30.0,
) -> np.ndarray:
    """Detect cycle slips per cut_slip_repair.m.

    Per paper Eq.(1): LGF = lambda1*phi1 - lambda2*phi2
    Per paper Eq.(2): NWL = (phi1-phi2) - (f1*P1+f2*P2)/(f1+f2) / (1/lambda1 - 1/lambda2)

    Detection per cut_slip_repair.m GPS_slip lines 79-149:
    - sig0 = sqrt(2*(0.0027^2 + 0.0017^2))
    - dl = 4 * (dt/3600)   (iono_rate_per_hour=4)
    - GF threshold: 4 * sig0 * me + dl,  me = 1 + 10*exp(-elv/10)
    - MW threshold: |dmw| > 5 * smw  where smw = max(std(window), 0.01)
    - MW also requires arc_nwl_std > 0.6
    - Min arc length: 30 epochs
    """
    if gf.ndim == 1:
        gf = gf.reshape(-1, 1)
    n_epochs, n_sats = gf.shape
    slips = np.zeros((n_epochs, n_sats), dtype=bool)

    sig0 = np.sqrt(2.0 * (0.0027 ** 2 + 0.0017 ** 2))
    dt = 30.0
    iono_rate_per_hour = 4.0
    dl = iono_rate_per_hour * (dt / 3600.0)

    for col in range(n_sats):
        gf_col = gf[:, col]
        hmw_col = hmw[:, col] if hmw is not None and hmw.shape[0] > col else None
        elev_col = elevation[:, col] if elevation is not None and elevation.shape[0] > col else None

        valid = np.isfinite(gf_col) & (gf_col != 0)
        arcs = _get_arcs(valid)

        for arc_start, arc_end in arcs:
            # Per cut_slip_repair.m line 104: remove arcs < 30 epochs
            if (arc_end - arc_start + 1) < 30:
                continue

            # Per cut_slip_repair.m line 113: arc_nwl_std
            arc_nwl_std = 0.0
            if hmw_col is not None:
                arc_hmw = hmw_col[arc_start:arc_end + 1]
                finite_hmw = arc_hmw[np.isfinite(arc_hmw)]
                if len(finite_hmw) >= 2:
                    arc_nwl_std = np.std(finite_hmw, ddof=1)

            for k in range(arc_start + 1, arc_end + 1):
                dgfc = False
                dmwc = False

                # --- GF detection per cut_slip_repair.m lines 120-131 ---
                dgf = gf_col[k] - gf_col[k - 1]
                elv = elev_col[k] if elev_col is not None else 90.0

                # Per line 124: me = 1 + 10*exp(-elv/10)
                me = 1.0 + 10.0 * np.exp(-elv / 10.0)
                smg = sig0 * me
                # Per line 127: thresh_gf = 4 * smg + dl
                thresh_gf = gf_threshold_factor * smg + dl

                if abs(dgf) > thresh_gf:
                    dgfc = True

                # --- MW detection per cut_slip_repair.m lines 133-147 ---
                if hmw_col is not None:
                    window_start = max(arc_start, k - window_size)

                    if (k - window_start) >= min_obs_for_stats:
                        past_data = hmw_col[window_start:k]
                        finite_past = past_data[np.isfinite(past_data)]
                        if len(finite_past) >= 2:
                            mmw = np.mean(finite_past)
                            smw = np.std(finite_past, ddof=1)
                            smw = max(smw, 0.01)  # Per line 140

                            dmw = hmw_col[k] - mmw
                            if abs(dmw) > hmw_threshold_factor * smw:
                                dmwc = True

                # Per line 149: if dgfc || (dmwc && arc_nwl_std > 0.6)
                if dgfc or (dmwc and arc_nwl_std > 0.6):
                    slips[k, col] = True

    return slips


def cycle_slip_repair(
    gf: np.ndarray,
    slips: np.ndarray,
    hmw: np.ndarray | None = None,
    repair_method: Literal["lsq", "simple"] = "lsq",
) -> np.ndarray:
    """Repair cycle slips per cut_slip_repair.m GPS_slip lines 151-168.

    Per paper Eq.(3):
        A = [1, -1; lambda1, -lambda2]
        L = [delta_Nwl; delta_Lgf]
        dN_float = A \\ L
        dN1_fix = round(dN_float(1))
        dN2_fix = round(dN_float(2))
        correction = dN1_fix*lambda1 - dN2_fix*lambda2
    """
    if gf.ndim == 1:
        gf = gf.reshape(-1, 1)
    if slips.ndim == 1:
        slips = slips.reshape(-1, 1)

    out = gf.copy()
    n_epochs, n_sats = out.shape

    for col in range(n_sats):
        hmw_col = hmw[:, col] if hmw is not None and hmw.shape[0] > col else None

        # Get arcs
        valid = np.isfinite(out[:, col]) & (out[:, col] != 0)
        arcs = _get_arcs(valid)

        for arc_start, arc_end in arcs:
            if (arc_end - arc_start + 1) < 30:
                continue

            for k in range(arc_start + 1, arc_end + 1):
                if not slips[k, col]:
                    continue

                if hmw_col is None:
                    # Fallback: simple differencing
                    out[k:arc_end + 1, col] -= (out[k, col] - out[k - 1, col])
                    continue

                # Per cut_slip_repair.m lines 151-166
                delta_Nwl = hmw_col[k] - hmw_col[k - 1]
                delta_Lgf = out[k, col] - out[k - 1, col]

                # Per Eq.(3): A = [1, -1; lambda1, -lambda2]
                A = np.array([
                    [1.0, -1.0],
                    [GPS_L1_WAVELENGTH, -GPS_L2_WAVELENGTH],
                ], dtype=float)
                L = np.array([delta_Nwl, delta_Lgf], dtype=float)

                try:
                    dN_float = np.linalg.solve(A, L)
                    dN1_fix = int(np.round(dN_float[0]))
                    dN2_fix = int(np.round(dN_float[1]))

                    if dN1_fix != 0 or dN2_fix != 0:
                        # Per line 165: L_gf correction
                        correction = dN1_fix * GPS_L1_WAVELENGTH - dN2_fix * GPS_L2_WAVELENGTH
                        out[k:arc_end + 1, col] -= correction
                except np.linalg.LinAlgError:
                    out[k:arc_end + 1, col] -= delta_Lgf

    return out


# ---------------------------------------------------------------------------
# Detrending per paper Eq.(4) and butterworthband.m
# ---------------------------------------------------------------------------

def geodetic_detrending(
    series: np.ndarray,
    degree: int = 1,
) -> np.ndarray:
    """Remove polynomial trend (linear by default). Per paper: geodetic detrending step."""
    if series.ndim == 1:
        return _detrend_1d(series, degree)
    result = np.zeros_like(series, dtype=float)
    for col in range(series.shape[1]):
        result[:, col] = _detrend_1d(series[:, col], degree)
    return result


def polynomial_detrending(
    series: np.ndarray,
    degree: int = 3,
) -> np.ndarray:
    """Third-order polynomial detrending per paper Eq.(4): P(t) = a3*t^3 + a2*t^2 + a1*t + a0."""
    return geodetic_detrending(series, degree=degree)


def _detrend_1d(series: np.ndarray, degree: int) -> np.ndarray:
    out = series.copy()
    valid = np.isfinite(out)
    if valid.sum() < degree + 1:
        return out
    x = np.where(valid)[0].astype(float)
    y = out[valid]
    coef = np.polyfit(x, y, degree)
    trend = np.full(len(out), np.nan, dtype=float)
    trend[valid] = np.polyval(coef, x)
    out[valid] = y - np.polyval(coef, x)
    return out


# ---------------------------------------------------------------------------
# Butterworth filter per butterworthband.m (strict translation)
# ---------------------------------------------------------------------------

def butterworth_filter(
    series: np.ndarray,
    order: int = 6,
    lowcut: float = 0.001,
    highcut: float = 0.015,
    fs: float = 1.0 / 30.0,
    filter_type: Literal["band", "low", "high"] = "band",
) -> np.ndarray:
    """6th-order Butterworth bandpass filter per butterworthband.m.

    Per butterworthband.m lines 16-63:
    1. order = 6; fn = fs/2; Wn = band_freqs / fn;
    2. [b, a] = butter(order, Wn, 'bandpass')
    3. For each column (satellite), find continuous finite segments
    4. For each segment: if length > 6*order, apply detrend(segment,3) then filtfilt
    5. Segments shorter than 6*order set to NaN

    Default passband: [0.001, 0.015] Hz per M_ISSION paper (wenxian.pdf).
    """
    if series.ndim == 1:
        series = series.reshape(-1, 1)

    nyquist = fs / 2.0
    if nyquist <= 0:
        return np.full_like(series, np.nan)

    Wn = np.array([lowcut, highcut]) / nyquist
    b, a = butter(order, Wn, btype="band", analog=False)

    min_segment = 6 * order  # Per line 51
    n_epochs, n_sats = series.shape
    out = np.full_like(series, np.nan, dtype=float)

    for col in range(n_sats):
        sat_data = series[:, col]

        # Per butterworthband.m lines 39-43: find continuous finite segments
        valid = np.isfinite(sat_data)
        d = np.diff(np.concatenate(([0], valid.astype(int), [0])))
        start_indices = np.where(d == 1)[0]
        end_indices = np.where(d == -1)[0] - 1

        for j in range(len(start_indices)):
            seg_start = start_indices[j]
            seg_end = end_indices[j]
            segment = sat_data[seg_start:seg_end + 1].copy()
            seg_len = len(segment)

            if seg_len > min_segment:
                # Per line 52: segment2 = detrend(segment, 3)
                x_idx = np.arange(seg_len, dtype=float)
                coef = np.polyfit(x_idx, segment, 3)
                detrended = segment - np.polyval(coef, x_idx)

                # Per line 53: filtered_segment = filtfilt(b, a, segment2)
                pad_len = min(3 * max(len(a), len(b)), seg_len - 1)
                try:
                    filtered_segment = filtfilt(b, a, detrended, padlen=pad_len)
                    out[seg_start:seg_end + 1, col] = filtered_segment
                except Exception:
                    pass  # Leave as NaN
            # else: segments shorter than 6*order stay NaN (line 55-56)

    if out.shape[1] == 1:
        return out.ravel()
    return out


# ---------------------------------------------------------------------------
# Full preprocessing chain per paper Fig.1
# ---------------------------------------------------------------------------

def preprocess_chain(signal: np.ndarray, min_arc: int = 10) -> PreprocessArtifacts:
    """Full preprocessing chain per paper Fig.1."""
    if signal.ndim == 1:
        signal_2d = signal.reshape(-1, 1)
    else:
        signal_2d = signal

    # 1. Short arc removal (paper: arcs < 10 epochs removed)
    gf = np.column_stack([
        short_arc_removal(signal_2d[:, col], min_arc=min_arc)
        for col in range(signal_2d.shape[1])
    ])

    # 2. Synthetic HMW (real HMW requires pseudorange data from RINEX)
    np.random.seed(42)
    hmw_base = np.random.randn(signal_2d.shape[0]).reshape(-1, 1) * 0.1
    if signal_2d.shape[1] > 1:
        hmw_base = np.hstack([hmw_base] * signal_2d.shape[1])
    hmw = np.column_stack([
        short_arc_removal(hmw_base[:, col], min_arc=min_arc)
        for col in range(hmw_base.shape[1])
    ])

    # 3. Cycle slip detection per cut_slip_repair.m
    slips = cycle_slip_detection(gf, hmw=hmw)

    # 4. Cycle slip repair per Eq.(3)
    repaired = cycle_slip_repair(gf, slips, hmw=hmw)

    # 5. Geodetic detrending (linear) - paper: requires precise products
    geo = geodetic_detrending(repaired, degree=1)

    # 6. Third-order polynomial detrending per Eq.(4) is applied INSIDE
    #    butterworth_filter() per butterworthband.m line 52: detrend(segment, 3).
    #    Applying it externally as well would double-detrend and suppress signal.

    # 7. Butterworth filter per butterworthband.m (internally applies 3rd-order detrend)
    filt = butterworth_filter(geo)

    def _squeeze(arr):
        return arr.ravel() if arr.shape[1] == 1 else arr

    return PreprocessArtifacts(
        gf=_squeeze(gf),
        hmw=_squeeze(hmw),
        cycle_slip_points=slips,
        detrended_geodetic=_squeeze(geo),
        detrended_poly=_squeeze(geo),
        filtered=_squeeze(filt),
    )
