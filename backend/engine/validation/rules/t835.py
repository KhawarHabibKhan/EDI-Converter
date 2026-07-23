"""SNIP Level 2 (Requirement) rules — 835 (Remittance, 005010X221A1).

Required financial header, trace, payer/payee, and claim-payment loops.
docx/v3/5-snip-rule-reference.md §5.2.
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine.validation.rules import common as C
from engine.x12_reader import EdiDocument


def check(doc: EdiDocument, txn_type: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    # Financial information (BPR) + reassociation trace (TRN).
    issues += C.require_segment(doc, "BPR", "financial information")
    issues += C.require_elements(doc, "BPR", [1, 2], "financial information")
    issues += C.check_decimal_element(doc, "BPR", 2, "total actual provider payment")
    issues += C.require_segment(doc, "TRN", "reassociation trace")
    issues += C.require_elements(doc, "TRN", [2], "trace number")
    # Payer (1000A N1*PR) + payee (1000B N1*PE).
    issues += C.require_qualified(doc, "N1", 1, "PR", "Payer identification", [2])
    issues += C.require_qualified(doc, "N1", 1, "PE", "Payee identification", [2])
    # Claim payment (2100 CLP): id, status, charge, paid.
    issues += C.require_segment(doc, "CLP", "claim payment information")
    issues += C.require_elements(doc, "CLP", [1, 2, 3, 4], "claim payment")
    issues += C.check_decimal_element(doc, "CLP", 3, "claim charge amount")
    issues += C.check_decimal_element(doc, "CLP", 4, "claim payment amount")
    # Service payment (2110 SVC) — situational; if present, require code + charge.
    issues += C.require_elements(doc, "SVC", [1, 2], "service payment", first_only=False)
    issues += C.check_decimal_element(doc, "SVC", 2, "line charge amount")
    return issues
