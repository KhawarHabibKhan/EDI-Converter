"""SNIP Level 4 — Situational.

Inter-segment "if A present, then B is required" rules. Each rule encodes a TR3
situational note. Representative set (docx/v3/5-snip-rule-reference.md §5.4);
extended as guides dictate.

* **837 (P/I) accident:** if `CLM11` (related-causes) is present, an accident/
  onset date `DTP*439` is required for that claim.
* **837 (P/I) coordination of benefits:** if the claim's subscriber `SBR01`
  indicates a non-primary payer (S/T), an other-payer loop (a second `SBR`,
  loop 2320) is required.
* **837I admission:** if `CL1` (institutional admission info) is present, an
  admission date `DTP*435` is required for that claim.
* **834 coverage dates:** each `HD` (health coverage) must be accompanied by a
  begin date `DTP*348`.

Reads the already-parsed segments only. docx/v3/3-snip-rules.md §3.4.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.validation.issue import ERROR, make
from engine.x12_reader import EdiDocument

_NON_PRIMARY = {"S", "T"}


def check(doc: EdiDocument, txn_type: str) -> List[Dict[str, Any]]:
    if txn_type in ("837P", "837I", "837"):
        return _check_837(doc, institutional=(txn_type == "837I"))
    if txn_type == "834":
        return _check_834(doc)
    return []


# --------------------------------------------------------------------------- #
#  837 — accident / COB / admission
# --------------------------------------------------------------------------- #
def _check_837(doc: EdiDocument, institutional: bool) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    claim: Optional[Dict[str, Any]] = None

    def finalize(c: Optional[Dict[str, Any]]) -> None:
        if not c:
            return
        if c["accident"] and not c["has_439"]:
            issues.append(make(
                ERROR, 4,
                "Claim is accident-related (CLM11 present) but the accident/onset "
                "date (DTP*439) is missing.",
                "CLM", c["pos"],
            ))
        if institutional and c["has_cl1"] and not c["has_435"]:
            issues.append(make(
                ERROR, 4,
                "Institutional admission (CL1) is present but the admission date "
                "(DTP*435) is missing.",
                "CL1", c["pos"],
            ))

    for pos, s in enumerate(doc.segments, start=1):
        sid = s.seg_id
        if sid == "CLM":
            finalize(claim)
            claim = {
                "pos": pos,
                "accident": bool((s.el(11) or "").strip()),
                "has_439": False, "has_cl1": False, "has_435": False,
            }
        elif sid == "CL1" and claim is not None:
            claim["has_cl1"] = True
        elif sid == "DTP" and claim is not None:
            q = (s.el(1) or "").strip()
            if q == "439":
                claim["has_439"] = True
            elif q == "435":
                claim["has_435"] = True

    finalize(claim)

    # Coordination of benefits: a non-primary claim needs an other-payer loop.
    sbrs = [s for s in doc.segments if s.seg_id == "SBR"]
    if sbrs and (sbrs[0].el(1) or "").strip().upper() in _NON_PRIMARY and len(sbrs) < 2:
        issues.append(make(
            ERROR, 4,
            f"Subscriber SBR01 '{sbrs[0].el(1)}' indicates a non-primary payer, so an "
            "other-payer loop (2320 SBR) naming the primary payer is required.",
            "SBR",
        ))

    return issues


# --------------------------------------------------------------------------- #
#  834 — coverage begin date
# --------------------------------------------------------------------------- #
def _check_834(doc: EdiDocument) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    open_hd: Optional[Dict[str, Any]] = None

    def finalize(hd: Optional[Dict[str, Any]]) -> None:
        if hd and not hd["has_348"]:
            issues.append(make(
                ERROR, 4,
                "Health coverage (HD) is present but its benefit begin date "
                "(DTP*348) is missing.",
                "HD", hd["pos"],
            ))

    for pos, s in enumerate(doc.segments, start=1):
        sid = s.seg_id
        if sid == "HD":
            finalize(open_hd)
            open_hd = {"pos": pos, "has_348": False}
        elif sid in ("INS", "SE") and open_hd is not None:
            # A new member or the trailer closes the current coverage's scope.
            finalize(open_hd)
            open_hd = None
        elif sid == "DTP" and open_hd is not None and (s.el(1) or "").strip() == "348":
            open_hd["has_348"] = True

    finalize(open_hd)
    return issues
