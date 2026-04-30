from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import warnings

import numpy as np
from scipy.io import loadmat

LIGHT_SPEED = 299792458.0
KEI = 40.309e16
EARTH_RADIUS_KM = 6371.0
IONO_HEIGHT_KM = 350.0

GPS_F1 = 1575.42e6
GPS_F2 = 1227.60e6


@dataclass(frozen=True)
class GpsMetricsBundle:
    roti: np.ndarray
    aatr: np.ndarray
    raatr: np.ndarray


@dataclass(frozen=True)
class GpsCrotBundle:
    b: np.ndarray
    l: np.ndarray
    crot: np.ndarray


@dataclass(frozen=True)
class DixsgBundle:
    adixsg: np.ndarray
    ll: np.ndarray
    mbl: np.ndarray


@dataclass(frozen=True)
class GpsSigmaPhiBundle:
    l1: np.ndarray | None = None
    l2: np.ndarray | None = None


def compute_gps_metrics_from_obs_cut(file_path: Path) -> GpsMetricsBundle:
    data = loadmat(file_path, squeeze_me=True, struct_as_record=False)
    obs = data["obs"]
    ea = data["EA"]

    gps_l1 = np.asarray(obs.GPSL1C, dtype=float)
    gps_l2 = np.asarray(obs.GPSL2W, dtype=float)
    gps_el = np.asarray(ea.GPSel, dtype=float)

    stec = _stec_from_dual_phase(gps_l1, gps_l2, GPS_F1, GPS_F2)
    dstec = _forward_diff(stec)

    roti = _compute_roti(dstec)
    roti = clean_anomalies(roti, diff_threshold=2.5, min_arc_length=10)

    aatr = _compute_aatr(dstec, gps_el)
    aatr = clean_anomalies(aatr, diff_threshold=5.2, min_arc_length=10)

    raatr = _compute_raatr(aatr)
    return GpsMetricsBundle(roti=roti, aatr=aatr, raatr=raatr)


def load_gps_crot_from_mat(file_path: Path) -> GpsCrotBundle:
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


def compute_sigma_phi_window_std(series_matrix: np.ndarray, *, window_epochs: int = 10) -> np.ndarray:
    data = np.asarray(series_matrix, dtype=float)
    if data.ndim != 2:
        raise ValueError("series_matrix must be 2D")
    rows, cols = data.shape
    out = np.full((rows, cols), np.nan, dtype=float)
    for col in range(cols):
        for end in range(window_epochs, rows + 1):
            out[end - 1, col] = np.nanstd(data[end - window_epochs : end, col], ddof=0)
    return out


def compute_gps_crot_from_obs_cut(file_path: Path) -> GpsCrotBundle:
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

    l4 = (LIGHT_SPEED / GPS_F1) * gps_l1 - (LIGHT_SPEED / GPS_F2) * gps_l2
    l4 = np.asarray(l4, dtype=float)
    l4[l4 == 0] = np.nan

    # Keep MATLAB unit scaling used by Get_cROT.m for cROT branch.
    para = (GPS_F1 * GPS_F1 * GPS_F2 * GPS_F2) / ((GPS_F1 * GPS_F1 - GPS_F2 * GPS_F2) * KEI)
    stec = l4 * 1e-3 * para * 1e6
    dstec = _forward_diff(stec)

    dif, b, l = _get_dif(coor[0], coor[1], coor[2], gps_el, gps_az)
    with np.errstate(invalid="ignore", divide="ignore"):
        crot = np.abs(dstec / dif) * 2.0
    return GpsCrotBundle(b=b, l=l, crot=crot)


def compute_dixsg_from_crot_bundles(
    crot_by_station: Mapping[str, GpsCrotBundle],
    *,
    levels: int = 5,
    sensitivity_first: float = 100.0,
    sensitivity_step: float = 50.0,
    max_distance_km: float = 1000.0,
    minlon: float = -180.0,
    minlat: float = -90.0,
    maxlon: float = 180.0,
    maxlat: float = 90.0,
    dlat: float = 1.0,
    dlon: float = 0.5,
) -> DixsgBundle:
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


def clean_anomalies(data: np.ndarray, *, diff_threshold: float, min_arc_length: int) -> np.ndarray:
    if data.size == 0:
        return data

    cleaned = np.asarray(data, dtype=float).copy()
    num_rows, num_cols = cleaned.shape

    with_nan = np.vstack([np.full((1, num_cols), np.nan), cleaned])
    differences = np.diff(with_nan, axis=0)
    anomaly_rows, anomaly_cols = np.where(np.abs(differences) > diff_threshold)

    for row, col in zip(anomaly_rows, anomaly_cols):
        if np.isnan(cleaned[row, col]):
            continue
        arc_end = row
        while arc_end + 1 < num_rows and not np.isnan(cleaned[arc_end + 1, col]):
            arc_end += 1
        cleaned[row : arc_end + 1, col] = np.nan

    for col in range(num_cols):
        row = 0
        while row < num_rows:
            if np.isnan(cleaned[row, col]):
                row += 1
                continue
            start = row
            end = start
            while end + 1 < num_rows and not np.isnan(cleaned[end + 1, col]):
                end += 1
            if (end - start + 1) < min_arc_length:
                cleaned[start : end + 1, col] = np.nan
            row = end + 1

    return cleaned


def _stec_from_dual_phase(phase_l1: np.ndarray, phase_l2: np.ndarray, f1: float, f2: float) -> np.ndarray:
    l4 = (LIGHT_SPEED / f1) * phase_l1 - (LIGHT_SPEED / f2) * phase_l2
    l4 = np.asarray(l4, dtype=float)
    l4[l4 == 0] = np.nan
    para = (f1 * f1 * f2 * f2) / ((f1 * f1 - f2 * f2) * KEI)
    return l4 * para


def _forward_diff(values: np.ndarray) -> np.ndarray:
    out = np.full(values.shape, np.nan, dtype=float)
    out[:-1, :] = values[1:, :] - values[:-1, :]
    return out


def _compute_roti(dstec: np.ndarray) -> np.ndarray:
    rot = dstec * 2.0
    out = np.full(rot.shape, np.nan, dtype=float)
    num_rows = rot.shape[0]
    for m in range(11, num_rows + 2):
        out_idx = m - 7
        if out_idx < 0 or out_idx >= num_rows:
            continue
        window = rot[m - 11 : m - 1, :]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            out[out_idx, :] = np.nanstd(window, axis=0, ddof=1)
    return out


def _compute_aatr(dstec: np.ndarray, elevation_rad: np.ndarray) -> np.ndarray:
    el = np.asarray(elevation_rad, dtype=float).copy()
    el[el == 0] = np.nan
    ratio = (EARTH_RADIUS_KM / (IONO_HEIGHT_KM + EARTH_RADIUS_KM)) ** 2
    mapping = 1.0 / (1.0 - ratio * (np.cos(el) ** 2))
    return (2.0 * dstec) / mapping


def _compute_raatr(aatr: np.ndarray) -> np.ndarray:
    blocks = aatr.shape[0] // 120
    out = np.full((blocks, 1), np.nan, dtype=float)
    for i in range(blocks):
        seg = aatr[i * 120 : (i + 1) * 120, :]
        with np.errstate(invalid="ignore"):
            out[i, 0] = np.sqrt(np.nanmean(seg**2))
    return out


def _xyz_to_blh(x: float, y: float, z: float) -> tuple[float, float]:
    a_wgs84 = 6378137.0
    b_wgs84 = 6356752.3142
    eccentricity = np.sqrt(1.0 - (b_wgs84 / a_wgs84) ** 2)
    e2 = eccentricity * eccentricity
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


def _cal_ipp2(b: np.ndarray, l: np.ndarray) -> np.ndarray:
    g = b.shape[1]
    dif = np.full((b.shape[0], g), np.nan, dtype=float)
    radius_km = 6828.137
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
                lon1 = l[row + 1, col]
                lat1 = b[row + 1, col]
                lon2 = l[row, col]
                lat2 = b[row, col]
                dlon = lat1 - lat2
                dlat = lon1 - lon2
                a = (np.sin(dlat / 2.0) ** 2) + np.cos(lat1) * np.cos(lat2) * (np.sin(dlon / 2.0) ** 2)
                c = 2.0 * np.arcsin(np.sqrt(a))
                dif[row, col] = radius_km * c
    return dif


def _get_dif(sx: float, sy: float, sz: float, elevation: np.ndarray, azimuth: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sb, sl = _xyz_to_blh(sx, sy, sz)
    rows, cols = elevation.shape
    b = np.full((rows, cols), np.nan, dtype=float)
    l = np.full((rows, cols), np.nan, dtype=float)
    for col in range(cols):
        for row in range(rows):
            if elevation[row, col] == 0:
                continue
            ippz = np.arcsin(6371000.0 * np.sin(np.pi / 2.0 - elevation[row, col]) / (6371000.0 + 450000.0))
            t = np.pi / 2.0 - elevation[row, col] - ippz
            lat = np.arcsin(np.sin(sb) * np.cos(t) + np.cos(sb) * np.sin(t) * np.cos(azimuth[row, col]))
            lon = sl + np.arcsin(np.sin(t) * np.sin(azimuth[row, col]) / np.cos(lat))
            b[row, col] = lat
            l[row, col] = lon
    dif = _cal_ipp2(b, l)
    return dif, b, l


def _cal_dipp2(b1: np.ndarray, l1: np.ndarray, b2: np.ndarray, l2: np.ndarray) -> np.ndarray:
    rows = min(b1.shape[0], b2.shape[0])
    cols = min(b1.shape[1], b2.shape[1])
    bb1 = b1[:rows, :cols]
    ll1 = l1[:rows, :cols]
    bb2 = b2[:rows, :cols]
    ll2 = l2[:rows, :cols]
    d = np.full((rows, cols), np.nan, dtype=float)
    radius_km = 6828.137
    for col in range(cols):
        for row in range(rows - 1):
            if (
                ll1[row, col] != 0
                and ll2[row, col] != 0
                and bb1[row, col] != 0
                and bb2[row, col] != 0
                and np.isfinite(bb1[row, col])
                and np.isfinite(ll1[row, col])
                and np.isfinite(ll2[row, col])
                and np.isfinite(bb2[row, col])
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
    rows = min(f1.crot.shape[0], f2.crot.shape[0])
    cols = min(f1.crot.shape[1], f2.crot.shape[1])
    c1 = f1.crot[:rows, :cols]
    c2 = f2.crot[:rows, :cols]
    b1 = f1.b[:rows, :cols]
    l1 = f1.l[:rows, :cols]
    b2 = f2.b[:rows, :cols]
    l2 = f2.l[:rows, :cols]
    d = _cal_dipp2(b1, l1, b2, l2)
    if (np.isfinite(d).any() and np.nanmax(d) > max_distance_km) or np.isnan(d).all():
        return None

    fdixsg = np.zeros_like(c1, dtype=float)
    for level in level_values:
        with np.errstate(invalid="ignore", divide="ignore"):
            value = ((np.abs(c1 - c2) / level) ** 3) * ((d / max_distance_km) ** -1)
        part = value.copy()
        part[part > 1] = 1
        part[part < 1] = 0
        fdixsg = fdixsg + part

    if np.isnan(fdixsg).all():
        return None

    l1_deg = np.mod(l1 * 180.0 / np.pi + 180.0, 360.0) - 180.0
    l2_deg = np.mod(l2 * 180.0 / np.pi + 180.0, 360.0) - 180.0
    b1_deg = b1 * 180.0 / np.pi
    b2_deg = b2 * 180.0 / np.pi

    lon = np.full_like(l1_deg, np.nan, dtype=float)
    lat = np.full_like(b1_deg, np.nan, dtype=float)
    valid = (l1_deg != 0) & (l2_deg != 0) & (b1_deg != 0) & (b2_deg != 0)
    lon[valid] = (l1_deg[valid] + l2_deg[valid]) / 2.0
    lat[valid] = (b1_deg[valid] + b2_deg[valid]) / 2.0

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
