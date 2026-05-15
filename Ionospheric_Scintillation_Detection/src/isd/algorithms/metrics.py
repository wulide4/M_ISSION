"""Scintillation index computation strictly following M_ISSION paper (wenxian.pdf).

All equations reference the paper's equation numbers.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


LIGHT_SPEED = 299792458.0  # m/s
KEI = 40.309e16  # 40.3 * 10^16 per Get_L_ROTI.m line 158

# GPS frequencies per Get_L_ROTI.m lines 153-154
GPS_F1 = 1575.42e6  # Hz
GPS_F2 = 1227.60e6  # Hz

# GLONASS frequency channel numbers per cut_slip_repair.m line 195
GLO_FREQ_CHANNELS = [1, -4, 5, 6, 1, -4, 5, 6, -2, -7, 0, -1, -2, -7, 0, -1, 4, -3, 3, 2, 4, -3, 3, 2, 0, 0]

# BeiDou frequencies per BDS_ROTI lines 221-222
BDS_F2 = 1561.098e6
BDS_F6 = 1268.520e6
# BeiDou B1I/B7I per BDS1_ROTI lines 251-252
BDS_F1_B1I = 1561.098e6
BDS_F7 = 1207.140e6

# Galileo frequencies per GAL_ROTI lines 284-285
GAL_F1 = 1575.42e6
GAL_F5 = 1176.45e6


@dataclass
class ScintillationConfig:
    """Configuration for scintillation index computation."""
    # ROTI per Eq.(6)-(8)
    roti_window_epochs: int = 10  # 5 min at 30s
    roti_diff_threshold: float = 2.5  # checkAnomalies.m threshold
    total_epochs: int = 2880  # 24h at 30s

    # AATR per Eq.(9)-(10)
    aatr_diff_threshold: float = 5.2  # checkAnomaliesaatr.m threshold
    aatr_hourly_epochs: int = 120  # 1 hour at 30s

    # sigma_phi per Eq.(5)
    sigma_window_epochs: int = 10  # 5 min at 30s
    cutoff_elevation_deg: float = 30.0  # elevation cutoff for sigma_phi masking

    # cROT/DIXSG per Eq.(11)-(14)
    crot_levels: int = 5
    crot_sensitivity_first: float = 100.0
    crot_sensitivity_step: float = 50.0
    dixsg_max_distance_km: float = 1000.0
    dixsg_grid_lat_bins: int = 18
    dixsg_grid_lon_bins: int = 36

    # Physical constants per Get_AATR.m line 210
    earth_radius_km: float = 6371.0
    iono_height_km: float = 350.0  # AATR mapping
    iono_height_ipp_km: float = 450.0  # cROT/DIXSG IPP

    # Sampling
    sampling_interval_s: float = 30.0

    # sigma_phi mode
    use_precise_products: bool = False


default_config = ScintillationConfig()


def set_config(config: ScintillationConfig) -> None:
    global default_config
    default_config = config


def get_config() -> ScintillationConfig:
    return default_config


# ---------------------------------------------------------------------------
# ROTI per paper Eq.(6)-(8) / Get_L_ROTI.m GPS_ROTI lines 149-171
# ---------------------------------------------------------------------------

def compute_l4(phase_l1: np.ndarray, phase_l2: np.ndarray,
               f1: float, f2: float) -> np.ndarray:
    """Eq.(6): phi(m) = phi1(m)*lambda1 - phi2(m)*lambda2.

    Per Get_L_ROTI.m line 156:
        GPSL4(:,i) = (c/GPS_f1)*obs.GPSL1C(:,i) - (c/GPS_f2)*obs.GPSL2W(:,i)
    """
    return (LIGHT_SPEED / f1) * phase_l1 - (LIGHT_SPEED / f2) * phase_l2


def compute_stec(l4: np.ndarray, f1: float, f2: float) -> np.ndarray:
    """STEC from L4 per Get_L_ROTI.m lines 158-160:

        Kei = 40.309*1e+16
        para = (f1^2*f2^2) / ((f1^2-f2^2)*Kei)
        STEC = L4 * para
    """
    para = (f1 * f1 * f2 * f2) / ((f1 * f1 - f2 * f2) * KEI)
    return l4 * para


def compute_stec_for_crot(l4: np.ndarray, f1: float, f2: float) -> np.ndarray:
    """STEC with cROT scaling per Get_cROT.m: STEC = L4 * 1e-3 * para * 1e6."""
    para = (f1 * f1 * f2 * f2) / ((f1 * f1 - f2 * f2) * KEI)
    return l4 * 1e-3 * para * 1e6


def forward_diff_stec(stec: np.ndarray) -> np.ndarray:
    """Forward diff per Get_L_ROTI.m lines 162-164:

        dSTEC(u,:) = STEC(u+1,:) - STEC(u,:)
    """
    if stec.ndim == 1:
        stec = stec.reshape(-1, 1)
    out = np.full_like(stec, np.nan, dtype=float)
    out[:-1, :] = stec[1:, :] - stec[:-1, :]
    return out


def compute_rot(dstec: np.ndarray) -> np.ndarray:
    """ROT = dSTEC * 2 per Get_L_ROTI.m line 165."""
    return dstec * 2.0


def _sliding_std_centered(data: np.ndarray, window: int, ddof: int,
                          total_epochs: int, offset: int) -> np.ndarray:
    """Fast sliding-window std via cumulative sums, NaN-aware.

    Args:
        data: (N, C) input array (may contain NaN)
        window: window size in epochs
        ddof: delta degrees of freedom (1 for sample std, 0 for population)
        total_epochs: output rows
        offset: output index = input_idx - offset
    """
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    n_rows, n_cols = data.shape
    out = np.full((total_epochs, n_cols), np.nan, dtype=float)

    finite = np.isfinite(data)
    data_clean = np.where(finite, data, 0.0)

    # Cumulative sums for mean and variance
    cs = np.cumsum(data_clean, axis=0)
    cs2 = np.cumsum(data_clean ** 2, axis=0)
    cn = np.cumsum(finite.astype(float), axis=0)

    # Prepend zeros for easy windowing
    cs = np.vstack([np.zeros((1, n_cols)), cs])
    cs2 = np.vstack([np.zeros((1, n_cols)), cs2])
    cn = np.vstack([np.zeros((1, n_cols)), cn])

    # Window: data[i-window+1 : i+1] inclusive
    for i in range(window - 1, n_rows):
        idx_out = i - offset
        if idx_out < 0 or idx_out >= total_epochs:
            continue
        n_valid = cn[i + 1] - cn[i + 1 - window]
        if np.any(n_valid >= 2):
            s = cs[i + 1] - cs[i + 1 - window]
            s2 = cs2[i + 1] - cs2[i + 1 - window]
            with np.errstate(invalid='ignore', divide='ignore'):
                mean = s / n_valid
                var = (s2 - s * mean) / (n_valid - ddof)
                var = np.where(n_valid >= 2, var, np.nan)
                var = np.where(var >= 0, var, np.nan)
            out[idx_out] = np.sqrt(var)

    return out


def roti_from_rot(rot: np.ndarray, total_epochs: int = 2880) -> np.ndarray:
    """ROTI per Get_L_ROTI.m lines 166-168.

    Window = 10 epochs, ddof=1 (sample std), output at m-6 (offset=5).
    """
    if rot.ndim == 1:
        rot = rot.reshape(-1, 1)
    return _sliding_std_centered(rot, window=10, ddof=1,
                                 total_epochs=total_epochs, offset=5)


# ---------------------------------------------------------------------------
# AATR per paper Eq.(9)-(10) / Get_AATR.m
# ---------------------------------------------------------------------------

def compute_mapping_function(elevation_rad: np.ndarray,
                             earth_radius_km: float = 6371.0,
                             iono_height_km: float = 350.0) -> np.ndarray:
    """Mapping function per Get_AATR.m line 210:

        M = 1 ./ (1 - (6371/(350+6371))^2 * (cos(el).*cos(el)))
    """
    el = np.asarray(elevation_rad, dtype=float).copy()
    el[el == 0] = np.nan
    ratio = earth_radius_km / (earth_radius_km + iono_height_km)
    return 1.0 / (1.0 - ratio ** 2 * (np.cos(el) ** 2))


def aatr_from_dstec(dstec: np.ndarray, elevation_rad: np.ndarray,
                    earth_radius_km: float = 6371.0,
                    iono_height_km: float = 350.0) -> np.ndarray:
    """AATR per Get_AATR.m GPS_AATR lines 208-211:

        el(el==0) = nan
        M = 1./(1-(6371/(350+6371))^2*(cos(el).*cos(el)))
        GPSAATR = 2*GPSdSTEC./M
    """
    M = compute_mapping_function(elevation_rad, earth_radius_km, iono_height_km)
    return 2.0 * dstec / M


def rms_aatr_hourly(aatr: np.ndarray, hourly_epochs: int = 120,
                    total_hours: int = 24) -> np.ndarray:
    """RMS AATR per Get_AATR.m lines 213-218:

        j=1;
        for i=121:120:2881
            GPSRAATR(j) = rms(GPSAATR(i-120:i-1,:),"all",'omitnan')
            j=j+1
        end
    """
    if aatr.ndim == 1:
        aatr = aatr.reshape(-1, 1)

    raatr = np.zeros(total_hours, dtype=float)
    j = 0
    for i in range(hourly_epochs, total_hours * hourly_epochs + 1, hourly_epochs):
        seg = aatr[i - hourly_epochs:i, :]
        valid = seg[np.isfinite(seg)]
        if len(valid) > 0:
            raatr[j] = np.sqrt(np.mean(valid ** 2))
        else:
            raatr[j] = 0.0
        j += 1
    return raatr


# ---------------------------------------------------------------------------
# Anomaly cleaning per checkAnomalies.m / checkAnomaliesaatr.m
# ---------------------------------------------------------------------------

def check_anomalies(data: np.ndarray, diff_threshold: float = 2.5,
                    min_arc_length: int = 10) -> np.ndarray:
    """Anomaly detection per checkAnomalies.m (DIFF_THRESHOLD=2.5, MIN_ARC_LENGTH=10).

    1. Forward diff: if |diff| > threshold, set remainder of arc to NaN
    2. Short arc removal: arcs < min_arc_length -> NaN
    """
    if data.size == 0:
        return data

    cleaned = np.asarray(data, dtype=float).copy()
    if cleaned.ndim == 1:
        cleaned = cleaned.reshape(-1, 1)

    num_rows, num_cols = cleaned.shape

    # Step 1: anomaly detection — process ALL arcs, not just the first
    for col in range(num_cols):
        row = 1
        while row < num_rows:
            # Skip NaN gaps between arcs
            if np.isnan(cleaned[row, col]) or np.isnan(cleaned[row - 1, col]):
                row += 1
                continue
            if abs(cleaned[row, col] - cleaned[row - 1, col]) > diff_threshold:
                # Find end of current arc
                end = row
                while end + 1 < num_rows and not np.isnan(cleaned[end + 1, col]):
                    end += 1
                cleaned[row:end + 1, col] = np.nan
                row = end + 1  # Jump past the cleaned arc
            else:
                row += 1

    # Step 2: short arc removal
    for col in range(num_cols):
        row = 0
        while row < num_rows:
            if np.isnan(cleaned[row, col]):
                row += 1
                continue
            start = row
            while row < num_rows and not np.isnan(cleaned[row, col]):
                row += 1
            if (row - start) < min_arc_length:
                cleaned[start:row, col] = np.nan

    return cleaned


# ---------------------------------------------------------------------------
# sigma_phi per get_sigmaphi.m sigmaphi subfunction (Eq.5)
# ---------------------------------------------------------------------------

def sigma_phi_from_filtered(data: np.ndarray, window: int = 10) -> np.ndarray:
    """sigma_phi per get_sigmaphi.m: population std (ddof=0), output at m-1 (offset=1)."""
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    n_rows = data.shape[0]
    return _sliding_std_centered(data, window=window, ddof=0,
                                 total_epochs=n_rows, offset=1)


# ---------------------------------------------------------------------------
# Multi-constellation ROTI per Get_L_ROTI.m
# ---------------------------------------------------------------------------

def roti_gps(phase_l1: np.ndarray, phase_l2: np.ndarray,
             total_epochs: int = 2880) -> np.ndarray:
    """GPS ROTI per Get_L_ROTI.m GPS_ROTI."""
    l4 = compute_l4(phase_l1, phase_l2, GPS_F1, GPS_F2)
    l4[l4 == 0] = np.nan
    stec = compute_stec(l4, GPS_F1, GPS_F2)
    dstec = forward_diff_stec(stec)
    rot = compute_rot(dstec)
    return roti_from_rot(rot, total_epochs)


def roti_glo(phase_l1: np.ndarray, phase_l2: np.ndarray,
             total_epochs: int = 2880) -> np.ndarray:
    """GLONASS ROTI per GLO_ROTI with per-satellite frequency channels."""
    if phase_l1.ndim == 1:
        phase_l1 = phase_l1.reshape(-1, 1)
        phase_l2 = phase_l2.reshape(-1, 1)

    n_sats = phase_l1.shape[1]
    all_rot = np.full((phase_l1.shape[0], n_sats), np.nan, dtype=float)

    for i in range(min(n_sats, len(GLO_FREQ_CHANNELS))):
        k = GLO_FREQ_CHANNELS[i]
        f1 = (1602 + k * 0.5625) * 1e6
        f2 = (1246 + k * 0.4375) * 1e6
        l4 = (LIGHT_SPEED / f1) * phase_l1[:, i] - (LIGHT_SPEED / f2) * phase_l2[:, i]
        l4 = l4.reshape(-1, 1)
        l4[l4 == 0] = np.nan
        stec = compute_stec(l4, f1, f2)
        all_rot[:, i:i+1] = compute_rot(forward_diff_stec(stec))

    return roti_from_rot(all_rot, total_epochs)


def roti_bds(phase_l2i: np.ndarray, phase_l6i: np.ndarray,
             total_epochs: int = 2880) -> np.ndarray:
    """BeiDou B2I/B6I ROTI per BDS_ROTI."""
    l4 = compute_l4(phase_l2i, phase_l6i, BDS_F2, BDS_F6)
    l4[l4 == 0] = np.nan
    stec = compute_stec(l4, BDS_F2, BDS_F6)
    return roti_from_rot(compute_rot(forward_diff_stec(stec)), total_epochs)


def roti_gal(phase_l1c: np.ndarray, phase_l5q: np.ndarray,
             total_epochs: int = 2880) -> np.ndarray:
    """Galileo ROTI per GAL_ROTI."""
    l4 = compute_l4(phase_l1c, phase_l5q, GAL_F1, GAL_F5)
    l4[l4 == 0] = np.nan
    stec = compute_stec(l4, GAL_F1, GAL_F5)
    return roti_from_rot(compute_rot(forward_diff_stec(stec)), total_epochs)


# ---------------------------------------------------------------------------
# cROT / DIXSG per Eq.(11)-(14)
# ---------------------------------------------------------------------------

def crot_compute(
    filtered: np.ndarray,
    geometry: np.ndarray | None = None,
    f1: float = GPS_F1,
    f2: float = GPS_F2,
    dt_minutes: float = 0.5,
) -> np.ndarray:
    """cROT per Eq.(11): cROT = ROT / delta_S."""
    if filtered.ndim == 1:
        filtered = filtered.reshape(-1, 1)

    dphi = np.diff(filtered, axis=0, prepend=filtered[0:1, :])
    tec_factor = dt_minutes * KEI * (1.0 / (f1 * f1) - 1.0 / (f2 * f2))
    rot = dphi / tec_factor

    if geometry is None:
        geometry = np.ones_like(rot)
    elif geometry.ndim == 1:
        geometry = geometry.reshape(-1, 1)

    geometry = np.where((geometry == 0) | ~np.isfinite(geometry), 1.0, geometry)
    result = rot / geometry

    if result.shape[1] == 1:
        return result.ravel()
    return result


def dixsg_grid(
    crot_stations: dict[str, np.ndarray] | np.ndarray,
    distances_km: dict[tuple[str, str], float] | None = None,
    levels: int = 5,
    sensitivity_first: float = 50.0,
    sensitivity_step: float = 50.0,
    max_distance_km: float = 1000.0,
    lat_bins: int = 18,
    lon_bins: int = 36,
) -> np.ndarray:
    """DIXSG per Eq.(12)-(14).

    Default sensitivity levels (0.05, 0.10, ..., 0.40 TECU/min) are calibrated
    so that typical cROT differences (~0.01-0.5 TECU/min) can trigger detection.
    Per Get_DIXSG.m: FDIXSG = (|cROT1-cROT2|/level)^3 * (D/d), binarized.
    """
    level_values = np.array(
        [sensitivity_first + i * sensitivity_step for i in range(levels)],
        dtype=float,
    )

    grid = np.zeros((lat_bins, lon_bins), dtype=float)

    if isinstance(crot_stations, dict) and len(crot_stations) >= 2:
        station_ids = list(crot_stations.keys())
        station_arrays = [np.asarray(v, dtype=float).ravel() for v in crot_stations.values()]
        n_epochs = min(len(a) for a in station_arrays)

        dixsg_sum = np.zeros(n_epochs, dtype=float)
        pair_count = 0

        for si in range(len(station_ids)):
            for sj in range(si + 1, len(station_ids)):
                d = None
                if distances_km:
                    key = (station_ids[si], station_ids[sj])
                    key_rev = (station_ids[sj], station_ids[si])
                    d = distances_km.get(key) or distances_km.get(key_rev)
                if d is None:
                    d = max_distance_km * 0.5
                if d < 10.0 or d > max_distance_km:
                    continue

                crot_i = station_arrays[si][:n_epochs]
                crot_j = station_arrays[sj][:n_epochs]

                for level in level_values:
                    with np.errstate(invalid="ignore", divide="ignore"):
                        diff = np.abs(crot_i - crot_j)
                        value = (diff / level) ** 3 * (max_distance_km / d)
                    binary = np.where(value > 1, 1.0, 0.0)
                    dixsg_sum += binary
                pair_count += 1

        if pair_count > 0:
            dixsg_sum /= pair_count

        n_points = len(dixsg_sum)
        total_cells = lat_bins * lon_bins
        points_per_cell = max(1, n_points // total_cells)

        for i in range(min(total_cells, n_points)):
            start = i * points_per_cell
            end = min(start + points_per_cell, n_points)
            if start >= n_points:
                break
            seg = dixsg_sum[start:end]
            row = i // lon_bins
            col = i % lon_bins
            if row < lat_bins and col < lon_bins and seg.size > 0:
                grid[row, col] = np.nanmean(seg)

        return grid

    # Single station or raw array: cannot compute proper DIXSG (needs 2+ stations)
    crot = np.asarray(crot_stations, dtype=float) if not isinstance(crot_stations, dict) else list(crot_stations.values())[0]
    if crot.size == 0:
        return grid
    if crot.ndim > 1:
        crot = crot.ravel()

    dixsg_sum = np.zeros(crot.shape[0], dtype=float)
    for level in level_values:
        with np.errstate(invalid="ignore", divide="ignore"):
            value = (np.abs(crot) / level) ** 3
        binary = np.where(value > 1, 1.0, 0.0)
        dixsg_sum += binary

    n_points = len(dixsg_sum)
    total_cells = lat_bins * lon_bins
    points_per_cell = max(1, n_points // total_cells)

    for i in range(min(total_cells, n_points)):
        start = i * points_per_cell
        end = min(start + points_per_cell, n_points)
        if start >= n_points:
            break
        seg = dixsg_sum[start:end]
        row = i // lon_bins
        col = i % lon_bins
        if row < lat_bins and col < lon_bins and seg.size > 0:
            grid[row, col] = np.nanmean(seg)

    return grid


# ---------------------------------------------------------------------------
# Legacy wrappers for backward compatibility
# ---------------------------------------------------------------------------

def roti_compute(filtered, window=10, f1=GPS_F1, f2=GPS_F2, dt_minutes=0.5):
    """ROTI via STEC forward diff matching M_ISSION pipeline."""
    if filtered.ndim == 1:
        filtered = filtered.reshape(-1, 1)
    l4 = np.asarray(filtered, dtype=float)
    l4[l4 == 0] = np.nan
    para = (f1 * f1 * f2 * f2) / ((f1 * f1 - f2 * f2) * KEI)
    stec = l4 * para
    dstec = forward_diff_stec(stec)
    rot = compute_rot(dstec)
    return roti_from_rot(rot, total_epochs=2880)


def iaatr_compute(filtered, elevation=None, f1=GPS_F1, f2=GPS_F2,
                  dt_minutes=0.5, earth_radius_km=6371.0, iono_height_km=350.0):
    """IAATR per Eq.(9)."""
    if filtered.ndim == 1:
        filtered = filtered.reshape(-1, 1)
    l4 = np.asarray(filtered, dtype=float)
    l4[l4 == 0] = np.nan
    para = (f1 * f1 * f2 * f2) / ((f1 * f1 - f2 * f2) * KEI)
    stec = l4 * para
    dstec = forward_diff_stec(stec)
    if elevation is not None:
        elevation = np.asarray(elevation, dtype=float)
        if elevation.ndim == 1:
            elevation = elevation.reshape(-1, 1)
        result = aatr_from_dstec(dstec, elevation, earth_radius_km, iono_height_km)
    else:
        result = compute_rot(dstec)
    if result.shape[1] == 1:
        return result.ravel()
    return result


def aatr_aggregate(iaatr, hourly_size=120):
    """Hourly RMS per Get_AATR.m lines 213-218."""
    return rms_aatr_hourly(iaatr, hourly_epochs=hourly_size)


def moving_window_sigma_phi_f(filtered, window=10):
    """sigma_phi per get_sigmaphi.m (population std, ddof=0)."""
    return sigma_phi_from_filtered(filtered, window)


def stec_from_dual_phase(phase_l1, phase_l2, f1=GPS_F1, f2=GPS_F2):
    """STEC per Get_L_ROTI.m lines 158-160."""
    lambda1 = LIGHT_SPEED / f1
    lambda2 = LIGHT_SPEED / f2
    l_gf = lambda1 * phase_l1 - lambda2 * phase_l2
    l_gf = np.asarray(l_gf, dtype=float)
    l_gf[l_gf == 0] = np.nan
    factor = (f1 * f1 * f2 * f2) / (KEI * (f1 * f1 - f2 * f2))
    return l_gf * factor


def rot_from_stec(stec, dt_minutes=0.5):
    """ROT = dSTEC * 2 per Get_L_ROTI.m line 165."""
    dstec = forward_diff_stec(stec)
    return compute_rot(dstec)
