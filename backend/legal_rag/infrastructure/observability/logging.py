"""JSON logging on stdout with a request-id context var set by HTTP middleware."""
from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Any

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_STANDARD = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime",
}


class JsonFormatter(logging.Formatter):
    """One-line JSON records; every ``extra`` kwarg is emitted as a top-level key."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = _request_id_var.get()
        if rid is not None:
            payload["request_id"] = rid
        for key, value in record.__dict__.items():
            if key in _STANDARD or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = _request_id_var.get()
        prefix = f"[{rid}] " if rid else ""
        base = f"{time.strftime('%H:%M:%S', time.gmtime(record.created))} " \
               f"{record.levelname:<7} {record.name}: {prefix}{record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(level: str = "INFO", format: str = "json") -> None:
    """Install the root handler. Idempotent — safe to call multiple times."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if format == "json" else TextFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    # Quiet noisy third-party loggers by default.
    for noisy in ("chromadb", "urllib3", "httpx", "httpcore", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, logging.getLevelName(level)))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def set_request_id(request_id: str | None) -> None:
    _request_id_var.set(request_id)


def current_request_id() -> str | None:
    return _request_id_var.get()
