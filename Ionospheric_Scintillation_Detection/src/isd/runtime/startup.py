from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


@dataclass(frozen=True)
class StartupReport:
    workspace_root: Path
    database_path: Path
    state_file_path: Path
    app_version: str
    install_id: str
    first_run: bool
    upgrade_detected: bool
    previous_version: str | None
    db_backup_path: Path | None
    started_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspaceRoot": str(self.workspace_root),
            "databasePath": str(self.database_path),
            "stateFilePath": str(self.state_file_path),
            "appVersion": self.app_version,
            "installId": self.install_id,
            "firstRun": self.first_run,
            "upgradeDetected": self.upgrade_detected,
            "previousVersion": self.previous_version,
            "dbBackupPath": str(self.db_backup_path) if self.db_backup_path else None,
            "startedAt": self.started_at,
        }


def prepare_startup(workspace_root: Path, database_path: Path, app_version: str) -> StartupReport:
    workspace_root = workspace_root.resolve()
    database_path = database_path.resolve()

    (workspace_root / "runtime").mkdir(parents=True, exist_ok=True)
    (workspace_root / "backups" / "db").mkdir(parents=True, exist_ok=True)
    (workspace_root / "logs" / "crash").mkdir(parents=True, exist_ok=True)

    state_file = workspace_root / "runtime" / "startup_state.json"
    state = _safe_load_json(state_file)
    install_id = str(state.get("installId") or uuid.uuid4())

    previous_version = str(state.get("appVersion") or "").strip() or None
    first_run = not bool(state)
    upgrade_detected = bool(previous_version and previous_version != app_version)
    db_backup_path: Path | None = None

    if upgrade_detected and database_path.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = workspace_root / "backups" / "db"
        db_backup_path = backup_dir / f"isd_preupgrade_{previous_version}_to_{app_version}_{timestamp}.sqlite3"
        shutil.copy2(database_path, db_backup_path)

    started_at = _utc_now()
    run_record = {
        "installId": install_id,
        "appVersion": app_version,
        "firstRunAt": state.get("firstRunAt") or started_at,
        "lastStartupAt": started_at,
        "previousVersion": previous_version,
        "upgradeDetected": upgrade_detected,
        "lastDbBackupPath": str(db_backup_path) if db_backup_path else None,
    }
    _atomic_write_json(state_file, run_record)

    return StartupReport(
        workspace_root=workspace_root,
        database_path=database_path,
        state_file_path=state_file,
        app_version=app_version,
        install_id=install_id,
        first_run=first_run,
        upgrade_detected=upgrade_detected,
        previous_version=previous_version,
        db_backup_path=db_backup_path,
        started_at=started_at,
    )


def finalize_startup(report: StartupReport, *, exit_code: int, crash_log_path: Path | None = None) -> None:
    state = _safe_load_json(report.state_file_path)
    state.update(
        {
            "installId": report.install_id,
            "appVersion": report.app_version,
            "firstRunAt": state.get("firstRunAt") or report.started_at,
            "lastStartupAt": report.started_at,
            "lastExitCode": int(exit_code),
            "lastExitAt": _utc_now(),
            "previousVersion": report.previous_version,
            "upgradeDetected": report.upgrade_detected,
            "lastDbBackupPath": str(report.db_backup_path) if report.db_backup_path else state.get("lastDbBackupPath"),
            "lastCrashLogPath": str(crash_log_path.resolve()) if crash_log_path else None,
        }
    )
    _atomic_write_json(report.state_file_path, state)

