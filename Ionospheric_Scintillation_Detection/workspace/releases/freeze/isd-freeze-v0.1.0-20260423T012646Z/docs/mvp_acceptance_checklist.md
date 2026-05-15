# MVP Acceptance Checklist
Date: 2026-04-21

## A. Environment
- [ ] Conda env available: `isd-mvp`
- [ ] `conda run -n isd-mvp pytest -q` passes
- [ ] Step12 gate passes:
  - [ ] `conda run -n isd-mvp python scripts/run_step12_gate.py`
  - [ ] `workspace/reports/regression_step12_summary_24084.json` has `overallStatus=PASSED`
  - [ ] `workspace/reports/regression_step12_summary_matrix.json` has `overallStatus=PASSED`

## B. End-to-End Demo
- [ ] Run one-click MVP demo:
  - [ ] `conda run -n isd-mvp python scripts/run_mvp_demo.py`
- [ ] Summary file generated:
  - [ ] `workspace/reports/mvp_demo_summary.json`
- [ ] Demo report generated:
  - [ ] `workspace/reports/mvp_demo_<taskId>_report.txt`
- [ ] Demo result export generated:
  - [ ] `workspace/reports/mvp_demo_<taskId>_first.mat`
  - [ ] `workspace/reports/mvp_demo_<taskId>_first.parquet`

## C. UI Verification
- [ ] Project management page can create and scan project
- [ ] Data calculation page can validate/create/start task
- [ ] Task runs to `COMPLETED` with logs visible
- [ ] Visualization page:
  - [ ] Result list visible
  - [ ] Time-series visible
  - [ ] Grid tab behaves correctly for grid/non-grid results
  - [ ] Risk flags shown in detail panel
- [ ] Analysis page:
  - [ ] Metric/station filters work
  - [ ] Metric detail updates with selection
- [ ] Report center:
  - [ ] Can load results by project id
  - [ ] Can preview and export report
  - [ ] Risk flags shown in report preview panel

## D. Governance Checks
- [ ] Task validation response includes `riskFlags`
- [ ] Result detail includes chain/sampling and risk flags
- [ ] Report preview summary includes risk flags
- [ ] Export supports `NPZ/Parquet/MAT/JSON`

## E. Freeze Decision
- [ ] Known blockers list empty or accepted
- [ ] Regression threshold policy signed off
- [ ] Demo script and docs committed
- [ ] Freeze snapshot script passes:
  - [ ] `conda run -n isd-mvp python scripts/run_release_freeze.py`
  - [ ] `workspace/reports/release_freeze_snapshot.json` has `overallStatus=PASSED`
- [ ] Windows release gate passes:
  - [ ] `conda run -n isd-mvp python scripts/run_windows_release_gate.py`
  - [ ] `workspace/reports/windows_release_gate_summary.json` has `overallStatus=PASSED`
- [ ] Ready for MVP freeze tag
