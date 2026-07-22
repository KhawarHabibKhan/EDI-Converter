"""276/277 (Health Care Claim Status Request & Response) mapper.

Walks the HL hierarchy: information source (20) → information receiver (21) →
provider (19) → subscriber (22) → dependent (23), collecting per-claim trace
(TRN) and, for a 277 response, claim-status (STC) information.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.mappers import _common as C
from engine.x12_reader import Delimiters, EdiDocument, Segment


def _parse_stc(seg: Segment, delim: Delimiters) -> Dict[str, Any]:
    """STC01 is a composite: category code : status code : entity code."""
    return {
        "category_code": seg.comp(1, 1, delim),
        "status_code": seg.comp(1, 2, delim),
        "entity_code": seg.comp(1, 3, delim),
        "status_date": C.fmt_date(seg.el(2)),
        "action_code": seg.el(3),
        "total_charge": seg.el(4),
        "paid_amount": seg.el(5),
    }


def to_json(doc: EdiDocument) -> Dict[str, Any]:
    delim = doc.delim
    st = doc.first("ST")
    is_request = st is not None and st.el(1) == "276"
    header: Dict[str, Any] = {}
    entities: List[Dict[str, Any]] = []   # flattened NM1 levels above the claim
    claims: List[Dict[str, Any]] = []

    current_claim: Optional[Dict[str, Any]] = None
    current_service: Optional[Dict[str, Any]] = None

    for seg in doc.segments:
        sid = seg.seg_id

        if sid == "ISA":
            header["interchange"] = {
                "sender_id": seg.el(6).strip(),
                "receiver_id": seg.el(8).strip(),
                "control_number": seg.el(13),
                "usage": "Production" if seg.el(15) == "P" else "Test",
            }
        elif sid == "GS":
            header["functional_group"] = {"version": seg.el(8)}
        elif sid == "BHT":
            header["transaction"] = {
                "structure": seg.el(1),
                "purpose_code": seg.el(2),
                "reference_id": seg.el(3),
                "date": C.fmt_date(seg.el(4)),
            }

        elif sid == "HL":
            # A new hierarchy level ends any in-progress claim.
            current_claim = None
            current_service = None

        elif sid == "NM1" and current_claim is None:
            entities.append(C.parse_name(seg))

        # --- Claim status loop (2200) --------------------------------- #
        elif sid == "TRN":
            current_claim = {
                "trace_number": seg.el(2),
                "statuses": [],
                "references": [],
                "service_lines": [],
            }
            claims.append(current_claim)
            current_service = None
        elif sid == "STC":
            status = _parse_stc(seg, delim)
            if current_service is not None:
                current_service.setdefault("statuses", []).append(status)
            elif current_claim is not None:
                current_claim["statuses"].append(status)
        elif sid == "REF" and current_claim is not None and current_service is None:
            current_claim["references"].append(
                {"qualifier": seg.el(1), "value": seg.el(2)}
            )
        elif sid == "SVC" and current_claim is not None:
            current_service = {
                "procedure_code": seg.comp(1, 2, delim),
                "charge_amount": seg.el(2),
                "paid_amount": seg.el(3),
                "statuses": [],
            }
            current_claim["service_lines"].append(current_service)
        elif sid == "DTP":
            entry = {"qualifier": seg.el(1), "value": C.fmt_dtp(seg.el(3))}
            if current_service is not None:
                current_service.setdefault("dates", []).append(entry)
            elif current_claim is not None:
                current_claim.setdefault("dates", []).append(entry)

    return {
        "form": "276 Claim Status Request" if is_request else "277 Claim Status Response",
        "source_transaction": "ANSI X12 276" if is_request else "ANSI X12 277",
        "header": header,
        "entities": entities,
        "claims": claims,
        "claim_count": len(claims),
    }
