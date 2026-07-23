"""SNIP Level 2 (Requirement) rules — 837P (Professional claim, 005010X222A1).

The proof-of-pattern rule set: required loops/segments/elements and basic data
types that a professional claim must carry. Rules are representative of the TR3
implementation guide (docx/v3/5-snip-rule-reference.md §5.2), not an exhaustive
reproduction. ``_shared_837`` is reused by the 837I module.
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine.validation.issue import ERROR, make
from engine.validation.rules import common as C
from engine.x12_reader import EdiDocument

# Principal-diagnosis qualifiers (ICD-10 / ICD-9).
_PRINCIPAL_DX = {"ABK", "BK"}


def check(doc: EdiDocument, txn_type: str) -> List[Dict[str, Any]]:
    issues = _shared_837(doc)
    # Professional service line (2400 SV1).
    issues += C.require_segment(doc, "SV1", "professional service line")
    issues += C.require_elements(doc, "SV1", [1, 2], "professional service line", first_only=False)
    issues += C.check_decimal_element(doc, "SV1", 2, "line charge")
    return issues


def _shared_837(doc: EdiDocument) -> List[Dict[str, Any]]:
    """Requirement rules common to 837P and 837I."""
    issues: List[Dict[str, Any]] = []
    # Header.
    issues += C.require_elements(doc, "ST", [3], "implementation guide (ST03)")
    issues += C.require_segment(doc, "BHT", "beginning of hierarchical transaction")
    issues += C.require_elements(doc, "BHT", [1, 2, 6], "BHT")
    # Submitter / receiver (1000A / 1000B).
    issues += C.require_qualified(doc, "NM1", 1, "41", "Submitter", [3])
    issues += C.require_qualified(doc, "NM1", 1, "40", "Receiver", [3])
    # Billing provider (2000A / 2010AA) — NPI required (NM108=XX, NM109).
    issues += C.require_any(doc, "HL", 3, ["20"], "Billing provider hierarchical level")
    issues += C.require_qualified(doc, "NM1", 1, "85", "Billing provider", [3, 8, 9])
    # Subscriber (2000B / 2010BA) + payer (2010BB).
    issues += C.require_any(doc, "HL", 3, ["22", "23"], "Subscriber/patient hierarchical level")
    issues += C.require_segment(doc, "SBR", "subscriber information")
    issues += C.require_qualified(doc, "NM1", 1, "IL", "Subscriber", [3, 9])
    issues += C.require_qualified(doc, "NM1", 1, "PR", "Payer", [3, 8, 9])
    # Claim (2300).
    issues += C.require_segment(doc, "CLM", "claim information")
    issues += C.require_elements(doc, "CLM", [1, 2], "claim")
    issues += C.check_decimal_element(doc, "CLM", 2, "total claim charge")
    issues += _require_principal_diagnosis(doc)
    # Service date (2400 DTP*472) + date format.
    issues += C.require_qualified(doc, "DTP", 1, "472", "service date")
    issues += C.check_d8_dates(doc, "DTP", 2, 3, "date")
    return issues


def _require_principal_diagnosis(doc: EdiDocument) -> List[Dict[str, Any]]:
    """At least one HI segment carrying a principal diagnosis (ABK/BK)."""
    his = C.occurrences(doc, "HI")
    if not his:
        return [make(ERROR, 2, "Missing required HI segment (diagnosis) for the claim.", "HI")]
    for s in his:
        for i in range(1, len(s.elements) + 1):
            comp = s.el(i)
            if comp and comp.split(doc.delim.component)[0] in _PRINCIPAL_DX:
                return []
    pos = C.position_of(doc, his[0])
    return [make(ERROR, 2, "HI present but no principal diagnosis (ABK/BK) found.", "HI", pos)]
