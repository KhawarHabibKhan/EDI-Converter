"""SNIP Level 2 (Requirement) rules — 276 / 277 (Claim status, 005010X212).

Shared requirement rules for the claim-status request (276) and response (277);
a 277 response additionally requires an STC (claim status) segment.
docx/v3/5-snip-rule-reference.md §5.2.
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine.validation.rules import common as C
from engine.x12_reader import EdiDocument


def check(doc: EdiDocument, txn_type: str) -> List[Dict[str, Any]]:
    is_request = txn_type == "276"
    issues: List[Dict[str, Any]] = []
    issues += C.require_segment(doc, "BHT", "beginning of hierarchical transaction")
    issues += C.require_elements(doc, "BHT", [1, 2], "BHT")
    # HL hierarchy: information source (20) + receiver (21).
    issues += C.require_any(doc, "HL", 3, ["20"], "Information source hierarchical level")
    issues += C.require_any(doc, "HL", 3, ["21"], "Information receiver hierarchical level")
    # Payer (NM1*PR).
    issues += C.require_qualified(doc, "NM1", 1, "PR", "Payer", [3])
    # Claim status trace (TRN).
    issues += C.require_segment(doc, "TRN", "claim status trace")
    issues += C.require_elements(doc, "TRN", [2], "trace number", first_only=False)
    # A 277 response must carry claim-status (STC) information.
    if not is_request:
        issues += C.require_segment(doc, "STC", "claim status information")
    return issues
