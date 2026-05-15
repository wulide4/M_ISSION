# Release Notes v0.1.0-mvp
Date: 2026-04-21

## Scope
This release delivers a local, offline Python desktop MVP for GNSS ionospheric scintillation workflow closure:
- import and scan
- validate and run tasks
- visualize and inspect results
- export result artifacts
- generate report output

## Delivered Capabilities
1. Project and input chain
- project create/list/delete
- recursive scan for OBS/SP3/CLK/ATX/NAV
- station metadata extraction and dependency matching

2. Task lifecycle
- validate/create/start/pause/resume/stop/retry
- runtime snapshot + structured logs + task steps
- rule-based blocking checks and risk flags in validation output

3. Metric pipeline support
- ROTI / AATR / IAATR
- cROT / DIXSG
- GPS SIGMA_PHI_F (formal)
- non-GPS SIGMA_PHI_F as experimental pathway (gated by settings/risk)

4. Result and report
- NPZ + Parquet persistence
- MAT/Parquet/NPZ/JSON export
- result visualization (series, grid, intermediate, detail)
- report preview/export with risk flag summary

5. Regression and gates
- Step12 one-click gate script
- consolidated gate summary JSON
- export-format regression included in gate

## Quality Snapshot
- `pytest`: 59 passed
- Step12 gate: passed
- MVP demo script: passed
- Windows release gate: passed

## Key Commands
- App: `conda run -n isd-mvp python -m isd`
- Full gate: `conda run -n isd-mvp python scripts/run_step12_gate.py`
- MVP demo: `conda run -n isd-mvp python scripts/run_mvp_demo.py`
- Freeze snapshot: `conda run -n isd-mvp python scripts/run_release_freeze.py`
- Windows release gate: `conda run -n isd-mvp python scripts/run_windows_release_gate.py`
- Build Windows package: `conda run -n isd-mvp python scripts/build_windows_release.py`

## Artifacts
- `workspace/reports/regression_step12_summary_24084.json`
- `workspace/reports/regression_step12_summary_matrix.json`
- `workspace/reports/mvp_demo_summary.json`
- `workspace/reports/release_freeze_snapshot.json`
- `workspace/reports/windows_release_gate_summary.json`
