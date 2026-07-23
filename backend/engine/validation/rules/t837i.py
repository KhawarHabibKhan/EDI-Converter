"""SNIP Level 2 (Requirement) rules — 837I (Institutional claim, 005010X223A2).

Reuses the shared 837 requirement rules and adds the institutional service line
(2400 SV2 with a revenue code). docx/v3/5-snip-rule-reference.md §5.2.
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine.validation.rules import common as C
from engine.validation.rules.t837p import _shared_837
from engine.x12_reader import EdiDocument


def check(doc: EdiDocument, txn_type: str) -> List[Dict[str, Any]]:
    issues = _shared_837(doc)
    # Institutional service line (2400 SV2): SV201 revenue code, SV203 charge.
    issues += C.require_segment(doc, "SV2", "institutional service line")
    issues += C.require_elements(doc, "SV2", [1, 3], "institutional service line", first_only=False)
    issues += C.check_decimal_element(doc, "SV2", 3, "line charge")
    return issues
