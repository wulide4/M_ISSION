from __future__ import annotations

import json
from pathlib import Path

from isd.runtime.crash import log_exception


def test_log_exception_writes_json(tmp_path: Path):
    crash_dir = tmp_path / "workspace" / "logs" / "crash"

    try:
        raise ValueError("boom")
    except ValueError as exc:
        crash_path = log_exception(
            crash_dir=crash_dir,
            exc_type=type(exc),
            exc_value=exc,
            exc_tb=exc.__traceback__,
            source="unit_test",
            app_version="0.1.0",
            extra_context={"k": "v"},
        )

    assert crash_path.exists()
    payload = json.loads(crash_path.read_text(encoding="utf-8"))
    assert payload["source"] == "unit_test"
    assert payload["appVersion"] == "0.1.0"
    assert payload["exceptionType"] == "ValueError"
    assert payload["message"] == "boom"
    assert payload["context"]["k"] == "v"
    assert "traceback" in payload

