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
    compute_s4c,
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
    s4c: np.ndarray | None = None
    s4c_s2: np.ndarray | None = None
    crot: np.ndarray | None = None
    crot_ipp_b: np.ndarray | None = None
    crot_ipp_l: np.ndarray | None = None
    ipp_b: np.ndarray | None = None
    ipp_l: np.ndarray | None = None
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


def _compute_ppp_l1_correction(
    obs_data,
    sp3_paths: list[str | Path],
    clk_paths: list[str | Path],
    atx_path: str | Path | None,
    gnss_system: str = 'GPS',
    rinex_path: str | Path | None = None,
) -> np.ndarray | None:
    """Compute PPP L1 correction array for SIGMA_PHI_F detrending."""
    from isd.algorithms.ppp_model.nmodel import compute_ppp_correction

    if not obs_data.epoch_times:
        return None

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

    sat_filter = set(obs_data.satellite_ids) if obs_data.satellite_ids else None
    sp3_positions = interpolate_sp3_to_epochs(
        sp3_list, target_seconds, lagrange_order=11, satellite_filter=sat_filter,
    )
    if not sp3_positions:
        return None

    # Build multi-day SP3 position arrays for satellite_position.py.
    # Each SP3 file has epoch_times_seconds relative to its own midnight;
    # convert to seconds relative to the observation day's midnight.
    from datetime import datetime
    first_epoch = obs_data.epoch_times[0]
    obs_midnight = datetime(first_epoch[0], first_epoch[1], first_epoch[2])

    # Collect per-satellite (time, position) pairs across all SP3 files
    sat_time_pos: dict[str, list[tuple[float, np.ndarray]]] = {}

    for sp3_data in sp3_list:
        if sp3_data.first_epoch_dt is None:
            continue
        dt_offset = (sp3_data.first_epoch_dt - obs_midnight).total_seconds()
        offset_epochs = sp3_data.epoch_times_seconds + dt_offset

        for sid_idx, sid in enumerate(sp3_data.satellite_ids):
            if sid not in sat_filter:
                continue
            if sid not in sat_time_pos:
                sat_time_pos[sid] = []
            for ep_i in range(sp3_data.n_epochs):
                sat_time_pos[sid].append((
                    offset_epochs[ep_i],
                    sp3_data.positions_km[ep_i, sid_idx, :],
                ))

    if not sat_time_pos:
        return None

    # Sort by time, deduplicate, and build arrays
    raw_sp3_positions: dict[str, np.ndarray] = {}
    raw_sp3_epochs_per_sat: dict[str, np.ndarray] = {}

    for sid, pairs in sat_time_pos.items():
        pairs.sort(key=lambda x: x[0])
        times: list[float] = []
        positions: list[np.ndarray] = []
        prev_t = float('-inf')
        for t, p in pairs:
            if t > prev_t:  # strictly increasing
                times.append(t)
                positions.append(p)
                prev_t = t
        raw_sp3_positions[sid] = np.array(positions)
        raw_sp3_epochs_per_sat[sid] = np.array(times)

    receiver_xyz = np.array(obs_data.approx_xyz)
    year, month, day = first_epoch[0], first_epoch[1], first_epoch[2]

    # Use gLAB static PPP for precise receiver position (matching MATLAB glab_ppp_solver.m)
    try:
        from isd.algorithms.ppp_model.glab_solver import glab_ppp_position
        rinex_file = str(rinex_path) if rinex_path else None
        if rinex_file:
            precise_xyz = glab_ppp_position(
                rinex_file, sp3_paths, clk_paths, atx_path, obs_data.approx_xyz,
            )
            receiver_xyz = np.array(precise_xyz)
            logger.info("Using PPP receiver XYZ: %.4f %.4f %.4f", *receiver_xyz)
    except Exception as exc:
        logger.warning("gLAB PPP failed (%s), using RINEX header approx_xyz", exc)

    antenna_type = getattr(obs_data, 'antenna_model', None)
    delta_hen = None
    raw_hen = getattr(obs_data, 'antenna_delta_hen', None)
    if raw_hen is not None:
        delta_hen = np.array(raw_hen)

    prange = obs_data.range_l1
    if prange is None:
        prange = np.full((len(target_seconds), len(obs_data.satellite_ids)), 0.070 * LIGHT_SPEED)

    ppp_result = compute_ppp_correction(
        obs_epochs_sec=target_seconds,
        sat_ids=obs_data.satellite_ids,
        sp3_positions_km=raw_sp3_positions,
        sp3_epoch_sec=raw_sp3_epochs_per_sat,
        receiver_xyz=receiver_xyz,
        year=year,
        month=month,
        day=day,
        clk_paths=clk_paths,
        atx_path=atx_path,
        pseudorange_l1=prange,
        antenna_type=antenna_type,
        antenna_delta_hen=delta_hen,
    )
    return ppp_result.l1_correction_m


def compute_scintillation_from_rinex(
    file_path: str | Path,
    config: ScintillationConfig | None = None,
    compute_metrics: list[str] | None = None,
    sp3_paths: list[str | Path] | None = None,
    gnss_system: str = 'GPS',
    clk_paths: list[str | Path] | None = None,
    atx_path: str | Path | None = None,
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

    # Compute IPP coordinates from elevation/azimuth for all metrics
    if (
        elevation_rad is not None
        and azimuth_rad is not None
        and obs_data.approx_xyz is not None
        and len(obs_data.approx_xyz) >= 3
    ):
        result.ipp_b, result.ipp_l = _compute_ipp_coordinates(
            elevation_rad, azimuth_rad, obs_data.approx_xyz,
        )

    # STEC already computed inside _compute_l4_stec for GPS/GAL/BDS;
    # for GLO it was per-satellite
    f1, f2 = _get_system_freqs(gnss_system)
    if gnss_system == 'GLO':
        stec = _compute_stec_glo(l4_clean)
    else:
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
        # Absolute cap: ROTI > 5 TECU/min is physically unrealistic
        # (Pi et al. 1997: extreme scintillation ROTI < 5)
        roti = np.where(np.isfinite(roti) & (np.abs(roti) > 5.0), np.nan, roti)
        result.roti = roti

    if 'IAATR' in compute_metrics:
        # IAATR per Eq.(9): AATR = 2*dSTEC/M
        if elevation_rad is not None:
            iaatr = aatr_from_dstec(dstec, elevation_rad,
                                    earth_radius_km=config.earth_radius_km,
                                    iono_height_km=config.iono_height_km)
        else:
            # Without elevation, estimate AATR using a typical mapping function
            # value (M ~ 2.0 for mid-latitude 30-degree elevation).
            # This provides physically meaningful TECU/min units instead of
            # raw ROT which is in TECU/epoch.
            typical_m = 2.0
            iaatr = rot / typical_m
        # Apply anomaly cleaning to remove cycle slip artifacts
        # (same threshold as AATR per checkAnomaliesaatr.m)
        iaatr = check_anomalies(iaatr, diff_threshold=config.aatr_diff_threshold,
                                min_arc_length=10)
        # Absolute cap: IAATR > 5 TECU/min is physically unrealistic
        # (Sanz et al. 2014: extreme AATR < 2)
        iaatr = np.where(np.isfinite(iaatr) & (np.abs(iaatr) > 5.0), np.nan, iaatr)
        result.iaatr = iaatr

    if 'AATR' in compute_metrics:
        # AATR per Get_AATR.m GPS_AATR lines 208-211 (Eq.9)
        if elevation_rad is not None:
            iaatr = aatr_from_dstec(dstec, elevation_rad,
                                    earth_radius_km=config.earth_radius_km,
                                    iono_height_km=config.iono_height_km)
        else:
            # Without elevation, estimate AATR using a typical mapping function
            # value (M ~ 2.0) to maintain correct TECU/min units.
            typical_m = 2.0
            iaatr = rot / typical_m
        # checkAnomaliesaatr.m: threshold=5.2, min_arc=5
        # Applied for both elevation and non-elevation paths to remove
        # cycle slip residuals and other outliers before RMS aggregation.
        # Use min_arc=5 (vs MATLAB's 10) because elevation NaN gaps create
        # shorter arcs in our pipeline.
        iaatr = check_anomalies(iaatr, diff_threshold=config.aatr_diff_threshold,
                                min_arc_length=5)
        # Absolute cap per-epoch before RMS aggregation
        iaatr = np.where(np.isfinite(iaatr) & (np.abs(iaatr) > 5.0), np.nan, iaatr)
        result.iaatr = iaatr
        # RMS AATR per Get_AATR.m lines 213-218 (Eq.10)
        result.aatr = rms_aatr_hourly(iaatr, hourly_epochs=config.aatr_hourly_epochs)

    if 'SIGMA_PHI_F' in compute_metrics:
        has_precise = getattr(config, 'use_precise_products', False)

        # PPP model correction per model_cor.m is REQUIRED for SIGMA_PHI_F.
        # SP3+CLK+ATX files are mandatory — no fallback polynomial detrend.
        ppp_l1_correction = None
        if clk_paths and sp3_paths and obs_data.approx_xyz is not None:
            try:
                ppp_l1_correction = _compute_ppp_l1_correction(
                    obs_data, sp3_paths, clk_paths, atx_path, gnss_system,
                    rinex_path=file_path,
                )
            except Exception as exc:
                logger.error("PPP correction failed for SIGMA_PHI_F: %s", exc)
        else:
            logger.error(
                "SIGMA_PHI_F requires SP3+CLK+ATX files for PPP model correction. "
                "Missing: SP3=%s, CLK=%s, approx_xyz=%s",
                bool(sp3_paths), bool(clk_paths), obs_data.approx_xyz is not None,
            )

        sigma = _compute_sigma_phi_f(
            phase_l1, phase_l2, f1, f2, config,
            has_precise_products=has_precise,
            elevation_rad=elevation_rad,
            ppp_correction_m=ppp_l1_correction,
        )
        result.sigma_phi_f = sigma

    if 'S4C' in compute_metrics:
        # S4C requires SNR (S1/S2) data from RINEX OBS.
        # If SNR arrays are not available from the reader, result.s4c stays None
        # and the task worker will fall back to synthetic generation.
        snr_l1 = getattr(obs_data, 'snr_l1', None)
        snr_l2 = getattr(obs_data, 'snr_l2', None)
        if snr_l1 is not None and snr_l1.size > 0:
            # Apply elevation mask: zero out SNR for satellites below cutoff
            # (matches IonoMoni apply_elevation_mask_for_S4C)
            if elevation_rad is not None:
                cutoff_rad = np.deg2rad(config.cutoff_elevation_deg)
                mask = (elevation_rad > 0) & (elevation_rad < cutoff_rad)
                snr_l1 = snr_l1.copy()
                snr_l1[mask] = 0.0
                if snr_l2 is not None:
                    snr_l2 = snr_l2.copy()
                    snr_l2[mask] = 0.0

            result.s4c, result.s4c_s2 = compute_s4c(
                snr_l1, snr_l2,
                n_trend=config.s4c_n_trend,
                l_stat=config.s4c_l_stat,
            )

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


def _compute_ipp_coordinates(
    elevation_rad: np.ndarray,
    azimuth_rad: np.ndarray,
    approx_xyz: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute IPP lat/lon in radians from elevation/azimuth and station XYZ.

    Per Get_dif.m: IPP at 450 km ionospheric shell height.
    Returns (ipp_b, ipp_l) arrays in radians, same shape as elevation_rad.
    """
    from isd.algorithms.matlab_metrics import _xyz_to_blh

    sb, sl = _xyz_to_blh(float(approx_xyz[0]), float(approx_xyz[1]), float(approx_xyz[2]))
    rows, cols = elevation_rad.shape
    ipp_b = np.full((rows, cols), np.nan, dtype=float)
    ipp_l = np.full((rows, cols), np.nan, dtype=float)

    R_E = 6371000.0
    h_ion = 450000.0

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

    return ipp_b, ipp_l


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
    # GPS (line 152): STEC = L4 * 1e-3 * para * 1e6  (= L4 * para * 1e3)
    # GLO (line 192): STEC = L4 * para * 1e3
    # BDS (line 224): STEC = L4 * para * 1e3
    # GAL (line 293): STEC = L4 * para * 1e3
    if gnss_system == 'GLO':
        stec = _compute_stec_glo(l4_clean) * 1e3
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
        and len(approx_xyz) >= 3
    ):
        ipp_b, ipp_l = _compute_ipp_coordinates(elevation_rad, azimuth_rad, approx_xyz)

        # Compute IPP inter-epoch distances via haversine
        ipp_sphere_r = (EARTH_RADIUS_KM + IONO_HEIGHT_IPP_KM)
        dif = np.full_like(ipp_b, np.nan, dtype=float)
        rows, cols = ipp_b.shape
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
                    dlat = lat1 - lat2
                    dlon = lon1 - lon2
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


def _detect_and_mark_cycle_slips(phase_m: np.ndarray, threshold_m: float = 2.0) -> np.ndarray:
    """Detect cycle slips as sudden jumps in PPP-corrected phase.

    Per cut_slip_repair.m: cycle slips cause discontinuities in carrier phase.
    The MATLAB pipeline uses GF+MW combinations for slip detection (cut_slip_repair.m),
    but here we apply a simpler forward-difference threshold on the PPP-corrected
    L1 phase. Normal ionospheric phase fluctuations between 30s epochs are well
    below 2m; jumps exceeding this indicate slips or PPP correction failures.

    Returns a copy of phase_m with NaN inserted at slip boundaries, which causes
    the Butterworth filter to process each sub-arc independently.
    """
    out = phase_m.copy()
    n_epochs, n_sats = out.shape

    for col in range(n_sats):
        col_data = out[:, col]
        valid = np.isfinite(col_data)
        if valid.sum() < 2:
            continue

        # Forward difference
        diff = np.full(n_epochs, np.nan)
        diff[1:] = np.abs(np.diff(col_data))

        slip_mask = np.zeros(n_epochs, dtype=bool)
        slip_mask[1:] = (np.isfinite(diff[1:]) & (diff[1:] > threshold_m))

        if not slip_mask.any():
            continue

        slip_indices = np.where(slip_mask)[0]
        for idx in slip_indices:
            out[idx, col] = np.nan

    return out


def _compute_sigma_phi_f(
    phase_l1: np.ndarray,
    phase_l2: np.ndarray,
    f1: float,
    f2: float,
    config: ScintillationConfig,
    has_precise_products: bool = False,
    elevation_rad: np.ndarray | None = None,
    ppp_correction_m: np.ndarray | None = None,
) -> np.ndarray:
    """sigma_phi per M_ISSION model_cor.m + butterworthband.m + get_sigmaphi.m.

    Pipeline (matching MATLAB):
      L1 phase (cycles) -> multiply by wavelength -> subtract PPP correction
      (per model_cor.m) -> cycle slip detection ->
      6th-order Butterworth bandpass [0.001, 0.015] Hz
      (per butterworthband.m, with internal 3rd-order detrend per line 52) ->
      sliding-window population std, window=10 (per get_sigmaphi.m Eq.5)

    PPP correction (SP3+CLK+ATX) is REQUIRED per model_cor.m.
    Returns all-NaN if unavailable or if shape mismatches.
    """
    # L1 phase in metres per obsToobs2.m / get_sigmaphi.m
    wavelength = LIGHT_SPEED / f1
    phase_m = phase_l1 * wavelength

    if phase_m.ndim == 1:
        phase_m = phase_m.reshape(-1, 1)

    phase_m = phase_m.copy()
    phase_m[phase_m == 0] = np.nan

    n_epochs, n_sats = phase_m.shape

    # PPP model correction is REQUIRED per model_cor.m
    if ppp_correction_m is None:
        logger.error(
            "SIGMA_PHI_F requires PPP model correction (SP3+CLK+ATX files). "
            "No precise products provided — cannot compute sigma_phi."
        )
        return np.full((n_epochs, n_sats), np.nan)

    # Subtract PPP model correction per model_cor.m correct_observations():
    #   corrected_l1 = raw_l1 - model_l1_error
    ppp_corr = ppp_correction_m.copy()
    if ppp_corr.ndim == 1:
        ppp_corr = ppp_corr.reshape(-1, 1)

    # Shape safety: model_cor.m iterates over matching (row, col) pairs.
    # If shapes differ, the correction cannot be applied correctly.
    if ppp_corr.shape != phase_m.shape:
        logger.error(
            "SIGMA_PHI_F: PPP correction shape %s != phase shape %s. "
            "Cannot compute sigma_phi.",
            ppp_corr.shape, phase_m.shape,
        )
        return np.full((n_epochs, n_sats), np.nan)

    phase_m = phase_m - ppp_corr
    # Per model_cor.m: where model error is 0 or NaN, set observation to NaN
    phase_m[np.isnan(ppp_corr)] = np.nan
    phase_m[ppp_corr == 0] = np.nan

    # Cycle slip detection: mark large discontinuities as NaN.
    # This is equivalent to cut_slip_repair.m splitting arcs at slip points.
    # Threshold 2m is conservative — normal ionospheric phase change between
    # 30s epochs is well below 1m even during strong scintillation.
    phase_m = _detect_and_mark_cycle_slips(phase_m, threshold_m=2.0)

    # 6th-order Butterworth bandpass filter per butterworthband.m.
    # Internally applies 3rd-order polynomial detrend per line 52:
    #   segment2 = detrend(segment, 3)
    #   filtered_segment = filtfilt(b, a, segment2)
    # Segments shorter than 6*order=36 epochs are set to NaN (lines 55-56).
    filtered = butterworth_filter(phase_m)

    # Post-filter sanity: bandpass filter output represents ionospheric
    # phase fluctuations. Even during extreme scintillation, filtered
    # amplitude should not exceed a few metres. Larger values indicate
    # unresolved cycle slips, PPP correction failures, or filter edge
    # artifacts (filtfilt transient at segment boundaries).
    FILTERED_AMPLITUDE_CAP = 5.0  # metres
    filtered[np.isfinite(filtered) & (np.abs(filtered) > FILTERED_AMPLITUDE_CAP)] = np.nan

    # sigma_phi per get_sigmaphi.m sigmaphi subfunction (Eq.5):
    #   for m = 11:2881
    #       sigmaphi(m-1, i) = std(data(m-10:m-1, i), 1)
    # Population std (ddof=0), window=10 epochs, output offset=1
    sigma = sigma_phi_from_filtered(filtered, window=config.sigma_window_epochs)

    # Final sanity cap: sigma_phi above 1.0 m is physically implausible
    # for ionospheric scintillation (threshold is 0.05 m per Ahmed 2015).
    # Catches remaining edge artifacts or insufficient window data.
    SIGMA_CAP = 1.0  # metres
    sigma[np.isfinite(sigma) & (sigma > SIGMA_CAP)] = np.nan

    return sigma
