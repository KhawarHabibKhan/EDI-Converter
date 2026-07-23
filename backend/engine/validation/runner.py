"""SNIP validation runner — parse once, run Levels 1..N cumulatively.

Public entry point for the ``POST /edi/validate`` endpoint. Runs Level 1
(envelope) always, then Levels 2..``snip_level`` of transaction-type-specific
rules, and returns a merged, de-duplicated, position-sorted issue list plus the
detected transaction type and applied level.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine import detector, x12_reader
from engine.validation import HIGHEST_LEVEL, issue, level1, level2, level3, level4, level5


def validate(raw: str, snip_level: Optional[int] = None) -> Dict[str, Any]:
    """Validate raw EDI up to ``snip_level`` (default: highest implemented)."""
    level = HIGHEST_LEVEL if snip_level is None else max(1, min(int(snip_level), HIGHEST_LEVEL))

    try:
        doc = x12_reader.parse(raw)
    except ValueError:
        return {
            "transaction_type": None,
            "snip_level": level,
            "issues": [issue.make(issue.ERROR, 1, "No EDI segments found; not a valid X12 interchange.")],
        }

    issues: List[Dict[str, Any]] = level1.check(doc)

    txn_type: Optional[str] = None
    try:
        txn_type = detector.detect_from_doc(doc)
    except detector.DetectionError:
        txn_type = None

    if level >= 2 and txn_type:
        issues += level2.check(doc, txn_type)
    if level >= 3 and txn_type:
        issues += level3.check(doc, txn_type)
    if level >= 4 and txn_type:
        issues += level4.check(doc, txn_type)
    if level >= 5 and txn_type:
        issues += level5.check(doc, txn_type)

    return {
        "transaction_type": txn_type,
        "snip_level": level,
        "issues": _dedup_sort(issues),
    }


def _dedup_sort(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique: List[Dict[str, Any]] = []
    for it in issues:
        key = (it["severity"], it.get("level"), it["message"], it.get("segment", ""), it.get("position", 0))
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
    unique.sort(key=lambda i: (i.get("position", 0), i.get("level", 0), issue.severity_rank(i["severity"])))
    return unique
