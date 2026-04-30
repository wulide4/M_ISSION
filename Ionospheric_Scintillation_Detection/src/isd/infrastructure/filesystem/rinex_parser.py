from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RinexHeader:
    station_code: str | None = None
    rinex_version: str | None = None
    interval_sec: int | None = None
    approx_xyz: tuple[float, float, float] | None = None
    systems: list[str] | None = None
    obs_types: dict[str, list[str]] | None = None  # {system: [obs_type_str, ...]}
    receiver_model: str | None = None
    receiver_manufacturer: str | None = None
    firmware_version: str | None = None
    antenna_model: str | None = None


class RinexParser:
    _system_map = {
        'G': 'GPS',
        'R': 'GLO',
        'E': 'GAL',
        'C': 'BDS',
        'J': 'QZS',
        'I': 'IRN',
        'S': 'SBAS',
    }

    def parse_header(self, file_path: Path) -> RinexHeader:
        hdr = RinexHeader(systems=[], obs_types={})
        with file_path.open('r', encoding='utf-8', errors='ignore') as file:
            current_sys = None
            for line in file:
                if 'RINEX VERSION / TYPE' in line:
                    hdr.rinex_version = line[:9].strip() or None
                    continue

                if 'MARKER NAME' in line and not hdr.station_code:
                    marker = line[:60].strip()
                    hdr.station_code = marker[:4].upper() if marker else None
                    continue

                if 'INTERVAL' in line:
                    try:
                        hdr.interval_sec = int(float(line[:10].strip()))
                    except ValueError:
                        pass
                    continue

                if 'APPROX POSITION XYZ' in line:
                    parts = line[:60].split()
                    if len(parts) >= 3:
                        try:
                            hdr.approx_xyz = (float(parts[0]), float(parts[1]), float(parts[2]))
                        except ValueError:
                            pass
                    continue

                if 'SYS / # / OBS TYPES' in line:
                    if line[:1].isalpha():
                        # New system header line
                        sys_char = line[0].strip()
                        system = self._system_map.get(sys_char)
                        if system:
                            hdr.systems.append(system)
                            current_sys = system
                            hdr.obs_types.setdefault(system, [])
                            try:
                                types_part = line[6:60]
                                for k in range(len(types_part) // 4):
                                    obs_type = types_part[k * 4:k * 4 + 4].strip()
                                    if obs_type and len(obs_type) >= 2:
                                        hdr.obs_types[system].append(obs_type)
                            except (ValueError, IndexError):
                                pass
                    elif current_sys and current_sys in hdr.obs_types:
                        # Continuation line
                        types_part = line[6:60]
                        for k in range(len(types_part) // 4):
                            obs_type = types_part[k * 4:k * 4 + 4].strip()
                            if obs_type and len(obs_type) >= 2:
                                hdr.obs_types[current_sys].append(obs_type)
                    continue

                if 'REC # / TYPE / VERS' in line:
                    hdr.receiver_manufacturer = line[0:20].strip() or None
                    hdr.receiver_model = line[20:40].strip() or None
                    hdr.firmware_version = line[40:60].strip() or None
                    continue

                if 'ANT # / TYPE' in line:
                    hdr.antenna_model = line[20:40].strip() or None
                    continue

                if 'END OF HEADER' in line:
                    break

        hdr.systems = sorted(set(hdr.systems or []))
        if not hdr.station_code:
            hdr.station_code = file_path.name[:4].upper()
        return hdr