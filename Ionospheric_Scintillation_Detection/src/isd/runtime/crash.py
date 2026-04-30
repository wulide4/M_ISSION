from __future__ import annotations

import json
import os
import platform
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_traceback_text(exc_type: type[BaseException], exc_value: BaseException, exc_tb: TracebackType | None) -> str:
    return "".join(traceback.format_exception(exc_type, exc_value, exc_tb))


def _write_payload(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _build_payload(
    *,
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
    source: str,
    app_version: str,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "timestampUtc": _utc_now(),
        "source": source,
        "appVersion": app_version,
        "pythonVersion": sys.version,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "exceptionType": getattr(exc_type, "__name__", str(exc_type)),
        "message": str(exc_value),
        "traceback": _to_traceback_text(exc_type, exc_value, exc_tb),
        "context": extra_context or {},
    }


def log_exception(
    crash_dir: Path,
    *,
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
    source: str,
    app_version: str,
    extra_context: dict[str, Any] | None = None,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fname = f"crash_{source}_{timestamp}_{os.getpid()}.json"
    payload = _build_payload(
        exc_type=exc_type,
        exc_value=exc_value,
        exc_tb=exc_tb,
        source=source,
        app_version=app_version,
        extra_context=extra_context,
    )
    return _write_payload(crash_dir / fname, payload)


def install_global_exception_hooks(
    crash_dir: Path,
    *,
    app_version: str,
    extra_context: dict[str, Any] | None = None,
) -> None:
    previous_hook = sys.excepthook
    previous_thread_hook = getattr(threading, "excepthook", None)

    def _sys_hook(exc_type, exc_value, exc_tb):
        log_exception(
            crash_dir,
            exc_type=exc_type,
            exc_value=exc_value,
            exc_tb=exc_tb,
            source="main",
            app_version=app_version,
            extra_context=extra_context,
        )
        if previous_hook:
            previous_hook(exc_type, exc_value, exc_tb)

    def _thread_hook(args: threading.ExceptHookArgs):
        log_exception(
            crash_dir,
            exc_type=args.exc_type,
            exc_value=args.exc_value,
            exc_tb=args.exc_traceback,
            source=f"thread_{args.thread.name if args.thread else 'unknown'}",
            app_version=app_version,
            extra_context=extra_context,
        )
        if previous_thread_hook:
            previous_thread_hook(args)

    sys.excepthook = _sys_hook
    if previous_thread_hook is not None:
        threading.excepthook = _thread_hook

