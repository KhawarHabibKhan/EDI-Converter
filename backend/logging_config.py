"""Logging for the EDI-Converter API.

The hard constraint here is that this service handles PHI. Request bodies are
claims — patient names, member IDs, diagnoses — so **nothing derived from a
request body is ever logged**: not the content, not the parsed result, not the
validation messages (which quote segment values), and not the uploaded filename,
which in practice often carries a patient name or claim number.

What is logged is the shape of the traffic: method, path, status, duration, and
the byte size of the upload. That is enough to answer "is it up, is it slow, is
it erroring" without turning the log into a PHI store.

Level and format come from the environment so an operator can turn detail up
without a code change:

    EDI_LOG_LEVEL=DEBUG      # default INFO
    EDI_LOG_FORMAT=json      # default text
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

LOGGER_NAME = "edi"


class JsonFormatter(logging.Formatter):
    """One JSON object per line — for log shippers that parse structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Anything attached via `extra=` rides along, so request fields are
        # queryable instead of buried in the message string.
        for key, value in getattr(record, "context", {}).items():
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def configure_logging() -> logging.Logger:
    """Install a single stdout handler. Idempotent — safe under uvicorn reload."""
    level = os.getenv("EDI_LOG_LEVEL", "INFO").upper()
    fmt = os.getenv("EDI_LOG_FORMAT", "text").lower()

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s  %(message)s")
        )

    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()          # avoid duplicate lines on reload
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False
    return logger


log = logging.getLogger(LOGGER_NAME)


async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Log one line per request, and attach a correlation id to the response.

    The id lets a user reporting "it failed at 14:02" be matched to a log line
    without anyone having to reproduce the upload.
    """
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()

    context = {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,          # path only — query strings excluded
        "bytes_in": request.headers.get("content-length", "0"),
    }

    try:
        response = await call_next(request)
    except Exception:
        # Log the traceback, then let the handler produce the 500. The exception
        # text is ours, not the file's — the endpoints never put body content
        # into error messages.
        log.exception(
            "request failed",
            extra={"context": {**context, "duration_ms": _ms(started)}},
        )
        raise

    context["status"] = response.status_code
    context["duration_ms"] = _ms(started)

    # 5xx is our bug, 4xx is the caller's input, 2xx is routine.
    level = logging.ERROR if response.status_code >= 500 else (
        logging.WARNING if response.status_code >= 400 else logging.INFO
    )
    log.log(
        level,
        "%(method)s %(path)s -> %(status)s in %(duration_ms)sms" % context,
        extra={"context": context},
    )

    response.headers["X-Request-ID"] = request_id
    return response


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
