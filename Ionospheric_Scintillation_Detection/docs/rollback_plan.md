# Rollback Plan (MVP Freeze)
Date: 2026-04-21

## Trigger Conditions
Rollback should be considered when one of the following happens:
1. Step12 gate fails (`overallStatus=FAILED`).
2. MVP demo script fails to complete end-to-end.
3. Critical regression appears in task lifecycle, result export, or report generation.

## Rollback Targets
1. Code rollback target: last freeze-stable tag/commit before risky merge.
2. Data rollback target:
- `workspace/isd.sqlite3` backup before release candidate run
- `workspace/reports/` archived gate and demo snapshots

## Operational Steps
1. Stop running app instances.
2. Backup current workspace DB and reports.
3. Restore previous code state.
4. Restore previous DB snapshot if schema or task metadata changed.
   - quick command:
     - `conda run -n isd-mvp python scripts/rollback_workspace.py --workspace workspace --latest`
5. Run validation:
- `conda run -n isd-mvp pytest -q`
- `conda run -n isd-mvp python scripts/run_step12_gate.py`

## Verification Checklist
1. Task validation/create/start works.
2. Result visualization list and export work.
3. Report preview/export works.
4. Step12 consolidated summary returns `PASSED`.

## Notes
1. Keep the latest failed snapshot file for diagnosis:
- `workspace/reports/release_freeze_snapshot.json`
2. Keep startup and crash traces for incident diagnosis:
- `workspace/runtime/startup_state.json`
- `workspace/logs/crash/*.json`
3. Do not delete failed artifacts before incident analysis.
