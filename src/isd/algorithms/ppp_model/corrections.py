"""PPP correction terms: APC, ARP, wind-up, Shapiro, solid tides, troposphere.

Reference: M_ISSION sat_apc.m, rec_apc.m, rec_arp.m, wind_up.m, rpath.m,
          solid.m, rel_clk.m, Trop_GMF.m, gmf_f_hu.m.
"""
from __future__ import annotations

import logging
import math

import numpy as np

from isd.algorithms.ppp_model.coordinates import build_enu_rotation, xyz_to_blh

logger = logging.getLogger(__name__)

C = 299792458.0  # m/s


# ---------------------------------------------------------------------------
# Satellite antenna phase centre correction  (ref: sat_apc.m)
# ---------------------------------------------------------------------------

def satellite_apc(
    s_xyz: np.ndarray,
    r_xyz: np.ndarray,
    sun_xyz: np.ndarray,
    pco_l1_m: np.ndarray | None,
    pco_l2_m: np.ndarray | None,
    freq_idx: int,
    sat_prn: int,
) -> float:
    """Satellite APC correction in metres.

    Args:
        s_xyz: satellite ECEF (3,) metres
        r_xyz: receiver ECEF (3,) metres
        sun_xyz: sun ECEF (3,) metres
        pco_l1_m: [north, east, up] metres for L1, or None
        pco_l2_m: [north, east, up] metres for L2, or None
        freq_idx: 1 for L1, 2 for L2
        sat_prn: satellite PRN number (for conventional defaults)

    Returns:
        APC range correction in metres.
    """
    los = r_xyz - s_xyz
    los = los / np.linalg.norm(los)

    # Satellite body frame
    k = -s_xyz / np.linalg.norm(s_xyz)
    rs = sun_xyz - s_xyz
    e = rs / np.linalg.norm(rs)
    j = np.cross(k, e)
    j = j / np.linalg.norm(j)
    i = np.cross(j, k)
    # sf rows are body-frame basis vectors in ECEF
    sf = np.array([i, j, k])  # (3,3)

    de = pco_l1_m if freq_idx == 1 else pco_l2_m

    # Conventional defaults for missing PCO
    if de is None or np.any(np.isnan(de)):
        if 58 < sat_prn < 89:  # Galileo
            de = np.array([0.2, 0.0, 0.6])
        elif 88 < sat_prn < 93:  # BeiDou
            de = np.array([0.6, 0.0, 1.1])
        else:
            return 0.0

    # Solve body-frame PCO: sf @ rk = de  =>  rk = sf^-1 @ de
    rk = np.linalg.solve(sf, de)
    return float(np.dot(rk, los))


# ---------------------------------------------------------------------------
# Receiver antenna phase centre correction  (ref: rec_apc.m)
# ---------------------------------------------------------------------------

def receiver_apc(
    s_xyz: np.ndarray,
    r_xyz: np.ndarray,
    pco_m: np.ndarray | None,
) -> float:
    """Receiver APC correction in metres.

    Args:
        s_xyz: satellite ECEF (3,)
        r_xyz: receiver ECEF (3,)
        pco_m: [north, east, up] PCO in metres (from ANTEX), or None

    Returns:
        APC range correction in metres.
    """
    if pco_m is None:
        return 0.0

    los = r_xyz - s_xyz
    los = los / np.linalg.norm(los)

    lat, lon, _ = xyz_to_blh(float(r_xyz[0]), float(r_xyz[1]), float(r_xyz[2]))
    R = build_enu_rotation(lat, lon)  # columns: E, N, Up in ECEF

    # ANTEX gives [north, east, up] — reorder to [east, north, up]
    enu = np.array([pco_m[1], pco_m[0], pco_m[2]])
    p = R @ enu
    return float(np.dot(p, los))


# ---------------------------------------------------------------------------
# Receiver antenna reference point correction  (ref: rec_arp.m)
# ---------------------------------------------------------------------------

def receiver_arp(
    s_xyz: np.ndarray,
    r_xyz: np.ndarray,
    delta_hen: np.ndarray | None,
) -> float:
    """Receiver ARP (DELTA H/E/N) correction in metres.

    Args:
        s_xyz: satellite ECEF (3,)
        r_xyz: receiver ECEF (3,)
        delta_hen: [H, E, N] antenna delta from RINEX header, or None

    Returns:
        ARP range correction in metres.
    """
    if delta_hen is None:
        return 0.0

    los = r_xyz - s_xyz
    los = los / np.linalg.norm(los)

    lat, lon, _ = xyz_to_blh(float(r_xyz[0]), float(r_xyz[1]), float(r_xyz[2]))
    R = build_enu_rotation(lat, lon)

    # [H, E, N] -> ENU = [E, N, U] where U=H
    enu = np.array([delta_hen[1], delta_hen[2], delta_hen[0]])
    p = R @ enu
    return float(np.dot(p, los))


# ---------------------------------------------------------------------------
# Relativistic clock correction  (ref: rel_clk.m)
# ---------------------------------------------------------------------------

def relativistic_clock(s_xyz: np.ndarray, v_xyz: np.ndarray) -> float:
    """Relativistic clock correction in metres.

    rclk = -2 * dot(pos, vel) / c
    """
    return float(-2.0 * np.dot(s_xyz, v_xyz) / C)


# ---------------------------------------------------------------------------
# Phase wind-up  (ref: wind_up.m, Wu et al. 2005)
# ---------------------------------------------------------------------------

def phase_windup(
    rec: np.ndarray,
    sat: np.ndarray,
    sun: np.ndarray,
    prev: float,
) -> float:
    """Phase wind-up correction in radians.

    Args:
        rec: receiver ECEF (3,) metres
        sat: satellite ECEF (3,) metres
        sun: sun ECEF (3,) metres
        prev: previous epoch wind-up in radians (for continuity)

    Returns:
        Wind-up in radians.
    """
    # Satellite body frame
    esun = sun - sat
    esun = esun / np.linalg.norm(esun)
    ez = -sat / np.linalg.norm(sat)
    ey = np.cross(ez, esun)
    ey = ey / np.linalg.norm(ey)
    ex = np.cross(ey, ez)
    ex = ex / np.linalg.norm(ex)

    xs = ex
    ys = ey

    # Receiver frame from geodetic
    phi, lam, _ = xyz_to_blh(float(rec[0]), float(rec[1]), float(rec[2]))
    xr = np.array([
        -math.sin(phi) * math.cos(lam),
        -math.sin(phi) * math.sin(lam),
        math.cos(phi),
    ])
    yr = np.array([math.sin(lam), -math.cos(lam), 0.0])

    k = rec - sat
    k = k / np.linalg.norm(k)

    Ds = xs - k * np.dot(k, xs) - np.cross(k, ys)
    Dr = xr - k * np.dot(k, xr) + np.cross(k, yr)

    norm_Ds = np.linalg.norm(Ds)
    norm_Dr = np.linalg.norm(Dr)
    if norm_Ds < 1e-30 or norm_Dr < 1e-30:
        return prev

    wup = math.acos(np.clip(np.dot(Ds, Dr) / norm_Ds / norm_Dr, -1.0, 1.0))
    if np.dot(k, np.cross(Ds, Dr)) < 0:
        wup = -wup

    # Maintain continuity with previous epoch
    wup = 2.0 * math.pi * math.floor((prev - wup) / (2.0 * math.pi) + 0.5) + wup
    return wup


# ---------------------------------------------------------------------------
# Shapiro delay  (ref: rpath.m)
# ---------------------------------------------------------------------------

def shapiro_delay(r_xyz: np.ndarray, s_xyz: np.ndarray) -> float:
    """Shapiro (gravitational) delay in metres.

    rpath = (2*mu/c^2) * log((rsat + rrec + rrs) / (rsat + rrec - rrs))
    """
    mu = 3986004.418e8  # m^3/s^2

    rsat = np.linalg.norm(s_xyz)
    rrec = np.linalg.norm(r_xyz)
    rrs = np.linalg.norm(s_xyz - r_xyz)

    denom = rsat + rrec - rrs
    if abs(denom) < 1e-10:
        return 0.0

    return float((2.0 * mu / (C * C)) * math.log((rsat + rrec + rrs) / denom))


# ---------------------------------------------------------------------------
# Solid Earth tides  (ref: solid.m)
# ---------------------------------------------------------------------------

def solid_earth_tides(
    r_xyz: np.ndarray,
    s_xyz: np.ndarray,
    sun_xyz: np.ndarray,
    moon_xyz: np.ndarray,
) -> float:
    """Solid Earth tide range correction in metres.

    IERS degree-2/3 with Love numbers.
    """
    l_vec = r_xyz - s_xyz
    los = l_vec / np.linalg.norm(l_vec)

    h0 = 0.6078; h2 = -0.0006; h3 = 0.292
    l0 = 0.0847; l2 = 0.0002;  l3 = 0.015

    MS2E = 332946.0
    MM2E = 0.01230002
    re = 6378137.0

    lat_r, _, _ = xyz_to_blh(float(r_xyz[0]), float(r_xyz[1]), float(r_xyz[2]))
    trm = 3.0 * math.sin(lat_r) ** 2 - 1.0
    h = h0 + h2 * trm
    lv = l0 + l2 * trm

    sun_dist = np.linalg.norm(sun_xyz)
    moon_dist = np.linalg.norm(moon_xyz)
    rec_dist = np.linalg.norm(r_xyz)

    sun_uni = sun_xyz / sun_dist
    moon_uni = moon_xyz / moon_dist
    rec_uni = r_xyz / rec_dist

    dot_SR = np.dot(sun_uni, rec_uni)
    dot_MR = np.dot(moon_uni, rec_uni)

    a_sun = sun_uni - dot_SR * rec_uni
    a_moon = moon_uni - dot_MR * rec_uni

    DRS = re ** 4 / sun_dist ** 3
    DRM = re ** 4 / moon_dist ** 3
    DRM2 = re ** 5 / moon_dist ** 4

    # Degree 2 Sun
    s1 = (3.0 * dot_SR ** 2 - 1.0) / 2.0
    d2s = MS2E * DRS * (h * rec_uni * s1 + 3.0 * lv * dot_SR * a_sun)

    # Degree 2 Moon
    s2 = (3.0 * dot_MR ** 2 - 1.0) / 2.0
    d2m = MM2E * DRM * (h * rec_uni * s2 + 3.0 * lv * dot_MR * a_moon)

    # Degree 3 Moon
    s3 = 2.5 * dot_MR ** 3 - 1.5 * dot_MR
    s4 = 7.5 * dot_MR ** 2 - 1.5
    d3m = MM2E * DRM2 * (h3 * rec_uni * s3 + l3 * s4 * a_moon)

    stide = d2s + d2m + d3m
    return float(np.dot(stide, los))


# ---------------------------------------------------------------------------
# GMF mapping function  (ref: gmf_f_hu.m)
# ---------------------------------------------------------------------------

# GMF spherical-harmonic coefficients (55 elements each, nmax=9)
_AH_MEAN = [
    1.2517e2, 8.503e-1, 6.936e-2, -6.760e0, 1.771e-1,
    1.130e-2, 5.963e-1, 1.808e-2, 2.801e-3, -1.414e-3,
    -1.212e0, 9.300e-2, 3.683e-3, 1.095e-3, 4.671e-5,
    3.959e-1, -3.867e-2, 5.413e-3, -5.289e-4, 3.229e-4,
    2.067e-5, 3.000e-1, 2.031e-2, 5.900e-3, 4.573e-4,
    -7.619e-5, 2.327e-6, 3.845e-6, 1.182e-1, 1.158e-2,
    5.445e-3, 6.219e-5, 4.204e-6, -2.093e-6, 1.540e-7,
    -4.280e-8, -4.751e-1, -3.490e-2, 1.758e-3, 4.019e-4,
    -2.799e-6, -1.287e-6, 5.468e-7, 7.580e-8, -6.300e-9,
    -1.160e-1, 8.301e-3, 8.771e-4, 9.955e-5, -1.718e-6,
    -2.012e-6, 1.170e-8, 1.790e-8, -1.300e-9, 1.000e-10,
]

_BH_MEAN = [
    0.0, 0.0, 3.249e-2, 0.0, 3.324e-2,
    1.850e-2, 0.0, -1.115e-1, 2.519e-2, 4.923e-3,
    0.0, 2.737e-2, 1.595e-2, -7.332e-4, 1.933e-4,
    0.0, -4.796e-2, 6.381e-3, -1.599e-4, -3.685e-4,
    1.815e-5, 0.0, 7.033e-2, 2.426e-3, -1.111e-3,
    -1.357e-4, -7.828e-6, 2.547e-6, 0.0, 5.779e-3,
    3.133e-3, -5.312e-4, -2.028e-5, 2.323e-7, -9.100e-8,
    -1.650e-8, 0.0, 3.688e-2, -8.638e-4, -8.514e-5,
    -2.828e-5, 5.403e-7, 4.390e-7, 1.350e-8, 1.800e-9,
    0.0, -2.736e-2, -2.977e-4, 8.113e-5, 2.329e-7,
    8.451e-7, 4.490e-8, -8.100e-9, -1.500e-9, 2.000e-10,
]

_AH_AMP = [
    -2.738e-1, -2.837e0, 1.298e-2, -3.588e-1, 2.413e-2,
    3.427e-2, -7.624e-1, 7.272e-2, 2.160e-2, -3.385e-3,
    4.424e-1, 3.722e-2, 2.195e-2, -1.503e-3, 2.426e-4,
    3.013e-1, 5.762e-2, 1.019e-2, -4.476e-4, 6.790e-5,
    3.227e-5, 3.123e-1, -3.535e-2, 4.840e-3, 3.025e-6,
    -4.363e-5, 2.854e-7, -1.286e-6, -6.725e-1, -3.730e-2,
    8.964e-4, 1.399e-4, -3.990e-6, 7.431e-6, -2.796e-7,
    -1.601e-7, 4.068e-2, -1.352e-2, 7.282e-4, 9.594e-5,
    2.070e-6, -9.620e-8, -2.742e-7, -6.370e-8, -6.300e-9,
    8.625e-2, -5.971e-3, 4.705e-4, 2.335e-5, 4.226e-6,
    2.475e-7, -8.850e-8, -3.600e-8, -2.900e-9, 0.0,
]

_BH_AMP = [
    0.0, 0.0, -1.136e-1, 0.0, -1.868e-1,
    -1.399e-2, 0.0, -1.043e-1, 1.175e-2, -2.240e-3,
    0.0, -3.222e-2, 1.333e-2, -2.647e-3, -2.316e-5,
    0.0, 5.339e-2, 1.107e-2, -3.116e-3, -1.079e-4,
    -1.299e-5, 0.0, 4.861e-3, 8.891e-3, -6.448e-4,
    -1.279e-5, 6.358e-6, -1.417e-7, 0.0, 3.041e-2,
    1.150e-3, -8.743e-4, -2.781e-5, 6.367e-7, -1.140e-8,
    -4.200e-8, 0.0, -2.982e-2, -3.000e-3, 1.394e-5,
    -3.290e-5, -1.705e-7, 7.440e-8, 2.720e-8, -6.600e-9,
    0.0, 1.236e-2, -9.981e-4, -3.792e-5, -1.355e-5,
    1.162e-6, -1.789e-7, 1.470e-8, -2.400e-9, -4.000e-10,
]

_AW_MEAN = [
    5.640e1, 1.555e0, -1.011e0, -3.975e0, 3.171e-2,
    1.065e-1, 6.175e-1, 1.376e-1, 4.229e-2, 3.028e-3,
    1.688e0, -1.692e-1, 5.478e-2, 2.473e-2, 6.059e-4,
    2.278e0, 6.614e-3, -3.505e-4, -6.697e-3, 8.402e-4,
    7.033e-4, -3.236e0, 2.184e-1, -4.611e-2, -1.613e-2,
    -1.604e-3, 5.420e-5, 7.922e-5, -2.711e-1, -4.406e-1,
    -3.376e-2, -2.801e-3, -4.090e-4, -2.056e-5, 6.894e-6,
    2.317e-6, 1.941e0, -2.562e-1, 1.598e-2, 5.449e-3,
    3.544e-4, 1.148e-5, 7.503e-6, -5.667e-7, -3.660e-8,
    8.683e-1, -5.931e-2, -1.864e-3, -1.277e-4, 2.029e-4,
    1.269e-5, 1.629e-6, 9.660e-8, -1.015e-7, -5.000e-10,
]

_BW_MEAN = [
    0.0, 0.0, 2.592e-1, 0.0, 2.974e-2,
    -5.471e-1, 0.0, -5.926e-1, -1.030e-1, -1.567e-2,
    0.0, 1.710e-1, 9.025e-2, 2.689e-2, 2.243e-3,
    0.0, 3.439e-1, 2.402e-2, 5.410e-3, 1.601e-3,
    9.669e-5, 0.0, 9.502e-2, -3.063e-2, -1.055e-3,
    -1.067e-4, -1.130e-4, 2.124e-5, 0.0, -3.129e-1,
    8.463e-3, 2.253e-4, 7.413e-5, -9.376e-5, -1.606e-6,
    2.060e-6, 0.0, 2.739e-1, 1.167e-3, -2.246e-5,
    -1.287e-4, -2.438e-5, -7.561e-7, 1.158e-6, 4.950e-8,
    0.0, -1.344e-1, 5.342e-3, 3.775e-4, -6.756e-5,
    -1.686e-6, -1.184e-6, 2.768e-7, 2.730e-8, 5.700e-9,
]

_AW_AMP = [
    1.023e-1, -2.695e0, 3.417e-1, -1.405e-1, 3.175e-1,
    2.116e-1, 3.536e0, -1.505e-1, -1.660e-2, 2.967e-2,
    3.819e-1, -1.695e-1, -7.444e-2, 7.409e-3, -6.262e-3,
    -1.836e0, -1.759e-2, -6.256e-2, -2.371e-3, 7.947e-4,
    1.501e-4, -8.603e-1, -1.360e-1, -3.629e-2, -3.706e-3,
    -2.976e-4, 1.857e-5, 3.021e-5, 2.248e0, -1.178e-1,
    1.255e-2, 1.134e-3, -2.161e-4, -5.817e-6, 8.836e-7,
    -1.769e-7, 7.313e-1, -1.188e-1, 1.145e-2, 1.011e-3,
    1.083e-4, 2.570e-6, -2.140e-6, -5.710e-8, 2.000e-8,
    -1.632e0, -6.948e-3, -3.893e-3, 8.592e-4, 7.577e-5,
    4.539e-6, -3.852e-7, -2.213e-7, -1.370e-8, 5.800e-9,
]

_BW_AMP = [
    0.0, 0.0, -8.865e-2, 0.0, -4.309e-1,
    6.340e-2, 0.0, 1.162e-1, 6.176e-2, -4.234e-3,
    0.0, 2.530e-1, 4.017e-2, -6.204e-3, 4.977e-3,
    0.0, -1.737e-1, -5.638e-3, 1.488e-4, 4.857e-4,
    -1.809e-4, 0.0, -1.514e-1, -1.685e-2, 5.333e-3,
    -7.611e-5, 2.394e-5, 8.195e-6, 0.0, 9.326e-2,
    -1.275e-2, -3.071e-4, 5.374e-5, -3.391e-5, -7.436e-6,
    6.747e-7, 0.0, -8.637e-2, -3.807e-3, -6.833e-4,
    -3.861e-5, -2.268e-5, 1.454e-6, 3.860e-7, -1.068e-7,
    0.0, -2.658e-2, -1.947e-3, 7.131e-4, -3.506e-5,
    1.885e-7, 5.792e-7, 3.990e-8, 2.000e-8, -5.700e-9,
]

_NMAX = 9


def gmf_mapping(
    dmjd: float,
    dlat: float,
    dlon: float,
    dhgt: float,
    zd: float,
) -> tuple[float, float]:
    """GMF hydrostatic and wet mapping functions.

    Args:
        dmjd: Modified Julian Date
        dlat: geodetic latitude in radians
        dlon: geodetic longitude in radians
        dhgt: ellipsoidal height in metres
        zd: zenith distance in radians

    Returns:
        (gmfh, gmfw) — hydrostatic and wet mapping function values.
    """
    doy = dmjd - 44239.0 + 1.0 - 28.0

    x = math.cos(dlat) * math.cos(dlon)
    y = math.cos(dlat) * math.sin(dlon)
    z = math.sin(dlat)

    # Fully-normalised associated Legendre functions (V, W)
    V = [[0.0] * (_NMAX + 1) for _ in range(_NMAX + 1)]
    W = [[0.0] * (_NMAX + 1) for _ in range(_NMAX + 1)]
    V[0][0] = 1.0
    V[1][0] = z * V[0][0]
    W[1][0] = 0.0

    for n in range(2, _NMAX + 1):
        V[n][0] = ((2 * n - 1) * z * V[n - 1][0] - (n - 1) * V[n - 2][0]) / n
        W[n][0] = 0.0

    for m in range(1, _NMAX + 1):
        V[m][m] = (2 * m - 1) * (x * V[m - 1][m - 1] - y * W[m - 1][m - 1])
        W[m][m] = (2 * m - 1) * (x * W[m - 1][m - 1] + y * V[m - 1][m - 1])
        if m < _NMAX:
            V[m + 1][m] = (2 * m + 1) * z * V[m][m]
            W[m + 1][m] = (2 * m + 1) * z * W[m][m]
        for n in range(m + 2, _NMAX + 1):
            V[n][m] = ((2 * n - 1) * z * V[n - 1][m] - (n + m - 1) * V[n - 2][m]) / (n - m)
            W[n][m] = ((2 * n - 1) * z * W[n - 1][m] - (n + m - 1) * W[n - 2][m]) / (n - m)

    # Hydrostatic
    bh = 0.0029
    c0h = 0.062
    if dlat < 0:
        phh = math.pi
        c11h = 0.007
        c10h = 0.002
    else:
        phh = 0.0
        c11h = 0.005
        c10h = 0.001
    ch = c0h + ((math.cos(doy / 365.25 * 2.0 * math.pi + phh) + 1.0) * c11h / 2.0 + c10h) * (1.0 - math.cos(dlat))

    ahm = 0.0
    aha = 0.0
    i = 0
    for n in range(_NMAX + 1):
        for m_idx in range(n + 1):
            ahm += _AH_MEAN[i] * V[n][m_idx] + _BH_MEAN[i] * W[n][m_idx]
            aha += _AH_AMP[i] * V[n][m_idx] + _BH_AMP[i] * W[n][m_idx]
            i += 1
    ah = (ahm + aha * math.cos(doy / 365.25 * 2.0 * math.pi)) * 1e-5

    sine = math.sin(math.pi / 2.0 - zd)
    beta = bh / (sine + ch)
    gamma = ah / (sine + beta)
    topcon = 1.0 + ah / (1.0 + bh / (1.0 + ch))
    gmfh = topcon / (sine + gamma)

    # Height correction
    a_ht = 2.53e-5
    b_ht = 5.49e-3
    c_ht = 1.14e-3
    hs_km = dhgt / 1000.0
    beta_ht = b_ht / (sine + c_ht)
    gamma_ht = a_ht / (sine + beta_ht)
    topcon_ht = 1.0 + a_ht / (1.0 + b_ht / (1.0 + c_ht))
    ht_corr_coef = 1.0 / sine - topcon_ht / (sine + gamma_ht)
    gmfh += ht_corr_coef * hs_km

    # Wet
    bw = 0.00146
    cw = 0.04391
    awm = 0.0
    awa = 0.0
    i = 0
    for n in range(_NMAX + 1):
        for m_idx in range(n + 1):
            awm += _AW_MEAN[i] * V[n][m_idx] + _BW_MEAN[i] * W[n][m_idx]
            awa += _AW_AMP[i] * V[n][m_idx] + _BW_AMP[i] * W[n][m_idx]
            i += 1
    aw = (awm + awa * math.cos(doy / 365.25 * 2.0 * math.pi)) * 1e-5

    beta_w = bw / (sine + cw)
    gamma_w = aw / (sine + beta_w)
    topcon_w = 1.0 + aw / (1.0 + bw / (1.0 + cw))
    gmfw = topcon_w / (sine + gamma_w)

    return gmfh, gmfw


# ---------------------------------------------------------------------------
# Tropospheric delay using GMF  (ref: Trop_GMF.m)
# ---------------------------------------------------------------------------

def troposphere_gmf(
    rec_xyz: np.ndarray,
    sat_xyz: np.ndarray,
    mjd: float,
    pressure_hpa: float = 1013.25,
) -> float:
    """Tropospheric slant hydrostatic delay in metres.

    Args:
        rec_xyz: receiver ECEF (3,) metres
        sat_xyz: satellite ECEF (3,) metres
        mjd: Modified Julian Date
        pressure_hpa: surface pressure in hPa (default: standard atmosphere)

    Returns:
        Tropospheric delay in metres.
    """
    lat, lon, height = xyz_to_blh(float(rec_xyz[0]), float(rec_xyz[1]), float(rec_xyz[2]))

    # Elevation / azimuth
    dx = sat_xyz - rec_xyz
    r = np.linalg.norm(dx)
    if r < 1.0:
        return 0.0

    R_enu = build_enu_rotation(lat, lon)
    enu = R_enu.T @ dx
    e, n, u = enu
    horiz = math.sqrt(e * e + n * n)
    elev = math.atan2(u, horiz)
    if elev <= 0.0:
        return 0.0

    # Saastamoinen ZHD
    f = 0.0022768
    k = 1.0 - 0.00266 * math.cos(2.0 * lat) - 0.28e-6 * height
    zhd = f * pressure_hpa / k

    zd = math.pi / 2.0 - elev
    gmfh, _ = gmf_mapping(mjd, lat, lon, height, zd)

    return gmfh * zhd
