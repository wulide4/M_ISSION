from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from versioning import read_package_version, read_pyproject_version, validate_semver


def _run(cmd: list[str], cwd: Path) -> int:
    print(">>", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd))
    return int(proc.returncode)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_dependencies(pyproject_path: Path) -> list[str]:
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    deps = payload.get("project", {}).get("dependencies", [])
    out: list[str] = []
    for dep in deps:
        text = str(dep).strip()
        if text:
            out.append(text)
    return out


def _windows_readme(version: str) -> str:
    return f"""ISD Windows Portable Package
Version: {version}

Quick start:
1. Double-click install_and_launch.bat
2. Wait for local venv creation and dependency install
3. App starts automatically

After first installation:
- Use launch_isd.bat for normal startup
- Use upgrade_isd.bat when a new wheel is dropped in ./wheels
- Use collect_diagnostics.bat to generate troubleshooting package
- Use rollback_workspace.bat to restore database from backups
"""


def _install_bat() -> str:
    return r"""@echo off
setlocal EnableDelayedExpansion
set ROOT=%~dp0
set VENV=%ROOT%.runtime\venv

if not exist "%VENV%\Scripts\python.exe" (
  echo [ISD] Creating local venv...
  py -3.11 -m venv "%VENV%"
  if errorlevel 1 (
    echo [ISD] Failed to create venv. Ensure Python 3.11 launcher is available.
    exit /b 1
  )
)

call "%VENV%\Scripts\activate.bat"
python -m pip install --upgrade pip

set WHEEL=
for %%f in ("%ROOT%wheels\ionospheric_scintillation_detection-*.whl") do set WHEEL=%%f
if "%WHEEL%"=="" (
  echo [ISD] Wheel not found in %ROOT%wheels
  exit /b 1
)

echo [ISD] Installing %WHEEL%
python -m pip install "%WHEEL%"
if exist "%ROOT%requirements-win.txt" (
  python -m pip install -r "%ROOT%requirements-win.txt"
)

echo [ISD] Launching app...
python -m isd
"""


def _launch_bat() -> str:
    return r"""@echo off
set ROOT=%~dp0
set VENV=%ROOT%.runtime\venv
if not exist "%VENV%\Scripts\python.exe" (
  echo [ISD] Runtime not initialized. Run install_and_launch.bat first.
  exit /b 1
)
call "%VENV%\Scripts\activate.bat"
python -m isd
"""


def _upgrade_bat() -> str:
    return r"""@echo off
set ROOT=%~dp0
set VENV=%ROOT%.runtime\venv
if not exist "%VENV%\Scripts\python.exe" (
  echo [ISD] Runtime not initialized. Run install_and_launch.bat first.
  exit /b 1
)
call "%VENV%\Scripts\activate.bat"
set WHEEL=
for %%f in ("%ROOT%wheels\ionospheric_scintillation_detection-*.whl") do set WHEEL=%%f
if "%WHEEL%"=="" (
  echo [ISD] Wheel not found in %ROOT%wheels
  exit /b 1
)
python -m pip install --upgrade "%WHEEL%"
echo [ISD] Upgrade completed. Starting app once to apply migrations...
python -m isd
"""


def _collect_bat() -> str:
    return r"""@echo off
set ROOT=%~dp0
set VENV=%ROOT%.runtime\venv
if not exist "%VENV%\Scripts\python.exe" (
  echo [ISD] Runtime not initialized. Run install_and_launch.bat first.
  exit /b 1
)
call "%VENV%\Scripts\activate.bat"
python "%ROOT%tools\collect_diagnostics.py" --workspace "%ROOT%workspace"
"""


def _rollback_bat() -> str:
    return r"""@echo off
set ROOT=%~dp0
set VENV=%ROOT%.runtime\venv
if not exist "%VENV%\Scripts\python.exe" (
  echo [ISD] Runtime not initialized. Run install_and_launch.bat first.
  exit /b 1
)
call "%VENV%\Scripts\activate.bat"
python "%ROOT%tools\rollback_workspace.py" --workspace "%ROOT%workspace" --latest
"""


def _copy_tool(script_name: str, project_root: Path, tools_dir: Path) -> None:
    src = project_root / "scripts" / script_name
    dst = tools_dir / script_name
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _build_manifest(version: str, release_dir: Path, dependencies: list[str], skip_wheel: bool) -> dict[str, Any]:
    return {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "platform": "windows",
        "version": version,
        "packageType": "portable_venv",
        "releaseDir": str(release_dir),
        "skipWheelBuild": skip_wheel,
        "dependencies": dependencies,
        "launchers": [
            "install_and_launch.bat",
            "launch_isd.bat",
            "upgrade_isd.bat",
            "collect_diagnostics.bat",
            "rollback_workspace.bat",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Windows portable release package.")
    parser.add_argument(
        "--output-root",
        default="workspace/releases/windows",
        help="Output root folder relative to project root.",
    )
    parser.add_argument(
        "--skip-wheel",
        action="store_true",
        help="Skip wheel build step (useful for documentation-only dry run).",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    pyproject_version = read_pyproject_version(project_root)
    package_version = read_package_version(project_root)
    if pyproject_version != package_version:
        print(
            "Version mismatch: "
            f"pyproject.toml={pyproject_version}, src/isd/__init__.py={package_version}."
        )
        return 1
    if not validate_semver(pyproject_version):
        print(f"Invalid semantic version: {pyproject_version}")
        return 1

    dependencies = _read_dependencies(project_root / "pyproject.toml")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    release_dir = (project_root / args.output_root / f"isd-v{pyproject_version}-{timestamp}").resolve()
    wheels_dir = release_dir / "wheels"
    tools_dir = release_dir / "tools"
    release_dir.mkdir(parents=True, exist_ok=True)
    wheels_dir.mkdir(parents=True, exist_ok=True)
    tools_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_wheel:
        code = _run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(wheels_dir)], project_root)
        if code != 0:
            print("Wheel build failed.")
            return code

    _copy_tool("collect_diagnostics.py", project_root, tools_dir)
    _copy_tool("rollback_workspace.py", project_root, tools_dir)
    _copy_tool("check_version_sync.py", project_root, tools_dir)
    _copy_tool("versioning.py", project_root, tools_dir)

    _write(release_dir / "README_WINDOWS_RELEASE.txt", _windows_readme(pyproject_version))
    _write(release_dir / "requirements-win.txt", "\n".join(dependencies) + "\n")
    _write(release_dir / "install_and_launch.bat", _install_bat())
    _write(release_dir / "launch_isd.bat", _launch_bat())
    _write(release_dir / "upgrade_isd.bat", _upgrade_bat())
    _write(release_dir / "collect_diagnostics.bat", _collect_bat())
    _write(release_dir / "rollback_workspace.bat", _rollback_bat())

    manifest = _build_manifest(pyproject_version, release_dir, dependencies, args.skip_wheel)
    _write(release_dir / "release_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"Windows release package generated: {release_dir}")
    print(f"Version: {pyproject_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
