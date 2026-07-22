"""Structural EDI validation.

Checks the X12 envelope integrity (ISA/IEA, GS/GE, ST/SE pairing, control-number
matching, and segment counts) and returns a list of issues. This is structural
validation, not full HIPAA implementation-guide validation.
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine import x12_reader

KNOWN_TRANSACTIONS = {"837", "835", "834", "270", "271", "276", "277"}


def _issue(severity: str, message: str, segment: str = "", position: int = 0) -> Dict[str, Any]:
    return {"severity": severity, "message": message, "segment": segment, "position": position}


def validate_edi(raw: str) -> List[Dict[str, Any]]:
    """Validate raw EDI text and return a list of issues (empty = clean)."""
    issues: List[Dict[str, Any]] = []
    try:
        doc = x12_reader.parse(raw)
    except ValueError:
        return [_issue("ERROR", "No EDI segments found; not a valid X12 interchange.")]

    segs = doc.segments

    # --- Interchange envelope (ISA / IEA) ------------------------------- #
    isa = [s for s in segs if s.seg_id == "ISA"]
    iea = [s for s in segs if s.seg_id == "IEA"]
    if not isa:
        issues.append(_issue("WARNING", "Missing ISA interchange header.", "ISA"))
    elif segs[0].seg_id != "ISA":
        issues.append(_issue("WARNING", "Interchange does not start with ISA.", "ISA", 1))
    if isa and not iea:
        issues.append(_issue("ERROR", "Missing IEA interchange trailer.", "IEA"))
    if isa and iea and isa[0].el(13) and isa[0].el(13) != iea[-1].el(2):
        issues.append(_issue(
            "ERROR",
            f"IEA02 control number '{iea[-1].el(2)}' does not match ISA13 "
            f"'{isa[0].el(13)}'.", "IEA"))

    # --- Functional groups and transaction sets ------------------------ #
    group = None
    txn = None
    group_count = 0

    for i, s in enumerate(segs, start=1):
        sid = s.seg_id

        if sid == "GS":
            group = {"control": s.el(6), "st_count": 0}
            group_count += 1
        elif sid == "GE":
            if group is None:
                issues.append(_issue("ERROR", "GE trailer without a matching GS.", "GE", i))
            else:
                declared = _as_int(s.el(1))
                if declared is not None and declared != group["st_count"]:
                    issues.append(_issue(
                        "ERROR",
                        f"GE01 declares {declared} transaction set(s) but "
                        f"{group['st_count']} were found.", "GE", i))
                if s.el(2) and s.el(2) != group["control"]:
                    issues.append(_issue(
                        "ERROR",
                        f"GE02 control '{s.el(2)}' does not match GS06 "
                        f"'{group['control']}'.", "GE", i))
                group = None
        elif sid == "ST":
            if group is not None:
                group["st_count"] += 1
            txn = {"control": s.el(2), "code": s.el(1), "start": i}
            if s.el(1) and s.el(1) not in KNOWN_TRANSACTIONS:
                issues.append(_issue(
                    "WARNING",
                    f"Transaction set type '{s.el(1)}' is not a recognized "
                    "healthcare type.", "ST", i))
        elif sid == "SE":
            if txn is None:
                issues.append(_issue("ERROR", "SE trailer without a matching ST.", "SE", i))
            else:
                count = i - txn["start"] + 1
                declared = _as_int(s.el(1))
                if declared is not None and declared != count:
                    issues.append(_issue(
                        "ERROR",
                        f"SE01 segment count {declared} does not match the actual "
                        f"count {count}.", "SE", i))
                if s.el(2) and s.el(2) != txn["control"]:
                    issues.append(_issue(
                        "ERROR",
                        f"SE02 control '{s.el(2)}' does not match ST02 "
                        f"'{txn['control']}'.", "SE", i))
                txn = None

    if group is not None:
        issues.append(_issue("ERROR", "GS group without a matching GE trailer.", "GS"))
    if txn is not None:
        issues.append(_issue("ERROR", "ST transaction set without a matching SE.", "ST"))

    if isa and iea:
        declared_groups = _as_int(iea[-1].el(1))
        if declared_groups is not None and declared_groups != group_count:
            issues.append(_issue(
                "ERROR",
                f"IEA01 declares {declared_groups} functional group(s) but "
                f"{group_count} were found.", "IEA"))

    return issues


def _as_int(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
