"""Structured JSON logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.utils.correlation import get_correlation_id


_BASE_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonLogFormatter(logging.Formatter):
    """Format records as newline-delimited JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id and correlation_id != "-":
            payload["correlation_id"] = correlation_id

        for key, value in record.__dict__.items():
            if key in _BASE_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_json_logging() -> None:
    """Configure process-wide JSON logging and correlation-id enrichment once."""

    if getattr(configure_json_logging, "_configured", False):
        return

    base_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = base_factory(*args, **kwargs)
        if not hasattr(record, "correlation_id"):
            record.correlation_id = get_correlation_id()
        return record

    logging.setLogRecordFactory(record_factory)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        root_logger.addHandler(handler)

    for handler in root_logger.handlers:
        handler.setFormatter(JsonLogFormatter())

    root_logger.setLevel(logging.INFO)
    configure_json_logging._configured = True
