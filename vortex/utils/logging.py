"""Vortex logging utilities.

This module centralises structured logging configuration so every subsystem
emits JSON logs by default while still supporting colourful Rich output on the
console. The goal is to make log aggregation trivial in production while keeping
local developer ergonomics high.
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from rich.logging import RichHandler
except Exception:  # pragma: no cover - optional dependency
    RichHandler = None


class JsonFormatter(logging.Formatter):
    """Format log records as JSON documents.

    Logging is frequently ingested by systems such as ELK or OpenSearch. Using
    JSON ensures predictable parsing and allows operators to add custom fields
    easily. The formatter keeps the record lean while still exposing key
    metadata such as timestamps, severity, and source location.
    """

    default_time_format = "%Y-%m-%dT%H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.utcfromtimestamp(record.created).strftime(
                self.default_time_format
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        for key in ("request_id", "task_id", "user_id"):
            if key in record.__dict__:
                payload[key] = record.__dict__[key]
        return json.dumps(payload, ensure_ascii=False)


def _build_handlers(log_dir: Path, enable_rich: bool) -> Dict[str, Dict[str, Any]]:
    handlers: Dict[str, Dict[str, Any]] = {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": str(log_dir / "vortex.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
        }
    }
    if enable_rich and RichHandler is not None:
        handlers["console"] = {
            "class": "rich.logging.RichHandler",
            "formatter": "rich",
            "level": "DEBUG",
            "rich_tracebacks": True,
            "show_path": False,
        }
    else:
        handlers["console"] = {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    return handlers


def configure_logging(*, level: str = "INFO", log_dir: Optional[Path] = None) -> None:
    """Configure global logging for the Vortex application.

    Parameters
    ----------
    level:
        Minimum severity that should be emitted. Accepts standard logging level
        names.
    log_dir:
        Directory where persistent logs are written. When omitted the function
        falls back to ``$VORTEX_LOG_DIR`` or ``.vortex/logs`` within the user's
        home directory.

    The function is idempotent and safe to call multiple times. This behaviour
    simplifies testing because each test can reconfigure logging without
    worrying about duplicate handlers.
    """

    log_dir = log_dir or Path(os.environ.get("VORTEX_LOG_DIR", Path.home() / ".vortex" / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    enable_rich = os.environ.get("VORTEX_RICH", "1") != "0"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "vortex.utils.logging.JsonFormatter",
            },
            "rich": {
                "format": "%(message)s",
                "datefmt": "%H:%M:%S",
            },
        },
        "handlers": _build_handlers(log_dir, enable_rich),
        "root": {
            "level": level,
            "handlers": list(_build_handlers(log_dir, enable_rich).keys()),
        },
    }

    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance.

    Using this helper ensures every module uses the same configuration, which
    is essential when running in multiprocessing or asyncio-heavy scenarios.
    The function also allows future enhancements such as structured context
    propagation.
    """

    return logging.getLogger(name)


__all__ = ["configure_logging", "get_logger", "JsonFormatter"]
