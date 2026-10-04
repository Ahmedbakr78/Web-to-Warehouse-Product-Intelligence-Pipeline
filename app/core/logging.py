"""Logging configuration: human friendly console output plus optional JSON logs."""

from __future__ import annotations

import logging
import logging.handlers
import sys
import time
from typing import Any

from app.core.config import settings

_CONFIGURED = False

LEVEL_COLORS = {
    "DEBUG": "\033[0;36m",
    "INFO": "\033[0;32m",
    "WARNING": "\033[0;33m",
    "ERROR": "\033[0;31m",
    "CRITICAL": "\033[1;41m",
}
RESET = "\033[0m"


class _AnsiFormatter(logging.Formatter):
    """Colourised single-line console formatter (disabled when not a TTY)."""

    def __init__(self, use_color: bool = True) -> None:
        super().__init__("%(message)s")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not self.use_color:
            return message
        colour = LEVEL_COLORS.get(record.levelname, "")
        if not colour:
            return message
        return f"{colour}{message}{RESET}"


class _JsonFormatter(logging.Formatter):
    """Minimal dependency-free JSON formatter for log shippers."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None, force: bool = False) -> logging.Logger:
    """Idempotently configure the root logger and return the app logger."""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return logging.getLogger("app")

    resolved_level = (level or settings.app_log_level).upper()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stderr)
    if settings.app_log_format == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            _AnsiFormatter(use_color=sys.stderr.isatty())
            if resolved_level in {"DEBUG", "INFO"}
            else logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )

    root.addHandler(handler)
    root.setLevel(resolved_level)

    # Quieten noisy third-party loggers.
    for noisy in ("urllib3", "httpx", "httpcore", "asyncio", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    _CONFIGURED = True
    return logging.getLogger("app")


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child logger (e.g. ``app.etl.pipeline``)."""
    configure_logging()
    return logging.getLogger(name)


def setup_file_logging(filename: str = "pipeline.log", level: str = "DEBUG") -> None:
    """Attach a rotating file handler (used by the CLI when ``--log-file`` is passed)."""
    settings.ensure_directories()
    path = settings.log_dir / filename
    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(level.upper())
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)-38s | %(message)s")
    )
    logging.getLogger().addHandler(file_handler)


logger = configure_logging()

__all__ = ["configure_logging", "get_logger", "setup_file_logging", "logger"]