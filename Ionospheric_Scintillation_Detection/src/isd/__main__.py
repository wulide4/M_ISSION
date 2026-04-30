from __future__ import annotations

import sys
from pathlib import Path

from isd import __version__
from isd.application.bootstrap import bootstrap
from isd.runtime import finalize_startup, install_global_exception_hooks, log_exception, prepare_startup
from isd.settings import settings
from isd.ui.main_window import run


def _resolve_base_dir() -> Path:
    """Return the isd package directory, handling both normal and PyInstaller frozen modes."""
    if getattr(sys, 'frozen', False):
        # PyInstaller: packages are under sys._MEIPASS/isd/
        return Path(sys._MEIPASS) / 'isd'
    return Path(__file__).resolve().parent


def main() -> int:
    base_dir = _resolve_base_dir()
    startup = prepare_startup(
        workspace_root=settings.workspace_path,
        database_path=settings.database_path,
        app_version=__version__,
    )
    crash_dir = startup.workspace_root / "logs" / "crash"
    install_global_exception_hooks(
        crash_dir=crash_dir,
        app_version=__version__,
        extra_context={"startup": startup.to_dict()},
    )

    crash_file: Path | None = None
    exit_code = 1
    try:
        context = bootstrap(base_dir)
        exit_code = run(context)
        return exit_code
    except Exception as exc:  # noqa: BLE001
        crash_file = log_exception(
            crash_dir=crash_dir,
            exc_type=type(exc),
            exc_value=exc,
            exc_tb=exc.__traceback__,
            source="app_bootstrap",
            app_version=__version__,
            extra_context={"startup": startup.to_dict()},
        )
        print(f"[ISD] Unhandled startup/runtime exception logged to: {crash_file}")
        return 1
    finally:
        finalize_startup(startup, exit_code=exit_code, crash_log_path=crash_file)


if __name__ == "__main__":
    raise SystemExit(main())

