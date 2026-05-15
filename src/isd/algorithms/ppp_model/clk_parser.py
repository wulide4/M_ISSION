"""RINEX precise clock file parser.

Reference: M_ISSION r_clck.m.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Pattern: AS XX  YYYY MM DD HH MM SS.ss  nn  bias  [drift]
_AS_RE = re.compile(
    r'^AS\s+([GREC])(\d{2})\s+'
    r'(\d{4})\s+(\d{1,2})\s+(\d{1,2})\s+'
    r'(\d{1,2})\s+(\d{1,2})\s+([\d.]+)\s+'
    r'(\d+)\s+([\d.Ee+\-]+)'
)


@dataclass
class ClkData:
    satellite_ids: list[str]
    clock_biases: dict[str, np.ndarray]  # {sat_id: (N,) in seconds}
    epoch_times_seconds: np.ndarray      # (N,) seconds from midnight
    interval_sec: float
    n_epochs: int


def parse_clk(
    file_path: str | Path,
    interval_sec: float = 30.0,
    systems: list[str] | None = None,
) -> ClkData:
    """Parse RINEX 3.04 clock file per r_clck.m.

    Reads AS (satellite) records. Returns clock biases in seconds keyed
    by RINEX-style satellite ID ('G01', 'R01', etc.).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CLK file not found: {path}")

    if systems is None:
        systems = ['GPS', 'GLO', 'GAL', 'BDS']

    sys_chars = set()
    for s in systems:
        if s == 'GPS':
            sys_chars.add('G')
        elif s == 'GLO':
            sys_chars.add('R')
        elif s == 'GAL':
            sys_chars.add('E')
        elif s == 'BDS':
            sys_chars.add('C')

    n_epochs = int(86400 / interval_sec)
    epoch_sec = np.arange(n_epochs) * interval_sec

    # Temporary storage: sat_id -> epoch_index -> bias
    biases: dict[str, dict[int, float]] = {}

    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            m = _AS_RE.match(line.strip())
            if m is None:
                continue

            sys_char = m.group(1)
            if sys_char not in sys_chars:
                continue

            prn = int(m.group(2))
            hour = int(m.group(6))
            minute = int(m.group(7))
            second = float(m.group(8))
            n_vals = int(m.group(9))
            if n_vals < 1:
                continue

            bias_str = m.group(10).replace(' ', '')
            try:
                bias = float(bias_str)
            except ValueError:
                continue

            sat_id = f"{sys_char}{prn:02d}"
            epoch_idx = int((hour * 3600 + minute * 60 + second) / interval_sec)
            if epoch_idx < 0 or epoch_idx >= n_epochs:
                continue

            if sat_id not in biases:
                biases[sat_id] = {}
            biases[sat_id][epoch_idx] = bias

    # Build output arrays
    sat_ids = sorted(biases.keys())
    clock_biases = {}
    for sid in sat_ids:
        arr = np.full(n_epochs, np.nan, dtype=float)
        for idx, val in biases[sid].items():
            arr[idx] = val
        clock_biases[sid] = arr

    logger.info("Parsed CLK %s: %d satellites, %d epochs, interval=%.0fs",
                path.name, len(sat_ids), n_epochs, interval_sec)

    return ClkData(
        satellite_ids=sat_ids,
        clock_biases=clock_biases,
        epoch_times_seconds=epoch_sec,
        interval_sec=interval_sec,
        n_epochs=n_epochs,
    )


def interpolate_clock(clk_data: ClkData, sat_id: str, target_seconds: np.ndarray) -> np.ndarray:
    """Interpolate clock bias for a satellite at target epoch seconds.

    Linear interpolation between available clock epochs.
    """
    if sat_id not in clk_data.clock_biases:
        return np.full(len(target_seconds), np.nan)

    bias = clk_data.clock_biases[sat_id]
    valid = np.isfinite(bias)
    if valid.sum() < 2:
        return np.full(len(target_seconds), np.nan)

    return np.interp(
        target_seconds,
        clk_data.epoch_times_seconds[valid],
        bias[valid],
        left=np.nan,
        right=np.nan,
    )
