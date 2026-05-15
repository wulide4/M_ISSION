"""IGS ANTEX antenna file parser.

Reference: M_ISSION r_antx.m.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SatPcoEntry:
    north_mm: float
    east_mm: float
    up_mm: float


@dataclass
class AntexData:
    sat_pco: dict[str, dict[str, SatPcoEntry]] = field(default_factory=dict)
    rcv_pco: dict[str, dict[str, SatPcoEntry]] = field(default_factory=dict)


# Frequency code mapping per system (matching r_antx.m)
_SAT_FREQ_CODES = {
    'G': {'L1': 'G01', 'L2': 'G02'},
    'R': {'L1': 'R01', 'L2': 'R02'},
    'E': {'L1': 'E01', 'L2': 'E05'},
    'C': {'L1': 'C01', 'L2': 'C07'},
}

# Receiver frequency codes (r_antx.m uses G01/G02 for GPS, R01/R02 for GLO)
_RCV_FREQ_MAP = {
    'G01': 'GPS_L1', 'G02': 'GPS_L2',
    'R01': 'GLO_L1', 'R02': 'GLO_L2',
}


def _parse_pco_line(line: str) -> SatPcoEntry | None:
    """Parse a NORTH / EAST / UP line into a SatPcoEntry."""
    parts = line[:60].split()
    if len(parts) < 3:
        return None
    try:
        return SatPcoEntry(
            north_mm=float(parts[0]),
            east_mm=float(parts[1]),
            up_mm=float(parts[2]),
        )
    except ValueError:
        return None


def parse_antex(file_path: str | Path, antenna_type: str | None = None) -> AntexData:
    """Parse IGS ANTEX file per r_antx.m.

    Args:
        file_path: Path to the ANTEX file.
        antenna_type: Receiver antenna type string (from RINEX header) to match.
            If None, only satellite PCO is parsed.

    Returns:
        AntexData with satellite PCO keyed by sat_id ('G01', etc.)
        and receiver PCO keyed by antenna_type.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"ANTEX file not found: {path}")

    result = AntexData()
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    n = len(lines)

    i = 0
    while i < n:
        line = lines[i]
        tag = line[60:].strip() if len(line) > 60 else ''

        if tag == 'START OF ANTENNA':
            # Next line: TYPE / SERIAL NO
            i += 1
            if i >= n:
                break
            type_line = lines[i]
            type_tag = type_line[60:].strip() if len(type_line) > 60 else ''

            if type_tag != 'TYPE / SERIAL NO':
                # Scan to END OF ANTENNA
                while i < n:
                    i += 1
                    if i < n and lines[i][60:].strip() == 'END OF ANTENNA':
                        break
                i += 1
                continue

            # Determine if satellite or receiver antenna
            is_sat = False
            sys_char = ''
            prn = 0
            sat_id = ''

            if len(type_line) >= 23:
                char21 = type_line[20] if len(type_line) > 20 else ''
                if char21 in ('G', 'R', 'E', 'C'):
                    is_sat = True
                    sys_char = char21
                    try:
                        prn = int(type_line[21:23].strip())
                    except ValueError:
                        is_sat = False
                    else:
                        sat_id = f"{sys_char}{prn:02d}"

            is_rcv = False
            type_name = type_line[:20].strip()
            if not is_sat and antenna_type and type_name == antenna_type.strip()[:20].strip():
                is_rcv = True

            # Scan frequency blocks within this antenna
            freq_data: dict[str, SatPcoEntry] = {}
            i += 1
            while i < n:
                fline = lines[i]
                ftag = fline[60:].strip() if len(fline) > 60 else ''

                if ftag == 'END OF ANTENNA':
                    break

                if ftag == 'START OF FREQUENCY':
                    freq_code = fline[3:6].strip() if len(fline) >= 6 else ''

                    # Look for NORTH / EAST / UP on next line
                    i += 1
                    if i < n:
                        nline = lines[i]
                        ntag = nline[60:].strip() if len(nline) > 60 else ''
                        if ntag == 'NORTH / EAST / UP':
                            pco = _parse_pco_line(nline)
                            if pco is not None:
                                freq_data[freq_code] = pco

                i += 1

            # Store results
            if is_sat and sat_id:
                freq_map = _SAT_FREQ_CODES.get(sys_char, {})
                sat_freqs: dict[str, SatPcoEntry] = {}
                for band, fcode in freq_map.items():
                    if fcode in freq_data:
                        sat_freqs[band] = freq_data[fcode]
                if sat_freqs:
                    result.sat_pco[sat_id] = sat_freqs

            if is_rcv:
                rcv_freqs: dict[str, SatPcoEntry] = {}
                for fcode, pco in freq_data.items():
                    rcv_freqs[fcode] = pco
                if rcv_freqs:
                    result.rcv_pco[antenna_type] = rcv_freqs

        i += 1

    logger.info("Parsed ANTEX %s: %d satellites, %d receiver antennas",
                path.name, len(result.sat_pco), len(result.rcv_pco))
    return result


def get_sat_pco_meters(
    antex: AntexData, sat_id: str, freq_band: str,
) -> np.ndarray | None:
    """Get satellite PCO in meters [north, east, up].

    Returns None if not found in ANTEX.
    """
    if sat_id not in antex.sat_pco:
        return None
    entry = antex.sat_pco[sat_id].get(freq_band)
    if entry is None:
        return None
    return np.array([entry.north_mm, entry.east_mm, entry.up_mm]) / 1000.0


def get_rcv_pco_meters(
    antex: AntexData, antenna_type: str, freq_code: str,
) -> np.ndarray | None:
    """Get receiver PCO in meters [north, east, up].

    freq_code: 'G01', 'G02', 'R01', 'R02'.
    Returns None if not found.
    """
    if antenna_type not in antex.rcv_pco:
        return None
    entry = antex.rcv_pco[antenna_type].get(freq_code)
    if entry is None:
        return None
    return np.array([entry.north_mm, entry.east_mm, entry.up_mm]) / 1000.0
