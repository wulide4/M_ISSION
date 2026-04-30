"""MATLAB-compatible metric computation strictly following M_ISSION paper (wenxian.pdf).

Provides loading of MATLAB .mat files and Python computation matching
M_ISSION cROT, DIXSG, sigma_phi, ROTI, and AATR algorithms exactly.

All equations reference the paper's equation numbers.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
from scipy.io import loadmat

from isd.algorithms.metrics import (
    KEI,
    GPS_F1,
    GPS_F2,
    check_anomalies,
    compute_l4,
    compute_rot,
    compute_stec,
    forward_diff_stec,
    rms_aatr_hourly,
    roti_from_rot,
    sigma_phi_from_filtered,
    aatr_from_dstec,
)

# Physical constants per Get_dif.m / cal_IPP2.m
EARTH_RADIUS_KM = 6371.0
IONO_HEIGHT_IPP_KM = 450.0
IPP_SPHERE_RADIUS_KM = 6828.137  # R_E + 450 per cal_IPP2.m


@dataclass(frozen=True)
class GpsMetricsBundle:
    roti: np.ndarray
    aatr: np.ndarray
    raatr: np.ndarray
    iaatr: np.ndarray | None = None  # raw per-epoch AATR before anomaly cleaning


@dataclass(frozen=True)
class GpsCrotBundle:
    b: np.ndarray
    l: np.ndarray
    crot: np.ndarray
    satellite_ids: list[str] | None = None


@dataclass(frozen=True)
class DixsgBundle:
    adixsg: np.ndarray
    ll: np.ndarray
    mbl: np.ndarray


@dataclass(frozen=True)
class GpsSigmaPhiBundle:
    l1: np.ndarray | None = None
    l2: np.ndarray | None = None


# ---------------------------------------------------------------------------
# .mat file loaders
# ---------------------------------------------------------------------------

def compute_gps_metrics_from_obs_cut(file_path: Path) -> GpsMetricsBundle:
    """Compute GPS ROTI/AATR from MATLAB obs_cut .mat file.

    Pipeline per Get_L_ROTI.m GPS_ROTI (Eq.6-8) and Get_AATR.m GPS_AATR (Eq.9-10).
    """
    data = loadmat(file_path, squeeze_me=True, struct_as_record=False)
    obs = data["obs"]
    ea = data["EA"]

    gps_l1 = np.asarray(obs.GPSL1C, dtype=float)
    gps_l2 = np.asarray(obs.GPSL2W, dtype=float)
    gps_el = np.asarray(ea.GPSel, dtype=float)

    # Eq.(6): L4 = (c/f1)*L1 - (c/f2)*L2 per Get_L_ROTI.m line 156
    l4 = compute_l4(gps_l1, gps_l2, GPS_F1, GPS_F2)
    l4 = np.asarray(l4, dtype=float)
    l4[l4 == 0] = np.nan

    # STEC per Get_L_ROTI.m lines 158-160
    stec = compute_stec(l4, GPS_F1, GPS_F2)

    # dSTEC per Get_L_ROTI.m lines 162-164
    dstec = forward_diff_stec(stec)

    # ROT = dSTEC * 2 per Get_L_ROTI.m line 165
    rot = compute_rot(dstec)

    # ROTI per Get_L_ROTI.m lines 166-168
    roti = roti_from_rot(rot, total_epochs=2880)
    # checkAnomalies.m: threshold=2.5, min_arc=10
    roti = check_anomalies(roti, diff_threshold=2.5, min_arc_length=10)

    # AATR per Get_AATR.m GPS_AATR lines 208-211
    aatr = aatr_from_dstec(dstec, gps_el)
    # checkAnomaliesaatr.m: threshold=5.2, min_arc=10
    aatr = check_anomalies(aatr, diff_threshold=5.2, min_arc_length=10)

    # IAATR = per-epoch AATR (same as AATR before RMS aggregation)
    iaatr = aatr.copy()

    # RMS AATR per Get_AATR.m lines 213-218
    raatr = rms_aatr_hourly(aatr, hourly_epochs=120)

    return GpsMetricsBundle(roti=roti, aatr=aatr, raatr=raatr, iaatr=iaatr)


def load_gps_crot_from_mat(file_path: Path) -> GpsCrotBundle:
    """Load cROT from MATLAB .mat file."""
    data = loadmat(file_path, squeeze_me=True, struct_as_record=False)
    keys = [k for k in data.keys() if not k.startswith("__")]
    if not keys:
        raise ValueError(f"No data variable in {file_path}")
    payload = data[keys[0]]
    return GpsCrotBundle(
        b=np.asarray(payload.B, dtype=float),
        l=np.asarray(payload.L, dtype=float),
        crot=np.asarray(payload.cROT, dtype=float),
    )


def load_dixsg_from_mat(file_path: Path) -> DixsgBundle:
    """Load DIXSG from MATLAB .mat file."""
    data = loadmat(file_path, squeeze_me=True, struct_as_record=False)
    if "aDIXSG" not in data or "LL" not in data:
        raise ValueError(f"Invalid DIXSG mat file: {file_path}")

    ll_raw = np.asarray(data["LL"], dtype=object).reshape(-1)
    ll_stack = np.stack([np.asarray(item, dtype=float) for item in ll_raw], axis=0)
    mbl = np.asarray(data["MBL"], dtype=float).reshape(-1) if "MBL" in data else np.array([], dtype=float)
    return DixsgBundle(
        adixsg=np.asarray(data["aDIXSG"], dtype=float).reshape(-1),
        ll=ll_stack,
        mbl=mbl,
    )


def load_gps_sigmaphi_from_mat(file_path: Path) -> GpsSigmaPhiBundle:
    """Load sigma_phi from MATLAB .mat file."""
    data = loadmat(file_path, squeeze_me=True, struct_as_record=False)
    keys = [k for k in data.keys() if not k.startswith("__")]
    if not keys:
        raise ValueError(f"No data variable in {file_path}")
    payload = data[keys[0]]
    if not hasattr(payload, "__dict__"):
        raise ValueError(f"Invalid GPSsigmaphi struct in {file_path}")

    l1 = None
    l2 = None
    if hasattr(payload, "L1"):
        l1 = np.asarray(payload.L1, dtype=float)
    if hasattr(payload, "L2"):
        l2 = np.asarray(payload.L2, dtype=float)
    if l1 is None and l2 is None:
        raise ValueError(f"No L1/L2 field in {file_path}")
    return GpsSigmaPhiBundle(l1=l1, l2=l2)


# ---------------------------------------------------------------------------
# sigma_phi per get_sigmaphi.m (Eq.5) -- delegates to metrics.py
# ---------------------------------------------------------------------------

def compute_sigma_phi_window_std(series_matrix: np.ndarray, *, window_epochs: int = 10) -> np.ndarray:
    """sigma_phi per get_sigmaphi.m sigmaphi subfunction (Eq.5).

    Uses population std (ddof=0) matching MATLAB std(..., 1).
    Output indexing: sigmaphi(m-1,i) = std(data(m-10:m-1,i), 1) for m=11:2881.
    """
    return sigma_phi_from_filtered(series_matrix, window=window_epochs)


# ---------------------------------------------------------------------------
# cROT per Get_cROT.m (Eq.11)
# ---------------------------------------------------------------------------

def compute_gps_crot_from_obs_cut(file_path: Path) -> GpsCrotBundle:
    """Compute GPS cROT per M_ISSION Get_cROT.m GPS_cROT subfunction.

    Algorithm per Get_cROT.m:
    1. L4 = (c/f1)*L1 - (c/f2)*L2  (Eq.6)
    2. STEC = L4 * 1e-3 * para * 1e6  (Get_cROT.m scaling)
    3. dSTEC = forward diff
    4. IPP coordinates via Get_dif (450km shell)
    5. cROT = |dSTEC / dif| * 2 per Eq.(11)
    """
    data = loadmat(file_path, squeeze_me=True, struct_as_record=False)
    obs = data["obs"]
    ea = data["EA"]
    coor = np.asarray(data["coor"], dtype=float).reshape(-1)
    if coor.size < 3:
        raise ValueError(f"Invalid coor in {file_path}")

    gps_l1 = np.asarray(obs.GPSL1C, dtype=float)
    gps_l2 = np.asarray(obs.GPSL2W, dtype=float)
    gps_el = np.asarray(ea.GPSel, dtype=float)
    gps_az = np.asarray(ea.GPSaz, dtype=float)

    # L4 per Get_L_ROTI.m line 156 / Eq.(6)
    l4 = compute_l4(gps_l1, gps_l2, GPS_F1, GPS_F2)
    l4 = np.asarray(l4, dtype=float)
    l4[l4 == 0] = np.nan

    # STEC with cROT scaling per Get_cROT.m: STEC = L4 * 1e-3 * para * 1e6
    para = (GPS_F1 * GPS_F1 * GPS_F2 * GPS_F2) / ((GPS_F1 * GPS_F1 - GPS_F2 * GPS_F2) * KEI)
    stec = l4 * 1e-3 * para * 1e6

    # dSTEC per Get_L_ROTI.m lines 162-164
    dstec = forward_diff_stec(stec)

    # IPP coordinates per Get_dif.m (450km ionospheric shell)
    dif, b, l = _get_dif(coor[0], coor[1], coor[2], gps_el, gps_az)

    # cROT = |dSTEC / dif| * 2 per Get_cROT.m / Eq.(11)
    with np.errstate(invalid="ignore", divide="ignore"):
        crot = np.abs(dstec / dif) * 2.0
    return GpsCrotBundle(b=b, l=l, crot=crot)


# ---------------------------------------------------------------------------
# DIXSG per Get_DIXSG.m (Eq.12-14)
# ---------------------------------------------------------------------------

def compute_dixsg_from_crot_bundles(
    crot_by_station: Mapping[str, GpsCrotBundle],
    *,
    levels: int = 8,
    sensitivity_first: float = 50.0,
    sensitivity_step: float = 50.0,
    max_distance_km: float = 1000.0,
    minlon: float = -180.0,
    minlat: float = -90.0,
    maxlon: float = 180.0,
    maxlat: float = 90.0,
    dlat: float = 1.0,
    dlon: float = 0.5,
) -> DixsgBundle:
    """Compute DIXSG per M_ISSION Get_DIXSG.m (Eq.12-14).

    Algorithm per Get_DIXSG.m:
    1. For each station pair: compute FDIXSG sensitivity across all levels per Eq.(12)
    2. FDIXSG = (|cROT1-cROT2|/level)^3 * (d/D)^-1, binarized to {0,1} per Eq.(13)
    3. Grid assignment using Get_grid.m spatial binning per Eq.(14)
    4. Hourly aggregation: max across pairs, mean across grid cells
    """
    station_ids = sorted(crot_by_station.keys())
    if len(station_ids) < 2:
        raise ValueError("DIXSG requires at least two stations")

    numlon = int(np.ceil((maxlon - minlon) / dlon))
    numlat = int(np.ceil((maxlat - minlat) / dlat))
    lon_edges = np.arange(minlon, maxlon + dlon, dlon)
    lat_edges = np.arange(minlat, maxlat + dlat, dlat)
    level_values = np.array(
        [sensitivity_first + idx * sensitivity_step for idx in range(levels)],
        dtype=float,
    )

    pair_tall_list: list[np.ndarray] = []
    for idx_a in range(len(station_ids) - 1):
        for idx_b in range(idx_a + 1, len(station_ids)):
            f1 = crot_by_station[station_ids[idx_a]]
            f2 = crot_by_station[station_ids[idx_b]]
            tall = _compute_pair_tall(
                f1,
                f2,
                level_values=level_values,
                max_distance_km=max_distance_km,
                minlon=minlon,
                minlat=minlat,
                maxlon=maxlon,
                maxlat=maxlat,
                lon_edges=lon_edges,
                lat_edges=lat_edges,
                numlon=numlon,
                numlat=numlat,
            )
            if tall is not None:
                pair_tall_list.append(tall)

    if not pair_tall_list:
        ll = np.full((24, numlat, numlon), np.nan, dtype=float)
        adixsg = np.full(24, np.nan, dtype=float)
        mbl = np.array([maxlon, minlon, maxlat, minlat, float(levels)], dtype=float)
        return DixsgBundle(adixsg=adixsg, ll=ll, mbl=mbl)

    ll = np.full((24, numlat, numlon), np.nan, dtype=float)
    adixsg = np.full(24, np.nan, dtype=float)
    for hour in range(24):
        com = 0.0
        num = 0
        tran: np.ndarray | None = None
        for tall in pair_tall_list:
            grid = tall[hour]
            if np.isnan(grid).all():
                continue
            num += int(np.isfinite(grid).sum())
            com += float(np.nansum(grid))
            tran = _nanmax_preserve(tran, grid)
        if tran is not None:
            ll[hour] = tran
        if num > 0:
            adixsg[hour] = com / num

    mbl = np.array([maxlon, minlon, maxlat, minlat, float(levels)], dtype=float)
    return DixsgBundle(adixsg=adixsg, ll=ll, mbl=mbl)


# ---------------------------------------------------------------------------
# Coordinate transforms per M_ISSION XYZtoBLH.m
# ---------------------------------------------------------------------------

def _xyz_to_blh(x: float, y: float, z: float) -> tuple[float, float]:
    """XYZ to geodetic (lat, lon) per M_ISSION XYZtoBLH.m.

    WGS84: a=6378137.0, b=6356752.3142
    Iterative latitude with convergence < 0.00001/206265 radians.
    """
    a_wgs84 = 6378137.0
    b_wgs84 = 6356752.3142
    e2 = 1.0 - (b_wgs84 / a_wgs84) ** 2
    lon = np.arctan2(y, x)
    lat = np.arctan(z / np.sqrt(x * x + y * y))
    err = 1e10
    while err > 0.00001 / 206265:
        w = np.sqrt(1.0 - e2 * (np.sin(lat) ** 2))
        n = a_wgs84 / w
        old = lat
        lat = np.arctan((z + n * e2 * np.sin(lat)) / np.sqrt(x * x + y * y))
        err = float(np.abs(lat - old))
    return lat, lon


# ---------------------------------------------------------------------------
# IPP computation per Get_dif.m / cal_IPP2.m / cal_DIPP2.m
# ---------------------------------------------------------------------------

def _cal_ipp2(b: np.ndarray, l: np.ndarray) -> np.ndarray:
    """IPP inter-epoch distance per M_ISSION cal_IPP2.m.

    Haversine distance with R = 6828.137 km (6371 + 450).
    """
    g = b.shape[1]
    dif = np.full((b.shape[0], g), np.nan, dtype=float)
    radius_km = IPP_SPHERE_RADIUS_KM

    for col in range(g):
        for row in range(b.shape[0] - 1):
            if (
                np.isfinite(l[row, col])
                and np.isfinite(l[row + 1, col])
                and np.isfinite(b[row, col])
                and np.isfinite(b[row + 1, col])
                and l[row, col] != 0
                and l[row + 1, col] != 0
                and b[row, col] != 0
                and b[row + 1, col] != 0
            ):
                # Per cal_IPP2.m: lon1/lat1 from row+1, lon2/lat2 from row
                lon1 = l[row + 1, col]
                lat1 = b[row + 1, col]
                lon2 = l[row, col]
                lat2 = b[row, col]
                dlon = lat1 - lat2  # cal_IPP2.m: dlon = lat1-lat2
                dlat = lon1 - lon2  # cal_IPP2.m: dlat = lon1-lon2
                a = (np.sin(dlat / 2.0) ** 2) + np.cos(lat1) * np.cos(lat2) * (np.sin(dlon / 2.0) ** 2)
                c = 2.0 * np.arcsin(np.sqrt(a))
                dif[row, col] = radius_km * c
    return dif


def _get_dif(sx: float, sy: float, sz: float,
             elevation: np.ndarray, azimuth: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """IPP coordinates per M_ISSION Get_dif.m.

    Single-layer ionospheric model at 450 km height per Get_dif.m:
        IPP_z = arcsin(R_E * sin(pi/2 - el) / (R_E + h_ion))
        t = pi/2 - el - IPP_z
        B = arcsin(sin(lat_r)*cos(t) + cos(lat_r)*sin(t)*cos(az))
        L = lon_r + arcsin(sin(t)*sin(az) / cos(B))
    """
    sb, sl = _xyz_to_blh(sx, sy, sz)
    rows, cols = elevation.shape
    b = np.full((rows, cols), np.nan, dtype=float)
    l = np.full((rows, cols), np.nan, dtype=float)

    R_E = 6371000.0  # Earth radius in meters per Get_dif.m
    h_ion = 450000.0  # 450 km per Get_dif.m

    for col in range(cols):
        for row in range(rows):
            if elevation[row, col] == 0:
                continue
            ippz = np.arcsin(R_E * np.sin(np.pi / 2.0 - elevation[row, col]) / (R_E + h_ion))
            t = np.pi / 2.0 - elevation[row, col] - ippz
            lat = np.arcsin(np.sin(sb) * np.cos(t) + np.cos(sb) * np.sin(t) * np.cos(azimuth[row, col]))
            lon = sl + np.arcsin(np.sin(t) * np.sin(azimuth[row, col]) / np.cos(lat))
            b[row, col] = lat
            l[row, col] = lon

    dif = _cal_ipp2(b, l)
    return dif, b, l


def _cal_dipp2(b1: np.ndarray, l1: np.ndarray, b2: np.ndarray, l2: np.ndarray) -> np.ndarray:
    """Inter-station IPP distance per M_ISSION cal_DIPP2.m.

    Haversine with R = 6828.137 km.
    """
    rows = min(b1.shape[0], b2.shape[0])
    cols = min(b1.shape[1], b2.shape[1])
    bb1 = b1[:rows, :cols]
    ll1 = l1[:rows, :cols]
    bb2 = b2[:rows, :cols]
    ll2 = l2[:rows, :cols]
    d = np.full((rows, cols), np.nan, dtype=float)
    radius_km = IPP_SPHERE_RADIUS_KM

    for col in range(cols):
        for row in range(rows):
            if (
                ll1[row, col] != 0
                and ll2[row, col] != 0
                and bb1[row, col] != 0
                and bb2[row, col] != 0
                and np.isfinite(bb1[row, col])
                and np.isfinite(ll1[row, col])
                and np.isfinite(bb2[row, col])
                and np.isfinite(ll2[row, col])
            ):
                lon1 = ll1[row, col]
                lat1 = bb1[row, col]
                lon2 = ll2[row, col]
                lat2 = bb2[row, col]
                dlon = lat1 - lat2
                dlat = lon1 - lon2
                a = (np.sin(dlat / 2.0) ** 2) + np.cos(lat1) * np.cos(lat2) * (np.sin(dlon / 2.0) ** 2)
                c = 2.0 * np.arcsin(np.sqrt(a))
                d[row, col] = radius_km * c
    return d


def _align_satellite_columns(
    f1: GpsCrotBundle,
    f2: GpsCrotBundle,
    rows: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """Align two stations' cROT/IPP arrays by common satellite IDs.

    Returns (c1, c2, b1, l1, b2, l2) with matching satellite columns,
    or None if fewer than 1 common satellite.
    """
    ids1 = (f1.satellite_ids or []) if f1.satellite_ids else None
    ids2 = (f2.satellite_ids or []) if f2.satellite_ids else None

    if ids1 is not None and ids2 is not None:
        common = [s for s in ids1 if s in ids2]
        if not common:
            return None
        idx1 = [ids1.index(s) for s in common]
        idx2 = [ids2.index(s) for s in common]
        n = min(rows, f1.crot.shape[0], f2.crot.shape[0])
        c1 = f1.crot[:n, :][:, idx1]
        c2 = f2.crot[:n, :][:, idx2]
        b1 = f1.b[:n, :][:, idx1]
        l1 = f1.l[:n, :][:, idx1]
        b2 = f2.b[:n, :][:, idx2]
        l2 = f2.l[:n, :][:, idx2]
        return c1, c2, b1, l1, b2, l2

    # No satellite ID info available: fall back to positional alignment
    cols = min(f1.crot.shape[1], f2.crot.shape[1])
    n = min(rows, f1.crot.shape[0], f2.crot.shape[0])
    c1 = f1.crot[:n, :cols]
    c2 = f2.crot[:n, :cols]
    b1 = f1.b[:n, :cols]
    l1 = f1.l[:n, :cols]
    b2 = f2.b[:n, :cols]
    l2 = f2.l[:n, :cols]
    return c1, c2, b1, l1, b2, l2


def _compute_pair_tall(
    f1: GpsCrotBundle,
    f2: GpsCrotBundle,
    *,
    level_values: np.ndarray,
    max_distance_km: float,
    minlon: float,
    minlat: float,
    maxlon: float,
    maxlat: float,
    lon_edges: np.ndarray,
    lat_edges: np.ndarray,
    numlon: int,
    numlat: int,
) -> np.ndarray | None:
    """Compute DIXSG pair tall array per M_ISSION Get_DIXSG.m (Eq.12-13)."""
    rows = min(f1.crot.shape[0], f2.crot.shape[0])

    aligned = _align_satellite_columns(f1, f2, rows)
    if aligned is None:
        return None
    c1, c2, b1, l1, b2, l2 = aligned
    rows = c1.shape[0]

    d = _cal_dipp2(b1, l1, b2, l2)
    if np.isnan(d).all():
        return None

    # Mask cells where inter-station IPP distance exceeds max_distance_km
    d_filtered = d.copy()
    d_filtered[(d > max_distance_km) & np.isfinite(d)] = np.nan

    # FDIXSG per Get_DIXSG.m Eq.(12-13): (|cROT1-cROT2|/level)^3 * (d/D)^-1, binarized
    fdixsg = np.zeros_like(c1, dtype=float)
    for level in level_values:
        with np.errstate(invalid="ignore", divide="ignore"):
            value = ((np.abs(c1 - c2) / level) ** 3) * ((d_filtered / max_distance_km) ** -1)
        part = value.copy()
        part[part > 1] = 1
        part[~np.isfinite(part)] = 0
        part[part < 1] = 0
        fdixsg = fdixsg + part

    if np.isnan(fdixsg).all() and not (fdixsg > 0).any():
        return None

    # Midpoint coordinates per Get_DIXSG.m
    l1_deg = np.mod(l1 * 180.0 / np.pi + 180.0, 360.0) - 180.0
    l2_deg = np.mod(l2 * 180.0 / np.pi + 180.0, 360.0) - 180.0
    b1_deg = b1 * 180.0 / np.pi
    b2_deg = b2 * 180.0 / np.pi

    lon = np.full_like(l1_deg, np.nan, dtype=float)
    lat = np.full_like(b1_deg, np.nan, dtype=float)
    valid = (l1_deg != 0) & (l2_deg != 0) & (b1_deg != 0) & (b2_deg != 0)
    lon[valid] = (l1_deg[valid] + l2_deg[valid]) / 2.0
    lat[valid] = (b1_deg[valid] + b2_deg[valid]) / 2.0

    # Grid filling per Get_grid.m Eq.(14)
    tall = np.full((24, numlat, numlon), np.nan, dtype=float)
    has_value = False
    for hour in range(24):
        row_slice = slice(hour * 120, min((hour + 1) * 120, rows))
        lo = lon[row_slice, :]
        la = lat[row_slice, :]
        fd = fdixsg[row_slice, :]
        mask = (lo != 0) & (la != 0) & np.isfinite(fd) & np.isfinite(lo) & np.isfinite(la)
        if not mask.any():
            continue
        lo_v = lo[mask]
        la_v = la[mask]
        fd_v = fd[mask]
        lon_idx = np.searchsorted(lon_edges, lo_v, side="right") - 1
        lat_idx = np.searchsorted(lat_edges, la_v, side="right") - 1
        ok = (
            (lon_idx >= 0)
            & (lon_idx < numlon)
            & (lat_idx >= 0)
            & (lat_idx < numlat)
            & (lo_v > minlon)
            & (lo_v <= maxlon)
            & (la_v > minlat)
            & (la_v <= maxlat)
        )
        if not ok.any():
            continue
        rows_idx = numlat - 1 - lat_idx[ok]
        cols_idx = lon_idx[ok]
        values = fd_v[ok]
        grid = tall[hour]
        for r, c, value in zip(rows_idx, cols_idx, values):
            current = grid[r, c]
            if np.isnan(current) or value > current:
                grid[r, c] = value
        has_value = True

    if not has_value:
        return None
    return tall


def _nanmax_preserve(lhs: np.ndarray | None, rhs: np.ndarray) -> np.ndarray:
    if lhs is None:
        return rhs.copy()
    out = lhs.copy()
    lhs_nan = np.isnan(lhs)
    rhs_nan = np.isnan(rhs)
    out[lhs_nan] = rhs[lhs_nan]
    both = ~lhs_nan & ~rhs_nan
    out[both] = np.maximum(lhs[both], rhs[both])
    out[rhs_nan & lhs_nan] = np.nan
    return out
