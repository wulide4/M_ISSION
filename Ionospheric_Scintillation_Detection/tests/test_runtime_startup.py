from __future__ import annotations

from pathlib import Path

from isd.runtime.startup import finalize_startup, prepare_startup


def test_prepare_startup_first_run(tmp_path: Path):
    workspace = tmp_path / "workspace"
    db_path = workspace / "isd.sqlite3"

    report = prepare_startup(workspace, db_path, "0.1.0")
    assert report.first_run is True
    assert report.upgrade_detected is False
    assert report.db_backup_path is None
    assert report.state_file_path.exists()

    finalize_startup(report, exit_code=0)
    state_text = report.state_file_path.read_text(encoding="utf-8")
    assert '"lastExitCode": 0' in state_text


def test_prepare_startup_upgrade_creates_db_backup(tmp_path: Path):
    workspace = tmp_path / "workspace"
    db_path = workspace / "isd.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"sqlite-data")

    first = prepare_startup(workspace, db_path, "0.1.0")
    finalize_startup(first, exit_code=0)

    second = prepare_startup(workspace, db_path, "0.2.0")
    assert second.first_run is False
    assert second.upgrade_detected is True
    assert second.previous_version == "0.1.0"
    assert second.db_backup_path is not None
    assert second.db_backup_path.exists()

    crash_file = workspace / "logs" / "crash" / "demo_crash.json"
    crash_file.write_text("{}", encoding="utf-8")
    finalize_startup(second, exit_code=1, crash_log_path=crash_file)
    state_text = second.state_file_path.read_text(encoding="utf-8")
    assert '"lastExitCode": 1' in state_text
    assert "demo_crash.json" in state_text

