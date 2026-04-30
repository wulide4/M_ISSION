"""RINEX-based scintillation computation strictly following M_ISSION paper (wenxian.pdf).

Data flow per M_ISSION paper:
  RINEX OBS -> L4 = (c/f1)*L1 - (c/f2)*L2                    (Eq.6)
  -> STEC = L4 * para  (para = f1^2*f2^2 / ((f1^2-f2^2)*Kei))
  -> dSTEC(u) = STEC(u+1) - STEC(u)
  -> ROT = dSTEC * 2
  -> ROTI = std(ROT(m-10:m-1)) ddof=1 for m=11:2881          (Eq.7-8)
  -> AATR = 2*dSTEC / M  (M = mapping function per Eq.9)      (Eq.9)
  -> RMS AATR = hourly RMS per Eq.(10)                         (Eq.10)
  -> sigma_phi: preprocessing chain + Butterworth + std(ddof=0) (Eq.5)

All equations reference the paper's equation numbers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from isd.algorithms.metrics import (
    GPS_F1,
    GPS_F2,
    GAL_F1,
    GAL_F5,
    BDS_F2,
    BDS_F6,
    LIGHT_SPEED,
    GLO_FREQ_CHANNELS,
    ScintillationConfig,
    aatr_from_dstec,
    check_anomalies,
    compute_l4,
    compute_rot,
    compute_stec,
    compute_stec_for_crot,
    crot_compute,
    forward_diff_stec,
    rms_aatr_hourly,
    roti_from_rot,
    sigma_phi_from_filtered,
)
from isd.algorithms.preprocess import (
    butterworth_filter,
    cycle_slip_detection,
    cycle_slip_repair,
    geodetic_detrending,
    polynomial_detrending,
    short_arc_removal,
)
from isd.algorithms.sp3_orbit import (
    compute_elevation_azimuth,
    epoch_times_to_seconds,
    interpolate_sp3_to_epochs,
    parse_sp3,
)
from isd.infrastructure.filesystem.rinex_reader import read_rinex_obs

logger = logging.getLogger(__name__)

SYSTEM_FREQS = {
    'GPS': (GPS_F1, GPS_F2),
    'GAL': (GAL_F1, GAL_F5),
    'BDS': (BDS_F2, BDS_F6),
}


def _get_system_freqs(system: str) -> tuple[float, float]:
    return SYSTEM_FREQS.get(system, (GPS_F1, GPS_F2))


def _compute_l4_stec(
    phase_l1: np.ndarray, phase_l2: np.ndarray, gnss_system: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute L4 geometry-free combination with system-specific frequencies.

    For GLONASS, each satellite has a different frequency channel.
    Returns (L4, placeholder_STEC) — actual STEC is computed separately for GLO.
    """
    if gnss_system == 'GLO':
        n_sats = phase_l1.shape[1] if phase_l1.ndim == 2 else 1
        l4 = np.full_like(phase_l1, np.nan, dtype=float)
        for i in range(min(n_sats, len(GLO_FREQ_CHANNELS))):
            k = GLO_FREQ_CHANNELS[i]
            f1 = (1602 + k * 0.5625) * 1e6
            f2 = (1246 + k * 0.4375) * 1e6
            if phase_l1.ndim == 2:
                l4[:, i] = (LIGHT_SPEED / f1) * phase_l1[:, i] - (LIGHT_SPEED / f2) * phase_l2[:, i]
            else:
                l4[i] = (LIGHT_SPEED / f1) * phase_l1[i] - (LIGHT_SPEED / f2) * phase_l2[i]
        return l4, l4  # STEC placeholder for GLO
    else:
        f1, f2 = _get_system_freqs(gnss_system)
        l4 = compute_l4(phase_l1, phase_l2, f1, f2)
        return l4, l4


def _compute_stec_glo(l4_clean: np.ndarray) -> np.ndarray:
    """Compute STEC for GLONASS with per-satellite frequencies."""
    if l4_clean.ndim == 1:
        l4_clean = l4_clean.reshape(-1, 1)
    n_sats = l4_clean.shape[1]
    stec = np.full_like(l4_clean, np.nan, dtype=float)
    for i in range(min(n_sats, len(GLO_FREQ_CHANNELS))):
        k = GLO_FREQ_CHANNELS[i]
        f1 = (1602 + k * 0.5625) * 1e6
        f2 = (1246 + k * 0.4375) * 1e6
        para = (f1 * f1 * f2 * f2) / ((f1 * f1 - f2 * f2) * 40.309e16)
        stec[:, i] = l4_clean[:, i] * para
    return stec


@dataclass
class ScintillationResult:
    roti: np.ndarray | None = None
    iaatr: np.ndarray | None = None
    aatr: np.ndarray | None = None
    sigma_phi_f: np.ndarray | None = None
    crot: np.ndarray | None = None
    crot_ipp_b: np.ndarray | None = None
    crot_ipp_l: np.ndarray | None = None
    gf_phase: np.ndarray | None = None
    satellite_ids: list[str] | None = None
    num_epochs: int = 0
    num_satellites: int = 0
    station_code: str = ''
    elevation_rad: np.ndarray | None = None
    azimuth_rad: np.ndarray | None = None


def _compute_elevation_from_sp3(
    obs_data,
    sp3_paths: list[str | Path],
) -> tuple[np.ndarray, np.ndarray] | None:
    """Compute elevation/azimuth from SP3 files matching M_ISSION Get_EA.m."""
    if not sp3_paths or obs_data.approx_xyz is None:
        return None
    if not obs_data.epoch_times:
        return None

    try:
        sp3_list = []
        for p in sp3_paths:
            path = Path(p)
            if path.exists():
                sp3_list.append(parse_sp3(path))
        if not sp3_list:
            return None

        target_seconds = epoch_times_to_seconds(obs_data.epoch_times)
        if len(target_seconds) == 0:
            return None

        # Only interpolate satellites present in RINEX OBS (typically ~10-15 GPS vs 121 total)
        sat_filter = set(obs_data.satellite_ids) if obs_data.satellite_ids else None
        sat_pos = interpolate_sp3_to_epochs(
            sp3_list, target_seconds, lagrange_order=11, satellite_filter=sat_filter,
        )
        if not sat_pos:
            return None

        elev, az = compute_elevation_azimuth(
            obs_data.approx_xyz,
            sat_pos,
            satellite_order=obs_data.satellite_ids,
        )
        return elev, az
    except Exception as exc:
        logger.warning("SP3 elevation computation failed: %s", exc)
        return None


def compute_scintillation_from_rinex(
    file_path: str | Path,
    config: ScintillationConfig | None = None,
    compute_metrics: list[str] | None = None,
    sp3_paths: list[str | Path] | None = None,
    gnss_system: str = 'GPS',
) -> ScintillationResult:
    """Main entry: RINEX -> scintillation indices per M_ISSION pipeline.

    Pipeline strictly follows wenxian.pdf Fig.1 and corresponding MATLAB code.
    gnss_system selects which GNSS constellation to process ('GPS', 'GLO', 'GAL', 'BDS').
    """
    if config is None:
        config = ScintillationConfig()

    if compute_metrics is None:
        compute_metrics = ['ROTI', 'IAATR', 'AATR', 'SIGMA_PHI_F']

    obs_data = read_rinex_obs(file_path, gnss_system=gnss_system)
    if obs_data.phase_l1 is None or obs_data.phase_l2 is None:
        return ScintillationResult(
            station_code=obs_data.station_code,
            num_epochs=obs_data.num_epochs,
        )

    if obs_data.num_satellites == 0:
        return ScintillationResult(
            station_code=obs_data.station_code,
            num_epochs=obs_data.num_epochs,
        )

    phase_l1 = obs_data.phase_l1
    phase_l2 = obs_data.phase_l2

    # Compute L4 with system-specific frequencies
    l4, stec = _compute_l4_stec(phase_l1, phase_l2, gnss_system)
    l4_clean = l4.copy()
    l4_clean[l4_clean == 0] = np.nan

    # Compute elevation/azimuth from SP3 per Get_EA.m
    elev_az_result = _compute_elevation_from_sp3(obs_data, sp3_paths or [])
    elevation_rad = None
    azimuth_rad = None
    if elev_az_result is not None:
        elevation_rad, azimuth_rad = elev_az_result

    result = ScintillationResult(
        station_code=obs_data.station_code,
        satellite_ids=obs_data.satellite_ids,
        num_epochs=obs_data.num_epochs,
        num_satellites=obs_data.num_satellites,
        gf_phase=l4_clean,
        elevation_rad=elevation_rad,
        azimuth_rad=azimuth_rad,
    )

    # STEC already computed inside _compute_l4_stec for GPS/GAL/BDS;
    # for GLO it was per-satellite
    if gnss_system == 'GLO':
        stec = _compute_stec_glo(l4_clean)
    else:
        f1, f2 = _get_system_freqs(gnss_system)
        stec = compute_stec(l4_clean, f1, f2)

    # dSTEC per Get_L_ROTI.m lines 162-164
    dstec = forward_diff_stec(stec)

    # ROT = dSTEC * 2 per Get_L_ROTI.m line 165
    rot = compute_rot(dstec)

    if 'ROTI' in compute_metrics:
        # ROTI per Get_L_ROTI.m lines 166-168 (Eq.7-8)
        roti = roti_from_rot(rot, total_epochs=config.total_epochs)
        roti = check_anomalies(roti, diff_threshold=config.roti_diff_threshold,
                               min_arc_length=10)
        result.roti = roti

    if 'IAATR' in compute_metrics:
        # IAATR per Eq.(9): AATR = 2*dSTEC/M
        if elevation_rad is not None:
            iaatr = aatr_from_dstec(dstec, elevation_rad,
                                    earth_radius_km=config.earth_radius_km,
                                    iono_height_km=config.iono_height_km)
        else:
            iaatr = rot
        # Apply anomaly cleaning to remove cycle slip artifacts
        # (same threshold as AATR per checkAnomaliesaatr.m)
        iaatr = check_anomalies(iaatr, diff_threshold=config.aatr_diff_threshold,
                                min_arc_length=10)
        result.iaatr = iaatr

    if 'AATR' in compute_metrics:
        # AATR per Get_AATR.m GPS_AATR lines 208-211 (Eq.9)
        if elevation_rad is not None:
            iaatr = aatr_from_dstec(dstec, elevation_rad,
                                    earth_radius_km=config.earth_radius_km,
                                    iono_height_km=config.iono_height_km)
        else:
            # Fallback without elevation: use ROT proxy
            fake_el = np.full_like(dstec, np.nan, dtype=float)
            iaatr = aatr_from_dstec(dstec, fake_el,
                                    earth_radius_km=config.earth_radius_km,
                                    iono_height_km=config.iono_height_km)
            iaatr = np.where(np.isfinite(iaatr), iaatr, rot)
        # checkAnomaliesaatr.m: threshold=5.2, min_arc=5
        # Applied for both elevation and non-elevation paths to remove
        # cycle slip residuals and other outliers before RMS aggregation.
        # Use min_arc=5 (vs MATLAB's 10) because elevation NaN gaps create
        # shorter arcs in our pipeline.
        iaatr = check_anomalies(iaatr, diff_threshold=config.aatr_diff_threshold,
                                min_arc_length=5)
        # RMS AATR per Get_AATR.m lines 213-218 (Eq.10)
        result.aatr = rms_aatr_hourly(iaatr, hourly_epochs=config.aatr_hourly_epochs)

    if 'SIGMA_PHI_F' in compute_metrics:
        has_precise = getattr(config, 'use_precise_products', False)
        sigma = _compute_sigma_phi_f(
            l4_clean, config,
            has_precise_products=has_precise,
            elevation_rad=elevation_rad,
        )
        result.sigma_phi_f = sigma

    if 'CROT' in compute_metrics or 'DIXSG' in compute_metrics:
        crot, ipp_b, ipp_l = _compute_crot_with_ipp(
            l4_clean, f1, f2, gnss_system,
            obs_data.approx_xyz,
            elevation_rad, azimuth_rad,
            config,
        )
        result.crot = crot
        result.crot_ipp_b = ipp_b
        result.crot_ipp_l = ipp_l

    return result


def _compute_crot_with_ipp(
    l4_clean: np.ndarray,
    f1: float,
    f2: float,
    gnss_system: str,
    approx_xyz: np.ndarray | None,
    elevation_rad: np.ndarray | None,
    azimuth_rad: np.ndarray | None,
    config: ScintillationConfig,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    """Compute cROT with IPP coordinates per Get_cROT.m (Eq.11).

    Per the MATLAB pipeline:
      STEC = L4 * 1e-3 * para * 1e6
      dSTEC = forward diff
      IPP coords via Get_dif (450km shell)
      cROT = |dSTEC / dif| * 2

    Returns (cROT, ipp_lat_rad, ipp_lon_rad).
    """
    from isd.algorithms.matlab_metrics import EARTH_RADIUS_KM, IONO_HEIGHT_IPP_KM, _xyz_to_blh

    # STEC with cROT scaling per Get_cROT.m
    if gnss_system == 'GLO':
        stec = _compute_stec_glo(l4_clean)
    else:
        stec = compute_stec_for_crot(l4_clean, f1, f2)

    # dSTEC
    dstec = forward_diff_stec(stec)

    # Compute IPP coordinates if elevation/azimuth available
    ipp_b = None
    ipp_l = None

    if (
        elevation_rad is not None
        and azimuth_rad is not None
        and approx_xyz is not None
        and approx_xyz.size >= 3
    ):
        sb, sl = _xyz_to_blh(float(approx_xyz[0]), float(approx_xyz[1]), float(approx_xyz[2]))
        rows, cols = elevation_rad.shape
        ipp_b = np.full((rows, cols), np.nan, dtype=float)
        ipp_l = np.full((rows, cols), np.nan, dtype=float)

        R_E = 6371000.0  # meters
        h_ion = 450000.0  # 450 km per Get_dif.m

        for col in range(cols):
            for row in range(rows):
                if elevation_rad[row, col] == 0:
                    continue
                ippz = np.arcsin(
                    R_E * np.sin(np.pi / 2.0 - elevation_rad[row, col]) / (R_E + h_ion)
                )
                t = np.pi / 2.0 - elevation_rad[row, col] - ippz
                lat = np.arcsin(
                    np.sin(sb) * np.cos(t) + np.cos(sb) * np.sin(t) * np.cos(azimuth_rad[row, col])
                )
                lon = sl + np.arcsin(
                    np.sin(t) * np.sin(azimuth_rad[row, col]) / np.cos(lat)
                )
                ipp_b[row, col] = lat
                ipp_l[row, col] = lon

        # Compute IPP inter-epoch distances via haversine
        ipp_sphere_r = (EARTH_RADIUS_KM + IONO_HEIGHT_IPP_KM)
        dif = np.full_like(ipp_b, np.nan, dtype=float)
        for col in range(cols):
            for row in range(rows - 1):
                if (
                    np.isfinite(ipp_l[row, col])
                    and np.isfinite(ipp_l[row + 1, col])
                    and np.isfinite(ipp_b[row, col])
                    and np.isfinite(ipp_b[row + 1, col])
                    and ipp_l[row, col] != 0
                    and ipp_l[row + 1, col] != 0
                    and ipp_b[row, col] != 0
                    and ipp_b[row + 1, col] != 0
                ):
                    lon1 = ipp_l[row + 1, col]
                    lat1 = ipp_b[row + 1, col]
                    lon2 = ipp_l[row, col]
                    lat2 = ipp_b[row, col]
                    dlon = lat1 - lat2
                    dlat = lon1 - lon2
                    a = (np.sin(dlat / 2.0) ** 2) + np.cos(lat1) * np.cos(lat2) * (np.sin(dlon / 2.0) ** 2)
                    c = 2.0 * np.arcsin(np.sqrt(a))
                    dif[row, col] = ipp_sphere_r * c

        # cROT = |dSTEC / dif| * 2 per Get_cROT.m / Eq.(11)
        with np.errstate(invalid="ignore", divide="ignore"):
            crot = np.abs(dstec / dif) * 2.0
        return crot, ipp_b, ipp_l

    # Fallback without IPP: use simpler crot_compute
    crot = crot_compute(l4_clean, dt_minutes=config.sampling_interval_s / 60.0)
    return crot, None, None


def _compute_sigma_phi_f(
    gf_phase: np.ndarray,
    config: ScintillationConfig,
    has_precise_products: bool = False,
    elevation_rad: np.ndarray | None = None,
) -> np.ndarray:
    """sigma_phi preprocessing chain per M_ISSION paper Fig.1 and wenxian.pdf."""
    if gf_phase.ndim == 1:
        gf_phase = gf_phase.reshape(-1, 1)

    n_epochs, n_sats = gf_phase.shape

    # 1. Short arc removal
    gf_clean = np.zeros_like(gf_phase, dtype=float)
    for col in range(n_sats):
        gf_clean[:, col] = short_arc_removal(gf_phase[:, col], min_arc=config.sigma_window_epochs)

    # 2. Cycle slip detection per cut_slip_repair.m (Eq.1-2)
    #    Uses elevation-dependent threshold when elevation is available
    gf_slips = np.zeros_like(gf_phase, dtype=bool)
    for col in range(n_sats):
        col_data = gf_clean[:, col]
        if np.sum(np.isfinite(col_data)) < config.sigma_window_epochs:
            continue
        elev_col = None
        if elevation_rad is not None and col < elevation_rad.shape[1]:
            elev_col = elevation_rad[:, col].reshape(-1, 1)
        slips = cycle_slip_detection(col_data.reshape(-1, 1), elevation=elev_col)
        if slips.ndim == 2:
            gf_slips[:, col] = slips[:, 0]
        else:
            gf_slips[:, col] = slips

    # 3. Cycle slip repair per cut_slip_repair.m (Eq.3)
    repaired = np.zeros_like(gf_clean, dtype=float)
    for col in range(n_sats):
        rep = cycle_slip_repair(gf_clean[:, col], gf_slips[:, col])
        repaired[:, col] = rep.ravel() if rep.ndim > 1 else rep

    # 4. Geodetic detrending (linear) -- only with precise products
    if has_precise_products:
        geo = geodetic_detrending(repaired, degree=1)
    else:
        geo = repaired

    # 5. Third-order polynomial detrending per Eq.(4)
    poly = polynomial_detrending(geo, degree=3)

    # 6. 6th-order Butterworth bandpass filter per butterworthband.m
    filtered = butterworth_filter(poly)

    # 7. sigma_phi per get_sigmaphi.m Eq.(5)
    sigma = sigma_phi_from_filtered(filtered, window=config.sigma_window_epochs)

    # 8. Apply cutoff elevation masking
    if elevation_rad is not None:
        cutoff_rad = np.radians(config.cutoff_elevation_deg)
        mask = np.isfinite(elevation_rad) & (elevation_rad < cutoff_rad)
        sigma[mask] = np.nan

    return sigma
