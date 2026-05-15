from __future__ import annotations

import logging
from pathlib import Path

import structlog

_CONFIGURED = False


def configure_logging(log_dir: Path | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_dir / "app.log", encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=handlers,
    )
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str):
    return structlog.get_logger(name)

