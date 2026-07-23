"""SNIP Level 2 (Requirement) rules — 834 (Enrollment, 005010X220A1).

Required beginning segment, sponsor/payer, member, and health-coverage loops.
docx/v3/5-snip-rule-reference.md §5.2.
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine.validation.rules import common as C
from engine.x12_reader import EdiDocument


def check(doc: EdiDocument, txn_type: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    # Beginning segment (BGN).
    issues += C.require_segment(doc, "BGN", "beginning segment")
    issues += C.require_elements(doc, "BGN", [1, 2], "beginning segment")
    # Sponsor (1000A N1*P5) + payer/insurer (1000B N1*IN).
    issues += C.require_qualified(doc, "N1", 1, "P5", "Plan sponsor", [2])
    issues += C.require_qualified(doc, "N1", 1, "IN", "Insurer / payer", [2])
    # Member detail (2000 INS) + member name (2100A NM1*IL).
    issues += C.require_segment(doc, "INS", "member level detail")
    issues += C.require_elements(doc, "INS", [1, 3], "member level detail")
    issues += C.require_qualified(doc, "NM1", 1, "IL", "Member name", [3])
    # Health coverage (2300 HD): maintenance type + insurance line.
    issues += C.require_segment(doc, "HD", "health coverage")
    issues += C.require_elements(doc, "HD", [1, 3], "health coverage", first_only=False)
    return issues
