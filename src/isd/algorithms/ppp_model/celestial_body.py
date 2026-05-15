"""Low-precision Sun/Moon ephemeris in ECEF.

Reference: M_ISSION sun.m, moon.m, rotation.m.
"""
from __future__ import annotations

import numpy as np

AU = 149597870700.0  # meters


def _rotation_deg(pos: np.ndarray, angle_deg: float, axis: int) -> np.ndarray:
    """Rotation matrix matching M_ISSION rotation.m (angle in degrees)."""
    a = np.radians(angle_deg)
    c, s = np.cos(a), np.sin(a)
    if axis == 1:
        R = np.array([[1, 0, 0], [0, c, s], [0, -s, c]])
    elif axis == 2:
        R = np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])
    elif axis == 3:
        R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    else:
        raise ValueError(f"Invalid axis: {axis}")
    return (R @ pos.reshape(3, 1)).ravel()


def sun_position_ecef(mjd: float) -> np.ndarray:
    """Sun position in ECEF (meters) per sun.m."""
    d2r = np.pi / 180.0
    fday = mjd - np.floor(mjd)
    JDN = mjd - 15019.5

    v1 = (279.696678 + 0.9856473354 * JDN) % 360.0
    gstr = (279.690983 + 0.9856473354 * JDN + 360.0 * fday + 180.0) % 360.0
    g = ((358.475845 + 0.9856002670 * JDN) % 360.0) * d2r

    slong = (v1
             + (1.91946 - 0.004789 * JDN / 36525.0) * np.sin(g)
             + 0.020094 * np.sin(2.0 * g))
    obliq = (23.45229 - 0.0130125 * JDN / 36525.0) * d2r

    slp = (slong - 0.005686) * d2r
    snd = np.sin(obliq) * np.sin(slp)
    csd = np.sqrt(1.0 - snd * snd)
    sdec = np.degrees(np.arctan2(snd, csd))

    sra = 180.0 - np.degrees(np.arctan2(
        snd / csd / np.tan(obliq),
        -np.cos(slp) / csd,
    ))

    pos = np.array([
        np.cos(np.radians(sdec)) * np.cos(np.radians(sra)) * AU,
        np.cos(np.radians(sdec)) * np.sin(np.radians(sra)) * AU,
        np.sin(np.radians(sdec)) * AU,
    ])

    return _rotation_deg(pos, gstr, 3)


def moon_position_ecef(mjd: float) -> np.ndarray:
    """Moon position in ECEF (meters) per moon.m."""
    T = (mjd - 51544.5) / 36525.0
    L0 = 218.31617 + 481267.88088 * T - 1.3972 * T
    l = 134.96292 + 477198.86753 * T
    lp = 357.52543 + 35999.04944 * T
    F = 93.27283 + 483202.01873 * T
    D = 297.85027 + 445267.11135 * T
    obl = 23.43929111

    longitude = L0 + (
        22640 * np.sin(np.radians(l)) + 769 * np.sin(np.radians(2 * l))
        - 4586 * np.sin(np.radians(l - 2 * D)) + 2370 * np.sin(np.radians(2 * D))
        - 668 * np.sin(np.radians(lp)) - 412 * np.sin(np.radians(2 * F))
        - 212 * np.sin(np.radians(2 * l - 2 * D)) - 206 * np.sin(np.radians(l + lp - 2 * D))
        + 192 * np.sin(np.radians(l + 2 * D)) - 165 * np.sin(np.radians(lp - 2 * D))
        + 148 * np.sin(np.radians(l - lp)) - 125 * np.sin(np.radians(D))
        - 110 * np.sin(np.radians(l + lp)) - 55 * np.sin(np.radians(2 * F - 2 * D))
    ) / 3600.0

    lat_term = (
        18520 * np.sin(np.radians(F + longitude - L0 + (412 * np.sin(np.radians(2 * F)) + 541 * np.sin(np.radians(lp))) / 3600.0))
        - 526 * np.sin(np.radians(F - 2 * D)) + 44 * np.sin(np.radians(l + F - 2 * D))
        - 31 * np.sin(np.radians(-l + F - 2 * D)) - 25 * np.sin(np.radians(-2 * l + F))
        - 23 * np.sin(np.radians(lp + F - 2 * D)) + 21 * np.sin(np.radians(-l + F))
        + 11 * np.sin(np.radians(-lp + F - 2 * D))
    ) / 3600.0

    dist = (
        385000 - 20905 * np.cos(np.radians(l)) - 3699 * np.cos(np.radians(2 * D - l))
        - 2956 * np.cos(np.radians(2 * D)) - 570 * np.cos(np.radians(2 * l))
        + 246 * np.cos(np.radians(2 * l - 2 * D)) - 205 * np.cos(np.radians(lp - 2 * D))
        - 171 * np.cos(np.radians(l + 2 * D)) - 152 * np.cos(np.radians(l + lp - 2 * D))
    )

    longitude = longitude % 360.0
    lat_term = lat_term % 360.0

    pos_km = np.array([
        dist * np.cos(np.radians(longitude)) * np.cos(np.radians(lat_term)),
        dist * np.sin(np.radians(longitude)) * np.cos(np.radians(lat_term)),
        dist * np.sin(np.radians(lat_term)),
    ])

    pos_km = _rotation_deg(pos_km, -obl, 1)

    # ECI to ECEF
    fday = mjd - np.floor(mjd)
    JDN = mjd - 15019.5
    gstr = (279.690983 + 0.9856473354 * JDN + 360.0 * fday + 180.0) % 360.0
    pos_km = _rotation_deg(pos_km, gstr, 3)

    return pos_km * 1000.0  # km to meters
