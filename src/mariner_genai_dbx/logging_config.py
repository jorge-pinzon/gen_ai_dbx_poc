"""Structured, privacy-preserving operational logging."""

from __future__ import annotations

import json
import logging
import re
import sys
import traceback
from datetime import datetime, timezone


_SENSITIVE_VALUE = re.compile(
    r"(?i)(authorization|cookie|set-cookie|client[_-]?secret|password|access[_-]?token|"
    r"refresh[_-]?token|question|answer)\s*[:=]\s*([^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_EXTRA_FIELDS = (
    "event",
    "request_id",
    "method",
    "route",
    "status",
    "duration_ms",
    "exception_type",
)


def sanitize_log_text(value: object) -> str:
    """Redact common secret and business-content fields from controlled messages."""
    text = str(value)
    text = _BEARER_TOKEN.sub("Bearer [REDACTED]", text)
    return _SENSITIVE_VALUE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


class JsonFormatter(logging.Formatter):
    """Emit an allow-listed JSON object and a message-free exception trace."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_log_text(record.getMessage()),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            exception_type, _exception, trace = record.exc_info
            payload["exception_type"] = exception_type.__name__
            payload["stack_trace"] = [
                {
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": frame.name,
                }
                for frame in traceback.extract_tb(trace)
            ]
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    """Configure application loggers to write one JSON document per stdout line."""
    package_logger = logging.getLogger("mariner_genai_dbx")
    for handler in tuple(package_logger.handlers):
        if getattr(handler, "_mariner_json_handler", False):
            package_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._mariner_json_handler = True  # type: ignore[attr-defined]
    package_logger.addHandler(handler)
    package_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    package_logger.propagate = False
