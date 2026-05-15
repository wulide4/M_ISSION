"""Coordinate transforms: XYZ to geodetic, ENU rotation matrices.

Reference: M_ISSION xyz2plh.m, local.m.
"""
from __future__ import annotations

import numpy as np

# WGS84 ellipsoid
_WGS84_A = 6378137.0
_WGS84_B = 6356752.314245
_WGS84_E2 = 1.0 - (_WGS84_B / _WGS84_A) ** 2
_WGS84_EP2 = (_WGS84_A / _WGS84_B) ** 2 - 1.0


def xyz_to_blh(x: float, y: float, z: float) -> tuple[float, float, float]:
    """ECEF XYZ (meters) to geodetic (lat_rad, lon_rad, height_m).

    Iterative Bowring method matching xyz2plh.m.
    """
    lon = np.arctan2(y, x)
    p = np.sqrt(x * x + y * y)

    theta = np.arctan2(z * _WGS84_A, p * _WGS84_B)
    sin_theta = np.sin(theta)
    cos_theta = np.cos(theta)

    lat = np.arctan2(
        z + _WGS84_EP2 * _WGS84_B * sin_theta ** 3,
        p - _WGS84_E2 * _WGS84_A * cos_theta ** 3,
    )

    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    n = _WGS84_A / np.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)

    if abs(cos_lat) > 1e-10:
        h = p / cos_lat - n
    else:
        h = abs(z) - _WGS84_B

    return lat, lon, h


def build_enu_rotation(lat_rad: float, lon_rad: float) -> np.ndarray:
    """Build 3x3 ECEF-to-ENU rotation matrix.

    Columns: [East, North, Up] in ECEF.  To transform a vector from ENU to
    ECEF: v_ecef = R @ v_enu.  To project onto LOS: dot(R[:,2], los) = Up.
    """
    slat = np.sin(lat_rad)
    clat = np.cos(lat_rad)
    slon = np.sin(lon_rad)
    clon = np.cos(lon_rad)

    return np.array([
        [-slon,       -slat * clon,  clat * clon],
        [clon,        -slat * slon,  clat * slon],
        [0.0,         clat,          slat],
    ])


def local_enu(
    rec_xyz: np.ndarray, sat_xyz: np.ndarray,
) -> tuple[np.ndarray, float, float]:
    """Compute ENU vector, elevation, azimuth from receiver to satellite.

    Returns (enu_vector, elevation_rad, azimuth_rad).
    """
    dx = sat_xyz - rec_xyz
    r = np.linalg.norm(dx)
    if r < 1.0:
        return np.zeros(3), 0.0, 0.0

    lat, lon, _ = xyz_to_blh(float(rec_xyz[0]), float(rec_xyz[1]), float(rec_xyz[2]))
    R = build_enu_rotation(lat, lon)
    enu = R.T @ dx

    e, n, u = enu
    horiz = np.sqrt(e * e + n * n)
    el = np.arctan2(u, horiz)
    az = np.arctan2(e, n) % (2.0 * np.pi)
    return enu, el, az
