# Windows Release Runbook
Date: 2026-04-22

## 1. Scope
This runbook defines Windows packaging, versioning, first-run initialization, and upgrade operations for ISD.

## 2. Versioning Policy
1. Use semantic version format: `MAJOR.MINOR.PATCH`.
2. `pyproject.toml` and `src/isd/__init__.py` versions must be identical.
3. Validate consistency before release:
   - `conda run -n isd-mvp python scripts/check_version_sync.py`
4. Suggested increment strategy:
   - `PATCH`: bugfix, no contract change.
   - `MINOR`: compatible features/ops tooling updates.
   - `MAJOR`: incompatible behavior or storage contract change.

## 3. Build Windows Portable Package
1. Build release package:
   - `conda run -n isd-mvp python scripts/build_windows_release.py`
2. Package output path:
   - `workspace/releases/windows/isd-v<version>-<timestamp>/`
3. Important generated files:
   - `install_and_launch.bat`
   - `launch_isd.bat`
   - `upgrade_isd.bat`
   - `collect_diagnostics.bat`
   - `rollback_workspace.bat`
   - `release_manifest.json`
4. Release gate (layout + version checks):
   - `conda run -n isd-mvp python scripts/run_windows_release_gate.py`
   - summary: `workspace/reports/windows_release_gate_summary.json`

## 4. New Machine Installation
Prerequisites:
1. Windows 10/11.
2. Python 3.11 available through `py -3.11`.

Installation:
1. Copy the generated release folder to target machine.
2. Double-click `install_and_launch.bat`.
3. Script will:
   - create local runtime venv (`.runtime/venv`)
   - install wheel from `./wheels`
   - install dependencies from `requirements-win.txt`
   - launch `python -m isd`

Post-install normal startup:
1. Use `launch_isd.bat`.

## 5. First-Run and Upgrade Strategy
Runtime startup strategy is implemented in `src/isd/runtime/startup.py`.

On first run:
1. Ensure workspace structure exists.
2. Create startup state file:
   - `workspace/runtime/startup_state.json`

On upgrade (version changed):
1. Detect previous version from startup state.
2. If database exists, create backup before migration:
   - `workspace/backups/db/isd_preupgrade_<from>_to_<to>_<timestamp>.sqlite3`
3. Continue normal app bootstrap and DB migration.

On exit:
1. Persist exit status and last crash log path to startup state.

## 6. Upgrade Procedure
1. Drop new wheel into `wheels/` in release folder.
2. Run `upgrade_isd.bat`.
3. Upgrade script reinstalls wheel, then launches app once to apply migrations.
4. Verify:
   - app startup successful
   - `workspace/runtime/startup_state.json` updated
   - backup exists in `workspace/backups/db/` if version changed

## 7. Required Validation Before External Delivery
1. `conda run -n isd-mvp pytest -q`
2. `conda run -n isd-mvp python scripts/run_step12_gate.py`
3. `conda run -n isd-mvp python scripts/run_windows_release_gate.py`
4. `conda run -n isd-mvp python scripts/run_release_freeze.py`

