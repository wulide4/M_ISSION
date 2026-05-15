"""gLAB PPP static position solver per glab_ppp_solver.m.

Calls the gLAB.exe binary (gAGE/UPC) to compute a static PPP position from
RINEX OBS + SP3 + CLK + ANTEX files, replicating the MATLAB PPPH pipeline.

Priority chain (matching glab_ppp_solver.m):
  1. Custom coordinates file (if provided via ISD_PPP_COORDS env var)
  2. gLAB.exe static PPP solution
  3. RINEX header approximate coordinates as fallback
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default gLAB executable location relative to the M_ISSION project
_GLAB_DEFAULT = (
    Path(__file__).resolve().parents[5]
    / "M_ISSION-master"
    / "code_Data_processing"
    / "GETSIGMAPHI"
    / "PPPH"
    / "ErrorModelling"
    / "gLAB.exe"
)


def _find_glab() -> Path | None:
    """Locate gLAB.exe: env var ISD_GLAB_PATH, then default location."""
    env = os.getenv("ISD_GLAB_PATH")
    if env:
        p = Path(env)
        if p.exists():
            return p
    if _GLAB_DEFAULT.exists():
        return _GLAB_DEFAULT
    return None


def _parse_glab_output(stdout: str) -> list[float] | None:
    """Parse the last OUTPUT line from gLAB console output, extract X/Y/Z.

    gLAB OUTPUT format: fields split by whitespace, X=col[11], Y=col[12], Z=col[13]
    (1-indexed columns 12, 13, 14 per glab_ppp_solver.m line 157-159).
    """
    last_xyz: list[float] | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("OUTPUT"):
            continue
        parts = line.split()
        if len(parts) < 14:
            continue
        try:
            x = float(parts[11])
            y = float(parts[12])
            z = float(parts[13])
            if abs(x) > 1e3 and abs(y) > 1e3 and abs(z) > 1e3:
                last_xyz = [x, y, z]
        except (ValueError, IndexError):
            continue
    return last_xyz


def _parse_custom_coords(coords_file: Path, station_id: str) -> list[float] | None:
    """Parse a custom coordinates text file for station X/Y/Z.

    Format: whitespace-separated tokens; look for station_id then read next 3 as X/Y/Z.
    """
    try:
        text = coords_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    parts = re.split(r"\s+", text.strip())
    target = station_id.strip().upper()
    for i, tok in enumerate(parts):
        if tok.upper() == target and i + 3 < len(parts):
            try:
                x, y, z = float(parts[i + 1]), float(parts[i + 2]), float(parts[i + 3])
                if abs(x) > 1e3:
                    return [x, y, z]
            except ValueError:
                continue
    return None


def glab_ppp_position(
    rinex_path: str | Path,
    sp3_paths: list[str | Path],
    clk_paths: list[str | Path],
    atx_path: str | Path | None,
    approx_xyz: list[float] | Any,
) -> list[float]:
    """Compute static PPP receiver position using gLAB, matching glab_ppp_solver.m.

    Args:
        rinex_path: Path to RINEX observation file.
        sp3_paths: Paths to SP3 orbit files.
        clk_paths: Paths to CLK clock files.
        atx_path: Path to ANTEX antenna file (optional).
        approx_xyz: Fallback [X, Y, Z] from RINEX header.

    Returns:
        [X, Y, Z] ECEF coordinates in metres.
    """
    fallback = list(approx_xyz) if approx_xyz is not None else [0.0, 0.0, 0.0]

    # Priority 1: custom coordinates file
    coords_env = os.getenv("ISD_PPP_COORDS")
    if coords_env:
        coords_file = Path(coords_env)
        if coords_file.exists():
            rinex_name = Path(rinex_path).stem
            station = rinex_name[:4].upper() if len(rinex_name) >= 4 else ""
            xyz = _parse_custom_coords(coords_file, station)
            if xyz is not None:
                logger.info("PPP position from custom coords file: %.2f %.2f %.2f", *xyz)
                return xyz

    # Priority 2: gLAB.exe
    glab_exe = _find_glab()
    if glab_exe is None:
        logger.warning("gLAB.exe not found, falling back to RINEX header approx_xyz")
        return fallback

    # Build command — use absolute paths since cwd changes to gLAB directory
    # gLAB accepts max 2 SP3 files; when using orb+clk mode the counts must match
    rinex_abs = Path(rinex_path).resolve()
    cmd = [str(glab_exe)]
    cmd.append(f'-input:obs "{rinex_abs}"')

    # When CLK files are provided, use -input:orb (orbit only) + -input:clk.
    # Otherwise use -input:sp3 (orbit+clock from SP3).
    # gLAB requires matching orb/clk file counts and consistent dates.
    has_clk = bool(clk_paths)
    if has_clk:
        # Match SP3 files to CLK files by extracting the date substring from filenames.
        # For each CLK file, find an SP3 file whose name contains the same date pattern.
        matched_pairs: list[tuple[str, str]] = []
        for clk in clk_paths:
            clk_name = Path(clk).name
            # Extract 7-digit date pattern like "20240840" from filename
            clk_date = ""
            for m in re.finditer(r"(\d{4})(\d{3})", clk_name):
                clk_date = m.group(0)
                break
            for sp3 in sp3_paths:
                sp3_name = Path(sp3).name
                if clk_date and clk_date in sp3_name:
                    matched_pairs.append((sp3, clk))
                    break
        # If no date match found, fall back to index pairing
        if not matched_pairs:
            n = min(len(sp3_paths), len(clk_paths), 2)
            for i in range(n):
                matched_pairs.append((sp3_paths[i], clk_paths[i]))
        for sp3, clk in matched_pairs[:2]:
            cmd.append(f'-input:orb "{Path(sp3).resolve()}"')
            cmd.append(f'-input:clk "{Path(clk).resolve()}"')
    else:
        for sp3 in sp3_paths[:2]:
            cmd.append(f'-input:sp3 "{Path(sp3).resolve()}"')

    if atx_path:
        cmd.append(f'-input:ant "{Path(atx_path).resolve()}"')
    cmd.extend([
        "-pre:dec", "300",
        "-pre:elevation", "30",
        "-model:solidtides",
        "-filter:nav", "static",
        "-filter:trop",
        "-print:output",
    ])

    cmd_str = " ".join(cmd)
    logger.info("Running gLAB: %s", cmd_str)

    try:
        result = subprocess.run(
            cmd_str,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(glab_exe.parent),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("gLAB execution failed: %s, falling back to approx_xyz", exc)
        return fallback

    xyz = _parse_glab_output(result.stdout)
    if xyz is not None:
        logger.info("gLAB PPP position: %.4f %.4f %.4f", *xyz)
        return xyz

    # Retry with --model:recphasecenter if antenna error
    if "ERROR Reference station antenna" in result.stdout:
        cmd_retry = cmd + ["--model:recphasecenter"]
        cmd_retry_str = " ".join(cmd_retry)
        try:
            result2 = subprocess.run(
                cmd_retry_str,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(glab_exe.parent),
            )
            xyz2 = _parse_glab_output(result2.stdout)
            if xyz2 is not None:
                logger.info("gLAB PPP position (retry with recphasecenter): %.4f %.4f %.4f", *xyz2)
                return xyz2
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Priority 3: fallback
    logger.warning("gLAB produced no valid output, falling back to approx_xyz")
    return fallback
