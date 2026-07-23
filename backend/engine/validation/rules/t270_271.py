"""SNIP Level 2 (Requirement) rules — 270 / 271 (Eligibility, 005010X279A1).

Shared requirement rules for the eligibility inquiry (270) and response (271);
270 requires an EQ (inquiry) loop, 271 requires an EB (benefit) loop.
docx/v3/5-snip-rule-reference.md §5.2.
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine.validation.rules import common as C
from engine.x12_reader import EdiDocument


def check(doc: EdiDocument, txn_type: str) -> List[Dict[str, Any]]:
    is_inquiry = txn_type == "270"
    issues: List[Dict[str, Any]] = []
    issues += C.require_segment(doc, "BHT", "beginning of hierarchical transaction")
    issues += C.require_elements(doc, "BHT", [1, 2], "BHT")
    # HL hierarchy: information source (20), receiver (21), subscriber (22).
    issues += C.require_any(doc, "HL", 3, ["20"], "Information source hierarchical level")
    issues += C.require_any(doc, "HL", 3, ["21"], "Information receiver hierarchical level")
    issues += C.require_any(doc, "HL", 3, ["22"], "Subscriber hierarchical level")
    # Payer / information source (2100A NM1*PR) + subscriber (2100C NM1*IL).
    issues += C.require_qualified(doc, "NM1", 1, "PR", "Payer / information source", [3])
    issues += C.require_qualified(doc, "NM1", 1, "IL", "Subscriber", [3])
    # The direction-specific detail loop.
    if is_inquiry:
        issues += C.require_segment(doc, "EQ", "eligibility/benefit inquiry")
    else:
        issues += C.require_segment(doc, "EB", "eligibility/benefit information")
    return issues
