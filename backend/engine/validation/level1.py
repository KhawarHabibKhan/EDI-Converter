"""SNIP Level 1 — Integrity (envelope).

Reuses the existing, tested envelope logic in ``engine.validator`` (no
re-parse), tagging each issue with ``level = 1`` for the SNIP report.
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine import validator, x12_reader


def check(doc: x12_reader.EdiDocument) -> List[Dict[str, Any]]:
    """Return Level-1 envelope issues for an already-parsed document."""
    return [_with_level(i) for i in validator.validate_doc(doc)]


def _with_level(issue: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "severity": issue.get("severity"),
        "level": 1,
        "message": issue.get("message"),
        "segment": issue.get("segment", ""),
        "position": issue.get("position", 0),
    }
