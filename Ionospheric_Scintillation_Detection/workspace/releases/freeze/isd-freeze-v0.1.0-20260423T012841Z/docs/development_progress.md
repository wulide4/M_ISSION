# ISD Python MVP Development Progress
Updated: 2026-04-23

## Next Phase Progress (Post-MVP)
1. P0-01 (spec unification): done
- Added Python primary engineering spec:
  - `ENGINEERING_SPEC_PYTHON_V2.md`
- Aligned spec with current implementation:
  - Python/PySide6 stack freeze
  - `src/isd` layered structure
  - CommandBus channel contract
  - SQLite migration/tables
  - regression gate and freeze workflow
2. P0-02 (gate solidification): done
- Added unified gate runner:
  - `scripts/run_p0_gate.py`
- Gate output artifact:
  - `workspace/reports/p0_gate_summary.json`
- Verified once in `isd-mvp` environment:
  - `overallStatus=PASSED`
3. P0-03 (validateTask rule matrix + closure): done
- Added rule matrix:
  - `docs/validate_task_rule_matrix.md`
- Updated `validateTask` with settings-driven controls:
  - global NAV degraded switch check
  - global non-GPS sigma switch check
  - global 1s experimental switch check
  - policy-driven RINEX-approx sigma warning/blocking
- Expanded validation tests:
  - `tests/test_task_validate.py` (now 8 tests)
- Validation rerun:
  - `conda run -n isd-mvp pytest -q` -> `41 passed`
  - `conda run -n isd-mvp python scripts/run_p0_gate.py` -> `overallStatus=PASSED`
4. P0-04 (project management hardening): done
- Backend hardening:
  - project root must exist + be directory
  - unreadable root path returns explicit error
  - scan response now contains `summary` block (state/counts)
  - project list now includes root/workspace existence health flags
- UI hardening:
  - added "rescan project root" action
  - selected project now loads root path into form
  - added project status summary panel (state/files/stations/matched/issues/readyDates)
- Tests:
  - `tests/test_project_service.py` expanded to 4 tests
  - added non-directory root rejection test
  - added rescan replace-consistency test
- Validation rerun:
  - `conda run -n isd-mvp pytest -q` -> `43 passed`
  - `conda run -n isd-mvp python scripts/run_p0_gate.py` -> `overallStatus=PASSED`

## Step Status
1. Step 1 (MATLAB baseline manifest): done
2. Step 2 (sample mapping): done
3. Step 3 (input scan/match chain): done
4. Step 4 (`validateTask` blocking rules): done
5. Step 5 (task runtime lifecycle): done
6. Step 6 (ROTI/IAATR/AATR migration): done
7. Step 7 (cROT + DIXSG migration): done
8. Step 8 (GPS `SIGMA_PHI_F`): done
9. Step 9 (NPZ/Parquet + MAT export): done
10. Step 10 (result closure): done
11. Step 11 (batch/analysis/report/settings governance): done (MVP scope)
12. Step 12 (dual-track regression gate): done
13. Step 13 (MVP freeze package): done (initial freeze-ready)

## Delivered Finalization Package
1. Unified risk governance
- Added shared risk flag module and connected it to:
  - task validation output
  - visualization detail panel
  - report preview summary

2. Regression and gate closure
- Step12 one-click gate includes:
  - full `pytest`
  - ROTI/AATR regression
  - cROT/DIXSG regression
  - SIGMA_PHI_F regression
  - export-format regression (MAT/Parquet)
  - consolidated summary JSON

3. MVP freeze and release support
- Added one-click freeze snapshot runner:
  - `scripts/run_release_freeze.py`
- Added MVP release docs:
  - `docs/release_notes_v0_1_mvp.md`
  - `docs/known_limitations.md`
  - `docs/rollback_plan.md`
  - `docs/mvp_acceptance_checklist.md`

## Current Validation
- `conda run -n isd-mvp pytest -q` -> expected pass
- `conda run -n isd-mvp python scripts/run_step12_gate.py` -> expected pass
- `conda run -n isd-mvp python scripts/run_mvp_demo.py` -> expected pass
- `conda run -n isd-mvp python scripts/run_release_freeze.py` -> expected pass

## Freeze Artifacts
- `workspace/reports/regression_step12_summary_24084.json`
- `workspace/reports/mvp_demo_summary.json`
- `workspace/reports/release_freeze_snapshot.json`

## Incremental Update (2026-04-21)
5. P0-05 (result visualization hardening): done
- Backend hardening:
  - split `result:getSeries` and `result:getGrid` behavior and error codes
  - added strict format checks (`SERIES_NOT_AVAILABLE`, `SERIES_FORMAT_INVALID`, `GRID_NOT_AVAILABLE`, `GRID_FORMAT_INVALID`)
  - improved intermediate artifact lookup for project-scoped and fallback multi-project task path
- UI hardening:
  - added project-synced filter field in visualization page
  - distinct status hints for no-result / load-failed / format-invalid
  - unified load chain: `result:list -> getSeries -> getGrid -> getIntermediate`
  - strengthened export path validity under `workspace/outputs/{projectId}`
- Tests:
  - `tests/test_result_service_export.py` expanded with grid-coverage and no-grid behavior checks

6. P0-06 (report center PDF): done
- Report service upgrade:
  - report preview now includes task info, parameter snapshot, and result cards
  - non-GPS `SIGMA_PHI_F` excluded by default; opt-in via `includeNonGpsSigmaPhiF`
  - added stable lightweight PDF exporter with text fallback on failure
- Report UI upgrade:
  - report center now supports PDF/TXT export target
  - added export-state visualization and fallback/warning feedback
  - added non-GPS sigma report inclusion switch
- Tests:
  - `tests/test_report_service.py` expanded with PDF export and non-GPS sigma include/exclude checks
- Validation rerun:
  - `conda run -n isd-mvp pytest -q` -> `48 passed`
  - `conda run -n isd-mvp python scripts/run_p0_gate.py` -> `overallStatus=PASSED`

## Incremental Update (2026-04-21, P1-07)
7. P1-07 (settings + template system): done
- Settings persistence upgraded:
  - system settings now include `defaultAlgorithmConfig`, `thresholdPresets`, `receiverThresholdPresets`, `defaultOutputPath`
  - defaults load from `config/defaults/*.json` with deep-merge update and restart-safe persistence
- Settings UI completed:
  - editable default algorithm parameters
  - threshold presets JSON editing
  - receiver threshold preset CRUD (load/save/delete in settings cache, then persist)
- Template system completed:
  - added template channels: `template:list/get/save/delete`
  - implemented save/load/overwrite strategies (`OVERWRITE` / `CREATE_NEW` / `REJECT`)
  - Data Calculation page supports template apply and save-as-template
- Config source visibility completed:
  - Data Calculation page now shows `parameter_source` and `threshold_source` (`manual/template/default`)
  - task creation carries `templateId` + source metadata into `TaskConfig`
- Runtime metadata alignment:
  - result `parameter_source_summary` and `threshold_source` now derived from task config source metadata
- Validation rerun:
  - `conda run -n isd-mvp pytest -q` -> `51 passed`
  - `conda run -n isd-mvp python scripts/run_p0_gate.py` -> `overallStatus=PASSED`

## Incremental Update (2026-04-22, P1-08)
8. P1-08 (provider from stub to basic): done
- Provider interfaces upgraded:
  - added structured provider statuses for coordinate/orbit-clock/antenna
  - implemented `BasicPreciseCoordinateProvider`, `BasicOrbitClockCorrectionProvider`, `BasicAntennaCorrectionProvider`
- Validation and chain derivation integrated:
  - `validateTask` now builds `providerSummary` and returns `providerChainHint`
  - provider readiness now participates in sigma-phi-f dependency judgement and formal/degraded/experimental derivation
- Task/result metadata integrated:
  - `TaskConfig` now carries `provider_metadata`
  - task creation snapshots provider summary into config
  - runtime result metadata now fills `coordinate_source` and provider summary string in `parameter_source_summary`
- UI/Report visibility:
  - visualization detail card now shows `coordinateSource`, `thresholdSource`, and `parameterSourceSummary`
  - report summary/cards now include provider source breakdown
- Tests added/updated:
  - `tests/test_providers_basic.py` (new)
  - `tests/test_task_validate.py` (provider chain hint assertions + formal dependency case)
  - `tests/test_task_runtime.py` (result metadata provider summary assertion)
  - `tests/test_report_service.py` (provider source key presence)
- Validation rerun:
  - `conda run -n isd-mvp pytest -q` -> `55 passed`
  - `conda run -n isd-mvp python scripts/run_p0_gate.py` -> `overallStatus=PASSED`

## Incremental Update (2026-04-22, P1-09)
9. P1-09 (`SIGMA_PHI_F` formal chain hardening): done
- Worker chain tracing completed:
  - added explicit sigma sub-steps in runtime `ProcessingStep` records:
    - `sigmaphi_cutoff_elevation`
    - `sigmaphi_short_arc_removal`
    - `sigmaphi_cycle_slip_detection`
    - `sigmaphi_cycle_slip_repair`
    - `sigmaphi_geodetic_detrending`
    - `sigmaphi_polynomial_detrending`
    - `sigmaphi_butterworth_filter`
    - `sigmaphi_moving_window_sigma`
  - each sub-step now writes dedicated intermediate JSON artifact when `enable_intermediate_save=true`
- Formal path compatibility preserved:
  - GPS sigma final output keeps MATLAB baseline path as authoritative result source
  - added `traceDiff` summary into sigma metric artifact to compare trace output vs final loaded series
- Regression/stat summary enhancement:
  - `scripts/run_sigmaphi_regression_24084.py` now includes extra min/max/mean stats for A/B sides
- Tests updated:
  - `tests/test_matlab_sigmaphi_regression.py` now asserts:
    - required sigma sub-step keys exist
    - step status is `COMPLETED`
    - step artifact paths exist on disk
- Validation rerun:
  - `conda run -n isd-mvp pytest -q` -> `55 passed`
  - `conda run -n isd-mvp pytest -q tests/test_matlab_sigmaphi_regression.py tests/test_task_runtime.py tests/test_result_service_export.py` -> `11 passed`
  - `conda run -n isd-mvp python scripts/run_sigmaphi_regression_24084.py` -> all stations `mae=0.000e+00`

## Incremental Update (2026-04-22, P1-10)
10. P1-10 (MATLAB regression dataset expansion): done
- Dataset baseline registry completed:
  - added `config/datasets/regression_datasets.json`
  - kept `24084` as enabled baseline
  - added `24085` and `24086` manifests without overwriting old baseline:
    - `config/datasets/matlab_24085_manifest.json`
    - `config/datasets/matlab_24086_manifest.json`
- Regression scripts upgraded to dataset-parameterized execution:
  - `scripts/run_roti_aatr_regression_24084.py --dataset <id>`
  - `scripts/run_crot_dixsg_regression_24084.py --dataset <id>`
  - `scripts/run_sigmaphi_regression_24084.py --dataset <id>`
  - `scripts/run_export_regression_24084.py --dataset <id>`
- Step12 summary upgraded to per-dataset and matrix summary:
  - `scripts/build_step12_summary.py --dataset <id>` (single summary)
  - `scripts/build_step12_summary.py --datasets 24084,24085` (matrix summary)
  - output now supports `workspace/reports/regression_step12_summary_matrix.json`
- Gate orchestration upgraded:
  - `scripts/run_step12_gate.py` now loads enabled datasets from registry and runs regression in batch
  - generates both per-dataset summary and matrix summary
- Supporting updates:
  - `scripts/build_matlab_manifest.py` now supports `--dataset-id --doy --date`
  - `scripts/sync_matlab_samples.py` README metadata is now manifest-driven
  - `scripts/run_release_freeze.py` now records matrix summary artifact when available
- Tests:
  - `tests/test_step12_summary.py` expanded with matrix summary case
- Validation rerun:
  - `conda run -n isd-mvp pytest -q tests/test_step12_summary.py` -> `3 passed`
  - `conda run -n isd-mvp python scripts/run_step12_gate.py` -> `overallStatus=PASSED`
  - `conda run -n isd-mvp pytest -q` -> `56 passed`

## Incremental Update (2026-04-22, P2-11)
11. P2-11 (Windows release and operations hardening): done
- Windows release packaging and version governance:
  - added semver/version-sync tooling:
    - `scripts/versioning.py`
    - `scripts/check_version_sync.py`
  - added Windows portable package builder:
    - `scripts/build_windows_release.py`
  - added release gate:
    - `scripts/run_windows_release_gate.py`
  - release output:
    - `workspace/releases/windows/isd-v<version>-<timestamp>/`
- Startup initialization and upgrade migration strategy:
  - added runtime startup manager:
    - `src/isd/runtime/startup.py`
  - app entry now performs:
    - first-run workspace/runtime state initialization
    - version-change detection
    - pre-upgrade DB backup (`workspace/backups/db/`)
    - startup finalization with exit status persistence
- Crash logging and rollback operations:
  - added global exception capture:
    - `src/isd/runtime/crash.py`
    - integrated into `src/isd/__main__.py`
  - added rollback tool:
    - `scripts/rollback_workspace.py`
  - added diagnostics pack tool:
    - `scripts/collect_diagnostics.py`
- Logging hardening:
  - `configure_logging` now supports file output (`workspace/logs/app.log`) and idempotent setup
- Documentation:
  - `docs/windows_release_runbook.md`
  - `docs/windows_troubleshooting_manual.md`
  - updated `README.md`
- Tests added:
  - `tests/test_runtime_startup.py`
  - `tests/test_runtime_crash.py`
- Validation rerun:
  - `conda run -n isd-mvp pytest -q` -> `59 passed`
  - `conda run -n isd-mvp python scripts/run_step12_gate.py` -> `overallStatus=PASSED`
  - `conda run -n isd-mvp python scripts/run_p0_gate.py` -> `overallStatus=PASSED`
  - `conda run -n isd-mvp python scripts/run_windows_release_gate.py` -> `overallStatus=PASSED`
  - `conda run -n isd-mvp python scripts/run_release_freeze.py` -> `overallStatus=PASSED`

## Incremental Update (2026-04-23, P2-12)
12. P2-12 (final acceptance and freeze closeout): done
- Step12 closeout workflow completed:
  - added one-click closeout runner:
    - `scripts/run_step12_closeout.py`
  - closes the acceptance loop by:
    - running freeze snapshot + version sync checks
    - generating acceptance sign-off records
    - creating freeze archive package (`zip`) with docs and key reports
- New artifacts:
  - `workspace/reports/step12_closeout_summary.json`
  - `workspace/reports/mvp_acceptance_signoff.json`
  - `workspace/reports/mvp_acceptance_signoff.md`
  - `workspace/releases/freeze/isd-freeze-v<version>-<timestamp>/`
  - `workspace/releases/freeze/isd-freeze-v<version>-<timestamp>.zip`
- Tests:
  - added `tests/test_step12_closeout.py`
- Validation rerun:
  - `conda run -n isd-mvp pytest -q tests/test_step12_closeout.py` -> `2 passed`
  - `conda run -n isd-mvp python scripts/run_step12_closeout.py --signed-by codex_step12_closeout` -> `overallStatus=PASSED`
  - closeout run includes nested:
    - `conda run -n isd-mvp python scripts/run_release_freeze.py` -> `overallStatus=PASSED`
    - `conda run -n isd-mvp python scripts/check_version_sync.py` -> `Version check passed: 0.1.0`
