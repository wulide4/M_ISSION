"""Satellite position computation with time-of-flight and Earth rotation.

Reference: M_ISSION cal_sat.m.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline

from isd.algorithms.ppp_model.clk_parser import ClkData, interpolate_clock

logger = logging.getLogger(__name__)

C = 299792458.0  # m/s
OMEGA_EARTH = 7.2921151467e-5  # rad/s


@dataclass
class SatelliteState:
    position_m: np.ndarray    # (3,) ECEF meters
    velocity_m_s: np.ndarray  # (3,) ECEF m/s
    clock_bias_s: float       # seconds
    tof_s: float              # total signal travel time


def _interp_sp3_positions(
    sp3_times_sec: np.ndarray,
    sp3_pos_km: np.ndarray,
    target_sec: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Cubic spline interpolation of SP3 positions + velocity via derivative.

    Args:
        sp3_times_sec: (N,) SP3 epoch times in seconds
        sp3_pos_km: (N, 3) positions in km
        target_sec: (M,) target times in seconds

    Returns:
        (positions_m (M,3), velocities_m_s (M,3))
    """
    valid = np.all(np.isfinite(sp3_pos_km), axis=1)
    if valid.sum() < 4:
        return (np.full((len(target_sec), 3), np.nan),
                np.full((len(target_sec), 3), np.nan))

    t = sp3_times_sec[valid]
    p = sp3_pos_km[valid] * 1000.0  # km -> m

    pos_out = np.full((len(target_sec), 3), np.nan)
    vel_out = np.full((len(target_sec), 3), np.nan)

    for dim in range(3):
        try:
            cs = CubicSpline(t, p[:, dim])
            in_range = (target_sec >= t[0]) & (target_sec <= t[-1])
            pos_out[in_range, dim] = cs(target_sec[in_range])
            vel_out[in_range, dim] = cs(target_sec[in_range], 1)
        except Exception:
            pass

    return pos_out, vel_out


def _earth_rotation(pos_m: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rotate position around Z-axis by angle_rad (matching rotation.m axis=3)."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    return (R @ pos_m.reshape(3, 1)).ravel()


def compute_satellite_states(
    obs_epochs_sec: np.ndarray,
    sat_ids: list[str],
    sp3_positions_km: dict[str, np.ndarray],
    sp3_epoch_sec: np.ndarray,
    clk_data: ClkData,
    pseudorange_m: np.ndarray,
    receiver_xyz: np.ndarray,
) -> dict[str, list[SatelliteState | None]]:
    """Compute satellite states per cal_sat.m.

    For each epoch and satellite:
    1. ToF = pseudorange / c
    2. Transmit time = obs_time - ToF
    3. Interpolate clock at transmit time
    4. Corrected transmit time = transmit_time - clock_bias
    5. Interpolate SP3 position at corrected transmit time
    6. Earth rotation correction
    7. Velocity via spline derivative

    Args:
        obs_epochs_sec: (T,) observation epoch seconds from midnight
        sat_ids: list of satellite ID strings
        sp3_positions_km: {sat_id: (N_sp3, 3)} from SP3 interpolation
        sp3_epoch_sec: (N_sp3,) SP3 epoch times in seconds
        clk_data: parsed clock data
        pseudorange_m: (T, n_sat) pseudorange in meters
        receiver_xyz: (3,) receiver ECEF position in meters

    Returns:
        {sat_id: [SatelliteState | None for each epoch]}
    """
    n_epochs = len(obs_epochs_sec)
    result: dict[str, list[SatelliteState | None]] = {}

    for col, sat_id in enumerate(sat_ids):
        states: list[SatelliteState | None] = [None] * n_epochs

        if sat_id not in sp3_positions_km:
            result[sat_id] = states
            continue

        sp3_pos = sp3_positions_km[sat_id]
        if sp3_pos is None or np.all(np.isnan(sp3_pos)):
            result[sat_id] = states
            continue

        # Pre-compute clock bias for this satellite at all target times
        # We'll refine per-epoch using iterative ToF
        if pseudorange_m is not None:
            pr_col = pseudorange_m[:, col] if pseudorange_m.ndim == 2 else pseudorange_m
        else:
            pr_col = None

        for row in range(n_epochs):
            pr = pr_col[row] if pr_col is not None else np.nan
            if not np.isfinite(pr) or pr <= 0:
                # Use default 70ms ToF when no pseudorange available
                pr = 0.070 * C

            obs_t = obs_epochs_sec[row]

            obs_t = obs_epochs_sec[row]

            # Step 1: initial ToF from pseudorange
            tof_0 = pr / C

            # Step 2: approximate transmit time
            tx_t = obs_t - tof_0

            # Step 3: interpolate clock at transmit time
            clk_bias = interpolate_clock(clk_data, sat_id, np.array([tx_t]))[0]
            if not np.isfinite(clk_bias):
                # Try using obs time directly for clock
                clk_bias = interpolate_clock(clk_data, sat_id, np.array([obs_t]))[0]
                if not np.isfinite(clk_bias):
                    continue

            # Step 4: corrected transmit time
            tx_t_corr = tx_t - clk_bias

            # Step 5: interpolate position at corrected transmit time
            pos_m, vel_m = _interp_sp3_positions(
                sp3_epoch_sec, sp3_pos, np.array([tx_t_corr]),
            )
            if np.any(np.isnan(pos_m[0])):
                continue

            sat_pos = pos_m[0]
            sat_vel = vel_m[0]

            # Step 6: Earth rotation correction
            # Recompute actual ToF from geometric range
            geom_range = np.linalg.norm(sat_pos - receiver_xyz)
            total_tof = geom_range / C
            er_angle = total_tof * OMEGA_EARTH  # radians
            sat_pos = _earth_rotation(sat_pos, er_angle)

            # Recompute velocity position after rotation
            # (approximate: rotate velocity too)
            c_er, s_er = np.cos(er_angle), np.sin(er_angle)
            R_er = np.array([[c_er, s_er, 0], [-s_er, c_er, 0], [0, 0, 1]])
            sat_vel = (R_er @ sat_vel.reshape(3, 1)).ravel()

            # Recompute geometric range after rotation
            geom_range = np.linalg.norm(sat_pos - receiver_xyz)

            states[row] = SatelliteState(
                position_m=sat_pos,
                velocity_m_s=sat_vel,
                clock_bias_s=clk_bias,
                tof_s=total_tof,
            )

        result[sat_id] = states

    return result
