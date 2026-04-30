# Windows Troubleshooting Manual
Date: 2026-04-22

## 1. Crash Logs
Unhandled exceptions are written to:
- `workspace/logs/crash/*.json`

App runtime log file:
- `workspace/logs/app.log`

Startup status:
- `workspace/runtime/startup_state.json`

## 2. Fast Diagnostics Export
Generate diagnostics bundle:
- `conda run -n isd-mvp python scripts/collect_diagnostics.py --workspace workspace`

Output:
- `workspace/reports/diagnostics_<timestamp>.zip`

Optional include database snapshot:
- `conda run -n isd-mvp python scripts/collect_diagnostics.py --workspace workspace --include-db`

## 3. Common Failures and Actions
1. App does not start after upgrade
- Check `workspace/logs/crash/` newest JSON.
- Check `workspace/runtime/startup_state.json` for `upgradeDetected` and backup path.
- Run rollback:
  - `conda run -n isd-mvp python scripts/rollback_workspace.py --workspace workspace --latest`

2. Database migration related startup failure
- Verify DB backup exists under `workspace/backups/db/`.
- Restore previous DB:
  - `conda run -n isd-mvp python scripts/rollback_workspace.py --workspace workspace --latest`
- Re-run app and capture diagnostics bundle.

3. Release package launcher fails on new machine
- Ensure `py -3.11` works in terminal.
- Re-run `install_and_launch.bat`.
- If wheel missing, regenerate package with:
  - `conda run -n isd-mvp python scripts/build_windows_release.py`

4. Version mismatch during release build
- Run:
  - `conda run -n isd-mvp python scripts/check_version_sync.py`
- Update `pyproject.toml` and `src/isd/__init__.py` to identical semver values.

## 4. Rollback Procedure (Safe)
1. List available backups:
   - `conda run -n isd-mvp python scripts/rollback_workspace.py --workspace workspace --list`
2. Dry-run a specific restore:
   - `conda run -n isd-mvp python scripts/rollback_workspace.py --workspace workspace --backup <name_part> --dry-run`
3. Execute restore:
   - `conda run -n isd-mvp python scripts/rollback_workspace.py --workspace workspace --backup <name_part>`

Safety behavior:
1. Current DB is copied to `workspace/backups/rollback/` before overwrite.
2. Then selected backup is restored to `workspace/isd.sqlite3`.

## 5. Incident Closure Checklist
1. Reproduce and collect diagnostics zip.
2. Record crash log filename and stack summary.
3. Confirm rollback/mitigation result.
4. Re-run minimum gates:
   - `conda run -n isd-mvp pytest -q`
   - `conda run -n isd-mvp python scripts/run_step12_gate.py`

