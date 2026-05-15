"""Calendar-to-MJD and related time conversions.

References: M_ISSION cal2jul.m, clc_doy.m.
"""
from __future__ import annotations


def calendar_to_mjd(
    year: int, month: int, day: int,
    hour: int = 0, minute: int = 0, second: float = 0.0,
) -> float:
    """Convert calendar date/time to Modified Julian Date.

    Algorithm matches standard MJD definition:
        MJD = JD - 2400000.5
    where JD is computed via the astronomical Julian Day formula.
    """
    if month <= 2:
        year -= 1
        month += 12

    a = year // 100
    b = 2 - a + a // 4

    jd_day = (int(365.25 * (year + 4716))
              + int(30.6001 * (month + 1))
              + day + b - 1524.5)
    jd = jd_day + (hour + minute / 60.0 + second / 3600.0) / 24.0
    return jd - 2400000.5


def mjd_to_doy(mjd: float) -> tuple[int, int]:
    """Convert MJD to (year, day-of-year)."""
    jd = mjd + 2400000.5
    z = int(jd + 0.5)
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4

    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)

    day = b - d - int(30.6001 * e)
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715

    jan1_mjd = calendar_to_mjd(year, 1, 1)
    doy = int(mjd - jan1_mjd) + 1
    return year, doy


def epoch_time_to_mjd(
    year: int, month: int, day: int,
    hour: int, minute: int, second: float,
) -> float:
    """Convenience: convert RINEX-style epoch tuple to MJD."""
    return calendar_to_mjd(year, month, day, hour, minute, second)


def epoch_time_to_seconds(
    year: int, month: int, day: int,
    hour: int, minute: int, second: float,
) -> float:
    """Seconds from midnight of the given day."""
    return hour * 3600.0 + minute * 60.0 + second
