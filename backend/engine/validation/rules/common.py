"""Shared predicates for SNIP Level-2 (Requirement) rules.

Small, reusable helpers over the parsed ``EdiDocument`` so each transaction's
rule module reads as a list of requirements rather than a wall of ``if``s. Each
helper returns a list of issue dicts (empty = satisfied). Level defaults to 2.

Design: data + small predicates (docx/v3/3-snip-rules.md §3.4). These check
segment/element **presence** and basic **data types** — the core of Level 2.
Full loop-structure/repeat validation is layered on where it adds value.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.validation.issue import ERROR, make
from engine.x12_reader import EdiDocument, Segment


def _indexed(doc: EdiDocument):
    """Yield (1-based position, segment) pairs for issue locations."""
    return enumerate(doc.segments, start=1)


def occurrences(doc: EdiDocument, seg_id: str) -> List[Segment]:
    return [s for s in doc.segments if s.seg_id == seg_id]


def qualified(doc: EdiDocument, seg_id: str, idx: int, value: str) -> List[Segment]:
    """Segments of ``seg_id`` whose element ``idx`` equals ``value``."""
    return [s for s in doc.segments if s.seg_id == seg_id and s.el(idx) == value]


def position_of(doc: EdiDocument, seg: Segment) -> int:
    for i, s in _indexed(doc):
        if s is seg:
            return i
    return 0


# --------------------------------------------------------------------------- #
#  Requirement predicates
# --------------------------------------------------------------------------- #
def require_segment(doc: EdiDocument, seg_id: str, desc: str, level: int = 2) -> List[Dict[str, Any]]:
    """At least one ``seg_id`` must be present."""
    if not occurrences(doc, seg_id):
        return [make(ERROR, level, f"Missing required segment {seg_id} ({desc}).", seg_id)]
    return []


def require_qualified(
    doc: EdiDocument, seg_id: str, idx: int, value: str, desc: str,
    required_elems: Optional[List[int]] = None, level: int = 2,
) -> List[Dict[str, Any]]:
    """At least one ``seg_id`` with element ``idx == value`` must be present, and
    (on the first match) any ``required_elems`` positions must be non-empty."""
    matches = qualified(doc, seg_id, idx, value)
    if not matches:
        return [make(ERROR, level, f"Missing required {seg_id}*{value} ({desc}).", seg_id)]
    if required_elems:
        seg = matches[0]
        pos = position_of(doc, seg)
        return _missing_elements(seg, required_elems, f"{seg_id}*{value} ({desc})", seg_id, pos, level)
    return []


def require_elements(
    doc: EdiDocument, seg_id: str, positions: List[int], desc: str, level: int = 2,
    first_only: bool = True,
) -> List[Dict[str, Any]]:
    """Required element positions must be non-empty on the first (or every)
    occurrence of ``seg_id``. Skips entirely if the segment is absent (use
    ``require_segment`` for presence)."""
    segs = occurrences(doc, seg_id)
    if not segs:
        return []
    targets = segs[:1] if first_only else segs
    issues: List[Dict[str, Any]] = []
    for seg in targets:
        pos = position_of(doc, seg)
        issues += _missing_elements(seg, positions, f"{seg_id} ({desc})", seg_id, pos, level)
    return issues


def require_any(
    doc: EdiDocument, seg_id: str, idx: int, values: List[str], desc: str, level: int = 2,
) -> List[Dict[str, Any]]:
    """At least one ``seg_id`` whose element ``idx`` is in ``values``."""
    for s in occurrences(doc, seg_id):
        if s.el(idx) in values:
            return []
    joined = "/".join(values)
    return [make(ERROR, level, f"Missing required {seg_id} with {seg_id}{idx:02d} in [{joined}] ({desc}).", seg_id)]


def _missing_elements(
    seg: Segment, positions: List[int], label: str, seg_id: str, pos: int, level: int,
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for p in positions:
        if not (seg.el(p) or "").strip():
            issues.append(make(ERROR, level, f"{label} missing required element {seg_id}{p:02d}.", seg_id, pos))
    return issues


# --------------------------------------------------------------------------- #
#  Data-type predicates
# --------------------------------------------------------------------------- #
def check_decimal_element(
    doc: EdiDocument, seg_id: str, idx: int, desc: str, level: int = 2,
) -> List[Dict[str, Any]]:
    """Element ``idx`` on each ``seg_id`` must parse as a decimal amount when present."""
    issues: List[Dict[str, Any]] = []
    for pos, s in _indexed(doc):
        if s.seg_id != seg_id:
            continue
        raw = (s.el(idx) or "").strip()
        if raw and not _is_decimal(raw):
            issues.append(make(ERROR, level, f"{seg_id}{idx:02d} '{raw}' is not a valid amount ({desc}).", seg_id, pos))
    return issues


def check_d8_dates(
    doc: EdiDocument, seg_id: str, fmt_idx: int, val_idx: int, desc: str, level: int = 2,
) -> List[Dict[str, Any]]:
    """When a DTP/DTM format element == 'D8', the date value must be CCYYMMDD."""
    issues: List[Dict[str, Any]] = []
    for pos, s in _indexed(doc):
        if s.seg_id != seg_id:
            continue
        if (s.el(fmt_idx) or "").strip() == "D8":
            val = (s.el(val_idx) or "").strip()
            if val and not (len(val) == 8 and val.isdigit()):
                issues.append(make(ERROR, level, f"{seg_id} D8 date '{val}' is not CCYYMMDD ({desc}).", seg_id, pos))
    return issues


def _is_decimal(raw: str) -> bool:
    try:
        float(raw)
        return True
    except ValueError:
        return False
