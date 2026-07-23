"""SNIP issue builder.

Extends the v1 issue shape (severity/message/segment/position) with a SNIP
``level`` so the UI can label and filter by level. Kept tiny and dependency-free.
"""

from __future__ import annotations

from typing import Any, Dict

ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"

_SEVERITY_RANK = {ERROR: 0, WARNING: 1, INFO: 2}


def make(severity: str, level: int, message: str, segment: str = "", position: int = 0) -> Dict[str, Any]:
    return {
        "severity": severity,
        "level": level,
        "message": message,
        "segment": segment,
        "position": position,
    }


def severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, 3)
