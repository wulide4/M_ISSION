"""Central PPP correction assembly per nmodel.m.

Computes all model correction terms for each epoch x satellite and returns
per-frequency correction arrays in metres that can be subtracted from carrier
phase (in metres) to remove geometric/trend effects.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from isd.algorithms.metrics import LIGHT_SPEED, GPS_F1, GPS_F2
from isd.algorithms.ppp_model.celestial_body import moon_position_ecef, sun_position_ecef
from isd.algorithms.ppp_model.clk_parser import ClkData, parse_clk
from isd.algorithms.ppp_model.corrections import (
    phase_windup,
    receiver_apc,
    receiver_arp,
    relativistic_clock,
    satellite_apc,
    shapiro_delay,
    solid_earth_tides,
    troposphere_gmf,
)
from isd.algorithms.ppp_model.antex_parser import AntexData, get_sat_pco_meters, get_rcv_pco_meters, parse_antex
from isd.algorithms.ppp_model.satellite_position import compute_satellite_states
from isd.algorithms.ppp_model.time_utils import calendar_to_mjd

logger = logging.getLogger(__name__)

# Wavelengths (metres)
_L1_WAVELENGTH = LIGHT_SPEED / GPS_F1
_L2_WAVELENGTH = LIGHT_SPEED / GPS_F2


@dataclass
class PppCorrectionResult:
    """Per-frequency PPP correction arrays in metres."""
    l1_correction_m: np.ndarray   # (T, n_sat) total L1 correction
    l2_correction_m: np.ndarray   # (T, n_sat) total L2 correction


def _get_sat_prn(sat_id: str) -> int:
    """Extract PRN number from sat_id like 'G01' -> 1."""
    try:
        return int(sat_id[1:])
    except (ValueError, IndexError):
        return 0


def _get_sys_char(sat_id: str) -> str:
    """Get system character from sat_id: 'G', 'R', 'E', or 'C'."""
    return sat_id[0] if sat_id else 'G'


def _get_rcv_apc_index(sat_id: str, freq_idx: int) -> str:
    """Get receiver APC frequency code for a satellite and frequency index.

    GLONASS (R) uses R01/R02; others use G01/G02.
    """
    if _get_sys_char(sat_id) == 'R':
        return 'R01' if freq_idx == 1 else 'R02'
    return 'G01' if freq_idx == 1 else 'G02'


def compute_ppp_correction(
    obs_epochs_sec: np.ndarray,
    sat_ids: list[str],
    sp3_positions_km: dict[str, np.ndarray],
    sp3_epoch_sec: np.ndarray | dict[str, np.ndarray],
    receiver_xyz: np.ndarray,
    year: int,
    month: int,
    day: int,
    clk_paths: list[str | Path] | None = None,
    atx_path: str | Path | None = None,
    pseudorange_l1: np.ndarray | None = None,
    antenna_type: str | None = None,
    antenna_delta_hen: np.ndarray | None = None,
    pressure_hpa: float = 1013.25,
) -> PppCorrectionResult:
    """Compute full PPP model correction per nmodel.m.

    For each epoch x satellite, sums: geometric_range + sat_clock + sat_APC +
    rec_APC + rec_ARP + rel_clock + windup + tropo + shapiro + solid_tide.

    Args:
        obs_epochs_sec: (T,) observation epoch seconds from midnight
        sat_ids: list of satellite ID strings
        sp3_positions_km: {sat_id: (N_sp3, 3)} positions in km from SP3
        sp3_epoch_sec: (N_sp3,) SP3 epoch times in seconds, or a dict
            {sat_id: (N,)} for per-satellite epochs when merging multi-day SP3
        receiver_xyz: (3,) receiver ECEF in metres
        year, month, day: date for MJD computation
        clk_paths: paths to CLK files (at least one required)
        atx_path: path to ANTEX file (optional)
        pseudorange_l1: (T, n_sat) L1 pseudorange in metres (for ToF)
        antenna_type: receiver antenna type string from RINEX header
        antenna_delta_hen: (3,) [H, E, N] antenna delta from RINEX header
        pressure_hpa: surface pressure in hPa

    Returns:
        PppCorrectionResult with l1_correction_m and l2_correction_m arrays.
    """
    n_epochs = len(obs_epochs_sec)
    n_sats = len(sat_ids)

    l1_corr = np.full((n_epochs, n_sats), np.nan)
    l2_corr = np.full((n_epochs, n_sats), np.nan)

    # Parse clock data
    clk_data: ClkData | None = None
    if clk_paths:
        for cp in clk_paths:
            try:
                clk_data = parse_clk(cp)
                break
            except Exception as exc:
                logger.warning("Failed to parse CLK %s: %s", cp, exc)

    # Parse ANTEX
    antex: AntexData | None = None
    if atx_path:
        try:
            antex = parse_antex(atx_path, antenna_type=antenna_type)
        except Exception as exc:
            logger.warning("Failed to parse ANTEX %s: %s", atx_path, exc)

    # Compute satellite states
    if pseudorange_l1 is None:
        # Use 70 ms default ToF as fallback
        pseudorange_l1 = np.full((n_epochs, n_sats), 0.070 * LIGHT_SPEED)

    # Handle per-satellite or global epoch arrays
    per_sat_epochs: dict[str, np.ndarray]
    if isinstance(sp3_epoch_sec, dict):
        per_sat_epochs = sp3_epoch_sec
    else:
        per_sat_epochs = {sid: sp3_epoch_sec for sid in sat_ids}

    # Compute states per satellite (to use correct per-satellite epoch arrays)
    all_sat_states: dict[str, list] = {}
    for col, sid in enumerate(sat_ids):
        if sid not in sp3_positions_km:
            continue
        sat_pos_only = {sid: sp3_positions_km[sid]}
        sat_epoch = per_sat_epochs.get(sid, sp3_epoch_sec if isinstance(sp3_epoch_sec, np.ndarray) else np.array([]))
        pr_col = pseudorange_l1[:, col:col + 1] if pseudorange_l1.ndim == 2 else pseudorange_l1

        states = compute_satellite_states(
            obs_epochs_sec, [sid], sat_pos_only, sat_epoch,
            clk_data or ClkData([], {}, np.array([]), 30.0, 0),
            pr_col, receiver_xyz,
        )
        all_sat_states[sid] = states.get(sid, [None] * n_epochs)

    # Per-satellite wind-up state tracking
    windup_state: dict[str, float] = {sid: 0.0 for sid in sat_ids}

    # Base MJD for the day (at midnight)
    mjd_midnight = calendar_to_mjd(year, month, day, 0, 0, 0.0)

    for col, sat_id in enumerate(sat_ids):
        states = all_sat_states.get(sat_id)
        if not states:
            continue

        prn = _get_sat_prn(sat_id)

        for row in range(n_epochs):
            st = states[row]
            if st is None:
                continue

            s_xyz = st.position_m
            v_xyz = st.velocity_m_s
            clk_bias = st.clock_bias_s

            # MJD at this epoch (for celestial body / tropo)
            obs_t = obs_epochs_sec[row]
            mjd = mjd_midnight + obs_t / 86400.0

            # Celestial bodies at TT (~51.184 s offset from GPS)
            mjd_tt = mjd + 51.184 / 86400.0
            try:
                sun_xyz = sun_position_ecef(mjd_tt)
                moon_xyz = moon_position_ecef(mjd_tt)
            except Exception:
                sun_xyz = np.zeros(3)
                moon_xyz = np.zeros(3)

            # --- Individual correction terms ---

            # Geometric range
            geom_range = float(np.linalg.norm(s_xyz - receiver_xyz))

            # Satellite clock (negated, in metres)
            sat_clock_m = -(clk_bias * LIGHT_SPEED)

            # Relativistic clock (negated per nmodel.m line 187)
            try:
                rel_clk = -(relativistic_clock(s_xyz, v_xyz))
            except Exception:
                rel_clk = 0.0

            # Troposphere
            try:
                tropo = troposphere_gmf(receiver_xyz, s_xyz, mjd, pressure_hpa)
            except Exception:
                tropo = 0.0

            # Shapiro delay
            try:
                shapiro = shapiro_delay(receiver_xyz, s_xyz)
            except Exception:
                shapiro = 0.0

            # Solid Earth tides
            try:
                solid = solid_earth_tides(receiver_xyz, s_xyz, sun_xyz, moon_xyz)
            except Exception:
                solid = 0.0

            # Receiver ARP
            try:
                arp = receiver_arp(s_xyz, receiver_xyz, antenna_delta_hen)
            except Exception:
                arp = 0.0

            # --- L1 frequency-dependent terms ---
            pco_l1 = get_sat_pco_meters(antex, sat_id, 'L1') if antex else None
            try:
                sat_apc_l1 = -(satellite_apc(s_xyz, receiver_xyz, sun_xyz, pco_l1, None, 1, prn))
            except Exception:
                sat_apc_l1 = 0.0

            rcv_pco_l1 = None
            if antex and antenna_type:
                fc = _get_rcv_apc_index(sat_id, 1)
                rcv_pco_l1 = get_rcv_pco_meters(antex, antenna_type, fc)
            try:
                rec_apc_l1 = receiver_apc(s_xyz, receiver_xyz, rcv_pco_l1)
            except Exception:
                rec_apc_l1 = 0.0

            # Phase wind-up L1
            prev = windup_state[sat_id]
            try:
                wup_rad = phase_windup(receiver_xyz, s_xyz, sun_xyz, prev)
                windup_state[sat_id] = wup_rad
                windup_l1_m = (wup_rad / (2.0 * np.pi)) * _L1_WAVELENGTH
            except Exception:
                windup_l1_m = 0.0

            # Model correction including geometric range (matching MATLAB model_cor.m
            # second correction pass with len values = model(:,14)).
            total_l1 = (geom_range + sat_clock_m + sat_apc_l1 + rec_apc_l1 +
                        arp + rel_clk + windup_l1_m + tropo + shapiro + solid)
            l1_corr[row, col] = total_l1

            # --- L2 frequency-dependent terms ---
            pco_l2 = get_sat_pco_meters(antex, sat_id, 'L2') if antex else None
            try:
                sat_apc_l2 = -(satellite_apc(s_xyz, receiver_xyz, sun_xyz, pco_l1, pco_l2, 2, prn))
            except Exception:
                sat_apc_l2 = 0.0

            rcv_pco_l2 = None
            if antex and antenna_type:
                fc = _get_rcv_apc_index(sat_id, 2)
                rcv_pco_l2 = get_rcv_pco_meters(antex, antenna_type, fc)
            try:
                rec_apc_l2 = receiver_apc(s_xyz, receiver_xyz, rcv_pco_l2)
            except Exception:
                rec_apc_l2 = 0.0

            # Phase wind-up L2 (same angle, different wavelength)
            windup_l2_m = (windup_state[sat_id] / (2.0 * np.pi)) * _L2_WAVELENGTH

            total_l2 = (geom_range + sat_clock_m + sat_apc_l2 + rec_apc_l2 +
                        arp + rel_clk + windup_l2_m + tropo + shapiro + solid)
            l2_corr[row, col] = total_l2

    logger.info("PPP correction computed: %d epochs x %d sats, "
                "median L1 corr = %.1f m",
                n_epochs, n_sats, np.nanmedian(l1_corr) if np.any(np.isfinite(l1_corr)) else 0.0)

    return PppCorrectionResult(l1_correction_m=l1_corr, l2_correction_m=l2_corr)
