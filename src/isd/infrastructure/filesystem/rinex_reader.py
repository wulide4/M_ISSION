"""RINEX 2/3 OBS file reader for extracting dual-frequency carrier phase observations.

Supports RINEX 2.xx and 3.0x formats. Multi-GNSS: GPS, GLONASS, Galileo, BeiDou.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# Map system name to RINEX satellite prefix character
SYSTEM_PREFIX = {'GPS': 'G', 'GLO': 'R', 'GAL': 'E', 'BDS': 'C'}
PREFIX_TO_SYSTEM = {v: k for k, v in SYSTEM_PREFIX.items()}

# Per-system L1/L2 phase observation type priorities (most preferred first)
PHASE_L1_PRIORITY = {
    'GPS': ['L1W', 'L1C', 'L1P', 'L1'],
    'GLO': ['L1P', 'L1C'],
    'GAL': ['L1C'],
    'BDS': ['L2I', 'L1C', 'L1P'],
}
PHASE_L2_PRIORITY = {
    'GPS': ['L2W', 'L2L', 'L2C', 'L2P', 'L2'],
    'GLO': ['L2P', 'L2C'],
    'GAL': ['L5Q', 'L5X', 'L5C'],
    'BDS': ['L6I', 'L6C', 'L7I', 'L7Q'],
}
RANGE_L1_PRIORITY = {
    'GPS': ['C1W', 'C1C', 'C1P', 'C1', 'P1'],
    'GLO': ['C1P', 'C1C'],
    'GAL': ['C1C'],
    'BDS': ['C2I', 'C1C'],
}
RANGE_L2_PRIORITY = {
    'GPS': ['C2W', 'C2L', 'C2C', 'C2P', 'C2', 'P2'],
    'GLO': ['C2P', 'C2C'],
    'GAL': ['C5Q', 'C5X', 'C5C'],
    'BDS': ['C6I', 'C6C', 'C7I'],
}
SNR_L1_PRIORITY = {
    'GPS': ['S1C', 'S1W', 'S1'],
    'GLO': ['S1P', 'S1C'],
    'GAL': ['S1C'],
    'BDS': ['S2I', 'S1C'],
}
SNR_L2_PRIORITY = {
    'GPS': ['S2W', 'S2X', 'S2P', 'S2C', 'S2'],
    'GLO': ['S2P', 'S2C'],
    'GAL': ['S5Q', 'S5X', 'S5C'],
    'BDS': ['S6I', 'S6C', 'S7I'],
}


@dataclass
class ObsRecord:
    epoch_offset: int
    satellite_id: str
    phase_l1: float | None = None
    phase_l2: float | None = None
    range_l1: float | None = None
    range_l2: float | None = None
    snr_l1: float | None = None
    snr_l2: float | None = None
    lli_l1: int = 0
    lli_l2: int = 0


@dataclass
class RinexObsData:
    station_code: str
    rinex_version: str
    interval_sec: float
    approx_xyz: tuple[float, float, float] | None = None
    systems: list[str] = field(default_factory=list)
    receiver_model: str | None = None
    antenna_model: str | None = None
    antenna_delta_hen: tuple[float, float, float] | None = None  # [H, E, N] metres
    # Per-system observation types parsed from header
    obs_types_by_system: dict[str, list[str]] = field(default_factory=dict)
    # Resolved phase/range indices per system
    phase_l1_idx_by_system: dict[str, int] = field(default_factory=dict)
    phase_l2_idx_by_system: dict[str, int] = field(default_factory=dict)
    range_l1_idx_by_system: dict[str, int] = field(default_factory=dict)
    range_l2_idx_by_system: dict[str, int] = field(default_factory=dict)
    snr_l1_idx_by_system: dict[str, int] = field(default_factory=dict)
    snr_l2_idx_by_system: dict[str, int] = field(default_factory=dict)
    # The system this data was parsed for
    gnss_system: str = 'GPS'
    num_epochs: int = 0
    num_satellites: int = 0
    epoch_times: list[tuple[int, int, int, int, int, float]] = field(default_factory=list)
    phase_l1: np.ndarray | None = None
    phase_l2: np.ndarray | None = None
    range_l1: np.ndarray | None = None
    range_l2: np.ndarray | None = None
    snr_l1: np.ndarray | None = None
    snr_l2: np.ndarray | None = None
    satellite_ids: list[str] = field(default_factory=list)

    # Backward-compatible properties for GPS
    @property
    def gps_obs_types(self) -> list[str]:
        return self.obs_types_by_system.get('GPS', [])

    @gps_obs_types.setter
    def gps_obs_types(self, value: list[str]) -> None:
        self.obs_types_by_system['GPS'] = value

    @property
    def gps_phase_l1_idx(self) -> int:
        return self.phase_l1_idx_by_system.get('GPS', -1)

    @gps_phase_l1_idx.setter
    def gps_phase_l1_idx(self, value: int) -> None:
        self.phase_l1_idx_by_system['GPS'] = value

    @property
    def gps_phase_l2_idx(self) -> int:
        return self.phase_l2_idx_by_system.get('GPS', -1)

    @gps_phase_l2_idx.setter
    def gps_phase_l2_idx(self, value: int) -> None:
        self.phase_l2_idx_by_system['GPS'] = value

    @property
    def gps_range_l1_idx(self) -> int:
        return self.range_l1_idx_by_system.get('GPS', -1)

    @gps_range_l1_idx.setter
    def gps_range_l1_idx(self, value: int) -> None:
        self.range_l1_idx_by_system['GPS'] = value

    @property
    def gps_range_l2_idx(self) -> int:
        return self.range_l2_idx_by_system.get('GPS', -1)

    @gps_range_l2_idx.setter
    def gps_range_l2_idx(self, value: int) -> None:
        self.range_l2_idx_by_system['GPS'] = value


def read_rinex_obs(file_path: str | Path, max_epochs: int | None = None,
                   gnss_system: str = 'GPS') -> RinexObsData:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"RINEX file not found: {path}")

    with path.open('r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    data = _parse_rinex(lines, max_epochs, gnss_system)
    return data


def _parse_rinex(lines: list[str], max_epochs: int | None,
                 gnss_system: str) -> RinexObsData:
    target_prefix = SYSTEM_PREFIX.get(gnss_system, 'G')

    result = RinexObsData(
        station_code='',
        rinex_version='2',
        interval_sec=30.0,
        gnss_system=gnss_system,
    )

    idx = 0
    total_lines = len(lines)
    header_end = total_lines

    # Parse header
    while idx < total_lines:
        line = lines[idx]
        if 'END OF HEADER' in line:
            header_end = idx + 1
            break

        if 'RINEX VERSION / TYPE' in line:
            ver = line[:9].strip()
            result.rinex_version = ver
            idx += 1
            continue

        if 'MARKER NAME' in line and not result.station_code:
            marker = line[:60].strip()
            result.station_code = marker[:4].upper() if marker else ''
            idx += 1
            continue

        if 'INTERVAL' in line:
            try:
                result.interval_sec = float(line[:10].strip())
            except ValueError:
                result.interval_sec = 30.0
            idx += 1
            continue

        if 'APPROX POSITION XYZ' in line:
            parts = line[:60].split()
            if len(parts) >= 3:
                try:
                    result.approx_xyz = (float(parts[0]), float(parts[1]), float(parts[2]))
                except ValueError:
                    pass
            idx += 1
            continue

        if 'REC # / TYPE / VERS' in line:
            result.receiver_model = line[20:40].strip() or None
            idx += 1
            continue

        if 'ANT # / TYPE' in line:
            result.antenna_model = line[20:40].strip() or None
            idx += 1
            continue

        if 'ANTENNA: DELTA H/E/N' in line:
            parts = line[:60].split()
            if len(parts) >= 3:
                try:
                    result.antenna_delta_hen = (float(parts[0]), float(parts[1]), float(parts[2]))
                except ValueError:
                    pass
            idx += 1
            continue

        # RINEX 3: SYS / # / OBS TYPES — parse for ALL systems
        if 'SYS / # / OBS TYPES' in line and line[:1].isalpha():
            sys_char = line[0].strip()
            sys_name = PREFIX_TO_SYSTEM.get(sys_char)
            if sys_name:
                ntypes_str = line[3:6].strip()
                if ntypes_str:
                    ntypes = int(ntypes_str)
                else:
                    idx += 1
                    continue
                obs_types: list[str] = []
                row = 0
                while len(obs_types) < ntypes:
                    if idx + row >= total_lines:
                        break
                    target = lines[idx + row]
                    if 'SYS / # / OBS TYPES' not in target:
                        break
                    type_area = target[6:60]
                    tokens = type_area.split()
                    for tok in tokens:
                        if len(obs_types) >= ntypes:
                            break
                        tok = tok.strip()
                        if tok and len(tok) >= 2 and tok[0] in 'CLDS':
                            obs_types.append(tok)
                    row += 1
                result.obs_types_by_system[sys_name] = obs_types
                result.systems.append(sys_name)
                idx += row
                continue
            else:
                idx += 1
                continue

        # RINEX 2 header: # / TYPES OF OBSERV (GPS only in RINEX 2)
        if '# / TYPES OF OBSERV' in line:
            ntypes = int(line[:6].strip()) if line[:6].strip() else 0
            obs_types_r2: list[str] = []
            for i in range(ntypes):
                col = 6 + (i % 9) * 6
                row_offset = i // 9
                target_line = idx + row_offset
                if target_line < total_lines and col + 6 <= len(lines[target_line]):
                    otype = lines[target_line][col:col + 2].strip()
                    obs_types_r2.append(otype)
            result.obs_types_by_system['GPS'] = obs_types_r2
            if 'GPS' not in result.systems:
                result.systems.append('GPS')
            idx += (ntypes // 9) + 1
            continue

        idx += 1

    result.systems = sorted(set(result.systems))

    # Resolve phase/range indices for the target system
    _find_phase_indices_for_system(result, gnss_system)

    l1_idx = result.phase_l1_idx_by_system.get(gnss_system, -1)
    l2_idx = result.phase_l2_idx_by_system.get(gnss_system, -1)

    if l1_idx < 0 or l2_idx < 0:
        # Fallback: try broader matching
        _fallback_phase_indices(result, gnss_system)
        l1_idx = result.phase_l1_idx_by_system.get(gnss_system, -1)
        l2_idx = result.phase_l2_idx_by_system.get(gnss_system, -1)

    if l1_idx < 0 or l2_idx < 0:
        return result

    # Parse data records
    idx = header_end
    is_rinex3 = result.rinex_version.startswith('3')

    all_records: list[ObsRecord] = []
    epoch_count = 0
    epoch_times: list[tuple[int, int, int, int, int, float]] = []

    obs_types_list = result.obs_types_by_system.get(gnss_system, [])

    while idx < total_lines:
        line = lines[idx]

        if is_rinex3:
            if not line.startswith('>'):
                idx += 1
                continue
            parts = line.split()
            if len(parts) < 9:
                idx += 1
                continue
            try:
                yr = int(parts[1])
                mo = int(parts[2])
                dy = int(parts[3])
                hh = int(parts[4])
                mm = int(parts[5])
                ss = float(parts[6])
                n_sat = int(parts[8])
            except (ValueError, IndexError):
                idx += 1
                continue

            epoch_times.append((yr, mo, dy, hh, mm, ss))
            idx += 1

            for _ in range(n_sat):
                if idx >= total_lines:
                    break
                obs_line = lines[idx]
                if len(obs_line) < 3:
                    idx += 1
                    continue
                sat_id = obs_line[:3].strip()
                if not sat_id.startswith(target_prefix):
                    idx += 1
                    continue

                record = ObsRecord(
                    epoch_offset=epoch_count,
                    satellite_id=sat_id,
                )
                _parse_obs_values(obs_line[3:], obs_types_list, l1_idx, l2_idx,
                                  result.range_l1_idx_by_system.get(gnss_system, -1),
                                  result.range_l2_idx_by_system.get(gnss_system, -1),
                                  record,
                                  s1_idx=result.snr_l1_idx_by_system.get(gnss_system, -1),
                                  s2_idx=result.snr_l2_idx_by_system.get(gnss_system, -1))
                all_records.append(record)
                idx += 1

            epoch_count += 1
        else:
            # RINEX 2 epoch header
            if not line or not line[0].isspace():
                idx += 1
                continue

            parts = line.split()
            if len(parts) < 7:
                idx += 1
                continue

            try:
                yr = int(parts[0])
                mo = int(parts[1])
                dy = int(parts[2])
                hh = int(parts[3])
                mm = int(parts[4])
                ss = float(parts[5])
                n_sat = int(parts[6])
            except (ValueError, IndexError):
                idx += 1
                continue

            if yr < 80:
                yr += 2000
            elif yr < 100:
                yr += 1900

            epoch_times.append((yr, mo, dy, hh, mm, ss))

            # Parse satellite list from epoch header + continuation lines
            # RINEX 2 format: cols 32-67 hold up to 12 sats (3 chars each).
            # If n_sat > 12, continuation lines follow with ' ' at col 32.
            sat_list_str = line[32:68] if len(line) > 32 else ''
            idx += 1
            while len(sat_list_str) < n_sat * 3 and idx < total_lines:
                next_line = lines[idx]
                if next_line and next_line[0] == ' ' and len(next_line) > 32:
                    sat_list_str += next_line[32:68]
                    idx += 1
                else:
                    break

            all_sat_ids = re.findall(r'[GRCSEJ]\d{2}', sat_list_str)

            # Read ALL n_sat observation lines, only process matching ones
            for si in range(min(n_sat, len(all_sat_ids))):
                if idx >= total_lines:
                    break
                obs_line = lines[idx]
                sat_id = all_sat_ids[si]
                if sat_id.startswith(target_prefix):
                    record = ObsRecord(
                        epoch_offset=epoch_count,
                        satellite_id=sat_id,
                    )
                    _parse_obs_values_rinex2(obs_line, obs_types_list, l1_idx, l2_idx,
                                             result.range_l1_idx_by_system.get(gnss_system, -1),
                                             result.range_l2_idx_by_system.get(gnss_system, -1),
                                             record,
                                             s1_idx=result.snr_l1_idx_by_system.get(gnss_system, -1),
                                             s2_idx=result.snr_l2_idx_by_system.get(gnss_system, -1))
                    all_records.append(record)
                idx += 1

            # Skip any remaining observation lines (safety for mismatched counts)
            for _ in range(n_sat - min(n_sat, len(all_sat_ids))):
                if idx >= total_lines:
                    break
                idx += 1

            epoch_count += 1

        if max_epochs and epoch_count >= max_epochs:
            break

    result.epoch_times = epoch_times
    result.num_epochs = epoch_count

    if not all_records:
        return result

    # Get unique satellite IDs for the target system
    unique_sats = sorted({r.satellite_id for r in all_records
                          if r.satellite_id.startswith(target_prefix)})
    result.satellite_ids = unique_sats
    result.num_satellites = len(unique_sats)

    if not unique_sats:
        return result

    # Build phase matrices: (epochs x satellites)
    n_sat = len(unique_sats)
    sat_idx = {s: i for i, s in enumerate(unique_sats)}

    phase_l1 = np.full((epoch_count, n_sat), np.nan, dtype=float)
    phase_l2 = np.full((epoch_count, n_sat), np.nan, dtype=float)
    range_l1 = np.full((epoch_count, n_sat), np.nan, dtype=float)
    range_l2 = np.full((epoch_count, n_sat), np.nan, dtype=float)
    snr_l1 = np.full((epoch_count, n_sat), np.nan, dtype=float)
    snr_l2 = np.full((epoch_count, n_sat), np.nan, dtype=float)

    for rec in all_records:
        if rec.satellite_id not in sat_idx:
            continue
        si = sat_idx[rec.satellite_id]
        eo = rec.epoch_offset
        if 0 <= eo < epoch_count:
            if rec.phase_l1 is not None:
                phase_l1[eo, si] = rec.phase_l1
            if rec.phase_l2 is not None:
                phase_l2[eo, si] = rec.phase_l2
            if rec.range_l1 is not None:
                range_l1[eo, si] = rec.range_l1
            if rec.range_l2 is not None:
                range_l2[eo, si] = rec.range_l2
            if rec.snr_l1 is not None:
                snr_l1[eo, si] = rec.snr_l1
            if rec.snr_l2 is not None:
                snr_l2[eo, si] = rec.snr_l2

    result.phase_l1 = phase_l1
    result.phase_l2 = phase_l2
    result.range_l1 = range_l1
    result.range_l2 = range_l2
    result.snr_l1 = snr_l1
    result.snr_l2 = snr_l2

    return result


def _find_phase_indices_for_system(result: RinexObsData, system: str) -> None:
    obs_types = result.obs_types_by_system.get(system, [])
    if not obs_types:
        return

    l1_prior = PHASE_L1_PRIORITY.get(system, PHASE_L1_PRIORITY['GPS'])
    l2_prior = PHASE_L2_PRIORITY.get(system, PHASE_L2_PRIORITY['GPS'])
    r1_prior = RANGE_L1_PRIORITY.get(system, RANGE_L1_PRIORITY['GPS'])
    r2_prior = RANGE_L2_PRIORITY.get(system, RANGE_L2_PRIORITY['GPS'])
    s1_prior = SNR_L1_PRIORITY.get(system, SNR_L1_PRIORITY['GPS'])
    s2_prior = SNR_L2_PRIORITY.get(system, SNR_L2_PRIORITY['GPS'])

    l1_idx, l2_idx, r1_idx, r2_idx, s1_idx, s2_idx = -1, -1, -1, -1, -1, -1
    l1_rank, l2_rank = 999, 999

    for i, ot in enumerate(obs_types):
        ot_upper = ot.upper().strip()
        if ot_upper in l1_prior:
            rank = l1_prior.index(ot_upper)
            if l1_idx < 0 or rank < l1_rank:
                l1_idx = i
                l1_rank = rank
        if ot_upper in l2_prior:
            rank = l2_prior.index(ot_upper)
            if l2_idx < 0 or rank < l2_rank:
                l2_idx = i
                l2_rank = rank
        if ot_upper in r1_prior and r1_idx < 0:
            r1_idx = i
        if ot_upper in r2_prior and r2_idx < 0:
            r2_idx = i
        if ot_upper in s1_prior and s1_idx < 0:
            s1_idx = i
        if ot_upper in s2_prior and s2_idx < 0:
            s2_idx = i

    result.phase_l1_idx_by_system[system] = l1_idx
    result.phase_l2_idx_by_system[system] = l2_idx
    result.range_l1_idx_by_system[system] = r1_idx
    result.range_l2_idx_by_system[system] = r2_idx
    result.snr_l1_idx_by_system[system] = s1_idx
    result.snr_l2_idx_by_system[system] = s2_idx


def _fallback_phase_indices(result: RinexObsData, system: str) -> None:
    """Broader fallback matching for phase indices."""
    obs_types = result.obs_types_by_system.get(system, [])
    l1_idx = result.phase_l1_idx_by_system.get(system, -1)
    l2_idx = result.phase_l2_idx_by_system.get(system, -1)

    for i, ot in enumerate(obs_types):
        ot_upper = ot.upper().strip()
        if l1_idx < 0 and ot_upper.startswith('L1'):
            l1_idx = i
        if l2_idx < 0 and (ot_upper.startswith('L2') or ot_upper.startswith('L5')
                           or ot_upper.startswith('L6') or ot_upper.startswith('L7')):
            l2_idx = i

    result.phase_l1_idx_by_system[system] = l1_idx
    result.phase_l2_idx_by_system[system] = l2_idx


def _parse_obs_values(obs_str: str, obs_types: list[str],
                      l1_idx: int, l2_idx: int, r1_idx: int, r2_idx: int,
                      record: ObsRecord,
                      s1_idx: int = -1, s2_idx: int = -1) -> None:
    n_obs = len(obs_types)
    for i in range(n_obs):
        start = i * 16
        if start + 14 > len(obs_str):
            break
        val_str = obs_str[start:start + 14].strip()
        if not val_str:
            continue
        try:
            val = float(val_str)
        except ValueError:
            continue
        if val == 0.0:
            continue

        if i == l1_idx:
            record.phase_l1 = val
        elif i == l2_idx:
            record.phase_l2 = val
        elif i == r1_idx:
            record.range_l1 = val
        elif i == r2_idx:
            record.range_l2 = val
        elif i == s1_idx:
            record.snr_l1 = val
        elif i == s2_idx:
            record.snr_l2 = val


def _parse_obs_values_rinex2(obs_str: str, obs_types: list[str],
                             l1_idx: int, l2_idx: int, r1_idx: int, r2_idx: int,
                             record: ObsRecord,
                             s1_idx: int = -1, s2_idx: int = -1) -> None:
    n_obs = len(obs_types)
    for i in range(n_obs):
        start = i * 14
        if start + 14 > len(obs_str):
            break
        val_str = obs_str[start:start + 14].strip()
        if not val_str:
            continue
        try:
            val = float(val_str)
        except ValueError:
            continue
        if val == 0.0:
            continue

        if i == l1_idx:
            record.phase_l1 = val
        elif i == l2_idx:
            record.phase_l2 = val
        elif i == r1_idx:
            record.range_l1 = val
        elif i == r2_idx:
            record.range_l2 = val
        elif i == s1_idx:
            record.snr_l1 = val
        elif i == s2_idx:
            record.snr_l2 = val
