"""SP3 precise orbit parsing, Lagrange interpolation, and elevation/azimuth computation.

Strictly follows M_ISSION Get_cutobsE.m Get_EA function for NEU-based
elevation/azimuth and read_sp3.m for Lagrange interpolation approach.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np


@dataclass
class Sp3OrbitData:
    satellite_ids: list[str]
    epoch_times_seconds: np.ndarray  # (N,) seconds from midnight UTC of first epoch
    positions_km: np.ndarray  # (N, n_sat, 3) XYZ in km
    n_epochs: int
    interval_sec: float
    first_epoch_dt: datetime | None = None


def parse_sp3(file_path: str | Path) -> Sp3OrbitData:
    """Parse SP3c file per M_ISSION read_sp3.m / r_sp3 subfunction."""
    path = Path(file_path)
    lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()

    header1 = lines[0]
    n_epochs = int(header1[32:39].strip())
    first_year = int(header1[3:7])
    first_month = int(header1[8:10].strip())
    first_day = int(header1[11:13].strip())
    first_hour = int(header1[14:16].strip())
    first_min = int(header1[17:19].strip())
    first_sec = float(header1[20:30].strip())
    first_epoch_dt = datetime(first_year, first_month, first_day, first_hour, first_min, int(first_sec))

    header2 = lines[1]
    interval_sec = float(header2[24:38].strip())

    sat_ids: list[str] = []
    for line in lines[2:]:
        if not line.startswith('+'):
            break
        sat_part = line[3:]
        for i in range(0, len(sat_part), 3):
            chunk = sat_part[i:i + 3]
            if len(chunk) < 3:
                break
            sat = chunk.strip()
            if len(sat) == 3 and sat[0].isalpha() and sat[1:].isdigit():
                sat_ids.append(sat)

    n_sat = len(sat_ids)
    sat_index = {sid: i for i, sid in enumerate(sat_ids)}

    epoch_seconds: list[float] = []
    positions_list: list[np.ndarray] = []

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if not line.startswith('*'):
            idx += 1
            continue

        yr = int(line[3:7])
        mo = int(line[8:10].strip())
        dy = int(line[11:13].strip())
        hh = int(line[14:16].strip())
        mm = int(line[17:19].strip())
        ss = float(line[20:30].strip())
        epoch_dt = datetime(yr, mo, dy, hh, mm, int(ss))
        midnight = datetime(first_year, first_month, first_day)
        sec_from_midnight = (epoch_dt - midnight).total_seconds() + (ss - int(ss))
        epoch_seconds.append(sec_from_midnight)

        pos = np.full((n_sat, 3), np.nan, dtype=float)
        idx += 1
        while idx < len(lines):
            rec = lines[idx]
            if rec.startswith('*') or rec.startswith('/*') or not rec.strip():
                break
            if rec[0] == 'P':
                sat_id = rec[1:4].strip()
                if sat_id in sat_index:
                    si = sat_index[sat_id]
                    try:
                        pos[si, 0] = float(rec[4:18])
                        pos[si, 1] = float(rec[18:32])
                        pos[si, 2] = float(rec[32:46])
                    except (ValueError, IndexError):
                        pass
            idx += 1

        positions_list.append(pos)
        continue

    epoch_arr = np.array(epoch_seconds, dtype=float)
    pos_arr = np.stack(positions_list, axis=0) if positions_list else np.empty((0, n_sat, 3), dtype=float)

    return Sp3OrbitData(
        satellite_ids=sat_ids,
        epoch_times_seconds=epoch_arr,
        positions_km=pos_arr,
        n_epochs=len(epoch_seconds),
        interval_sec=interval_sec,
        first_epoch_dt=first_epoch_dt,
    )


def interpolate_sp3_to_epochs(
    sp3_data_list: list[Sp3OrbitData],
    target_seconds: np.ndarray,
    lagrange_order: int = 11,
    satellite_filter: list[str] | set[str] | None = None,
) -> dict[str, np.ndarray]:
    """Lagrange interpolation of satellite positions to target epochs.

    Per M_ISSION read_sp3.m: merge multiple days, then interpolate each
    satellite using centered Lagrange polynomial.

    Args:
        satellite_filter: If provided, only interpolate these satellite IDs
            (e.g. {'G01','G02',...}). Others are skipped entirely for speed.

    Returns {sat_id: np.ndarray shape (T, 3)} positions in km.
    """
    if not sp3_data_list or len(target_seconds) == 0:
        return {}

    all_sat_ids = sp3_data_list[0].satellite_ids
    n_target = len(target_seconds)

    all_times_list = []
    all_pos_list = []
    for sp3 in sp3_data_list:
        if sp3.n_epochs == 0:
            continue
        offset = 0.0
        if sp3.first_epoch_dt and sp3_data_list[0].first_epoch_dt:
            first_midnight = datetime(
                sp3_data_list[0].first_epoch_dt.year,
                sp3_data_list[0].first_epoch_dt.month,
                sp3_data_list[0].first_epoch_dt.day,
            )
            this_midnight = datetime(
                sp3.first_epoch_dt.year,
                sp3.first_epoch_dt.month,
                sp3.first_epoch_dt.day,
            )
            offset = (this_midnight - first_midnight).total_seconds()
        all_times_list.append(sp3.epoch_times_seconds + offset)
        all_pos_list.append(sp3.positions_km)

    if not all_times_list:
        return {}

    all_times = np.concatenate(all_times_list)
    all_pos = np.concatenate(all_pos_list, axis=0)

    sort_idx = np.argsort(all_times)
    all_times = all_times[sort_idx]
    all_pos = all_pos[sort_idx]

    unique_mask = np.concatenate(([True], np.diff(all_times) > 0.5))
    all_times = all_times[unique_mask]
    all_pos = all_pos[unique_mask]

    # Build index of satellites to interpolate
    filter_set = set(satellite_filter) if satellite_filter else None
    sat_indices: list[int] = []
    for si, sid in enumerate(all_sat_ids):
        if filter_set is None or sid in filter_set:
            sat_indices.append(si)

    result: dict[str, np.ndarray] = {}
    for si in sat_indices:
        sat_id = all_sat_ids[si]
        sat_pos = all_pos[:, si, :]
        valid_mask = np.all(np.isfinite(sat_pos), axis=1)

        if not valid_mask.any():
            result[sat_id] = np.full((n_target, 3), np.nan, dtype=float)
            continue

        interpolated = _scipy_interpolate_sat(all_times, sat_pos, target_seconds, valid_mask)
        result[sat_id] = interpolated

    return result


def _scipy_interpolate_sat(
    all_times: np.ndarray,
    sat_pos: np.ndarray,
    target_seconds: np.ndarray,
    valid_mask: np.ndarray,
) -> np.ndarray:
    """Interpolate one satellite using scipy CubicSpline per continuous arc."""
    from scipy.interpolate import CubicSpline

    n_target = len(target_seconds)
    interpolated = np.full((n_target, 3), np.nan, dtype=float)

    valid_indices = np.where(valid_mask)[0]
    if len(valid_indices) < 4:
        return interpolated

    # Split into continuous arcs (gap > 1 epoch means data hole)
    gaps = np.where(np.diff(valid_indices) > 1)[0] + 1
    arcs = np.split(valid_indices, gaps)

    for arc_indices in arcs:
        if len(arc_indices) < 4:
            continue
        arc_times = all_times[arc_indices]
        arc_pos = sat_pos[arc_indices]

        # Target epochs within this arc's span
        margin = (arc_times[-1] - arc_times[0]) * 0.001
        in_range = (target_seconds >= arc_times[0] - margin) & (target_seconds <= arc_times[-1] + margin)
        if not in_range.any():
            continue

        target_sub = target_seconds[in_range]
        try:
            for dim in range(3):
                cs = CubicSpline(arc_times, arc_pos[:, dim])
                interpolated[in_range, dim] = cs(target_sub)
        except Exception:
            interpolated[in_range, :] = np.nan

    return interpolated


def _fast_lagrange(
    all_times: np.ndarray,
    sat_pos: np.ndarray,
    target_seconds: np.ndarray,
    valid_mask: np.ndarray,
    starts: np.ndarray,
    ends: np.ndarray,
    order: int,
) -> np.ndarray:
    """Barycentric Lagrange interpolation for one satellite.

    starts/ends are precomputed per target epoch and shared across satellites.
    """
    n_target = len(target_seconds)
    interpolated = np.full((n_target, 3), np.nan, dtype=float)

    for ti in range(n_target):
        t = target_seconds[ti]
        s, e = int(starts[ti]), int(ends[ti])

        window_valid = valid_mask[s:e]
        n_valid = int(window_valid.sum())
        if n_valid < 4:
            continue

        valid_times = all_times[s:e][window_valid]
        valid_pos = sat_pos[s:e][window_valid]

        diffs = valid_times - t
        exact_idx = int(np.argmin(np.abs(diffs)))
        if abs(diffs[exact_idx]) < 1e-10:
            interpolated[ti] = valid_pos[exact_idx]
            continue

        # Barycentric weights: w_j = 1 / prod_{k!=j} (x_j - x_k)
        # Use matrix but avoid fill_diagonal overhead
        diff_matrix = valid_times[:, None] - valid_times[None, :]
        diag_backup = diff_matrix.diagonal().copy()
        np.fill_diagonal(diff_matrix, 1.0)
        with np.errstate(divide='ignore'):
            weights = 1.0 / np.prod(diff_matrix, axis=1)
        np.fill_diagonal(diff_matrix, diag_backup)

        with np.errstate(divide='ignore', invalid='ignore'):
            wd = weights / diffs
            denom = wd.sum()
            if abs(denom) < 1e-30:
                continue
            interpolated[ti, 0] = float((wd * valid_pos[:, 0]).sum() / denom)
            interpolated[ti, 1] = float((wd * valid_pos[:, 1]).sum() / denom)
            interpolated[ti, 2] = float((wd * valid_pos[:, 2]).sum() / denom)

    return interpolated


def compute_elevation_azimuth(
    station_xyz_m: tuple[float, float, float],
    sat_positions_km: dict[str, np.ndarray],
    satellite_order: list[str] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute elevation/azimuth per M_ISSION Get_EA.m via NEU rotation.

    Fully vectorized over epochs per satellite.
    """
    if satellite_order is None:
        satellite_order = sorted(sat_positions_km.keys())

    n_sat = len(satellite_order)
    if n_sat == 0:
        return np.empty((0, 0)), np.empty((0, 0))

    n_epochs = 0
    for sid in satellite_order:
        arr = sat_positions_km.get(sid)
        if arr is not None and arr.shape[0] > 0:
            n_epochs = arr.shape[0]
            break

    if n_epochs == 0:
        return np.empty((0, n_sat)), np.empty((0, n_sat))

    elevation = np.full((n_epochs, n_sat), np.nan, dtype=float)
    azimuth = np.full((n_epochs, n_sat), np.nan, dtype=float)

    sx, sy, sz = station_xyz_m
    lat_rad, lon_rad = _xyz_to_blh(sx, sy, sz)

    sin_lat = np.sin(lat_rad)
    cos_lat = np.cos(lat_rad)
    sin_lon = np.sin(lon_rad)
    cos_lon = np.cos(lon_rad)

    for col, sat_id in enumerate(satellite_order):
        sat_km = sat_positions_km.get(sat_id)
        if sat_km is None:
            continue
        n = min(sat_km.shape[0], n_epochs)
        if n == 0:
            continue

        sat_m = sat_km[:n] * 1000.0
        dx = sat_m[:, 0] - sx
        dy = sat_m[:, 1] - sy
        dz = sat_m[:, 2] - sz

        e_comp = -sin_lon * dx + cos_lon * dy
        n_comp = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
        u_comp = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz

        horiz = np.sqrt(e_comp ** 2 + n_comp ** 2)
        with np.errstate(invalid='ignore', divide='ignore'):
            elevation[:n, col] = np.arctan2(u_comp, horiz)
            azimuth[:n, col] = np.mod(np.arctan2(e_comp, n_comp), 2.0 * np.pi)

    return elevation, azimuth


def epoch_times_to_seconds(epoch_times: list[tuple[int, int, int, int, int, float]]) -> np.ndarray:
    """Convert RINEX epoch times to seconds from midnight UTC of the first day."""
    if not epoch_times:
        return np.array([], dtype=float)

    first = epoch_times[0]
    midnight = datetime(first[0], first[1], first[2])
    seconds = np.empty(len(epoch_times), dtype=float)
    for i, (yr, mo, dy, hh, mm, ss) in enumerate(epoch_times):
        epoch_dt = datetime(yr, mo, dy, hh, mm, int(ss))
        frac = ss - int(ss)
        seconds[i] = (epoch_dt - midnight).total_seconds() + frac
    return seconds


def _xyz_to_blh(x: float, y: float, z: float) -> tuple[float, float]:
    """XYZ to geodetic (lat, lon) per M_ISSION XYZtoBLH.m / WGS84."""
    a = 6378137.0
    b = 6356752.3142
    e2 = 1.0 - (b / a) ** 2
    lon = np.arctan2(y, x)
    lat = np.arctan(z / np.sqrt(x * x + y * y))
    err = 1e10
    while err > 0.00001 / 206265:
        w = np.sqrt(1.0 - e2 * (np.sin(lat) ** 2))
        n = a / w
        old = lat
        lat = np.arctan((z + n * e2 * np.sin(lat)) / np.sqrt(x * x + y * y))
        err = float(np.abs(lat - old))
    return lat, lon
