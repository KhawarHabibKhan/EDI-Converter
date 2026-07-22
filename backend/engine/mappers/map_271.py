"""270/271 (Eligibility / Benefit Inquiry & Response) mapper.

Walks the X12 HL hierarchy: information source (20) → information receiver (21)
→ subscriber (22) → dependent (23). A 271 response carries EB (benefit) segments;
a 270 request carries EQ (inquiry) segments — both are captured.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.mappers import _common as C
from engine.x12_reader import Delimiters, EdiDocument, Segment

ELIGIBILITY_CODE = {
    "1": "Active Coverage",
    "2": "Active - Full Risk Capitation",
    "3": "Active - Services Capitated",
    "6": "Inactive",
    "7": "Inactive - Pending Eligibility Update",
    "8": "Inactive - Pending Investigation",
    "A": "Co-Insurance",
    "B": "Co-Payment",
    "C": "Deductible",
    "D": "Benefit Description",
    "F": "Limitations",
    "G": "Out of Pocket (Stop Loss)",
    "I": "Non-Covered",
    "L": "Primary Care Provider",
    "R": "Other or Additional Payer",
    "U": "Contact Following Entity for Eligibility",
}


def _parse_eb(seg: Segment, delim: Delimiters) -> Dict[str, Any]:
    service_types = seg.el(3).split(delim.repetition) if seg.el(3) else []
    return {
        "eligibility_code": seg.el(1),
        "eligibility": ELIGIBILITY_CODE.get(seg.el(1), seg.el(1)),
        "coverage_level_code": seg.el(2),
        "service_type_codes": service_types,
        "insurance_type_code": seg.el(4),
        "plan_description": seg.el(5),
        "time_period_qualifier": seg.el(6),
        "benefit_amount": seg.el(7),
        "benefit_percent": seg.el(8),
        "in_plan_network_indicator": seg.el(12),
    }


def _new_node() -> Dict[str, Any]:
    return {"info": {}, "trace_numbers": [], "dates": [], "eligibility": [], "dependents": []}


def to_json(doc: EdiDocument) -> Dict[str, Any]:
    delim = doc.delim
    st = doc.first("ST")
    is_inquiry = st is not None and st.el(1) == "270"
    header: Dict[str, Any] = {}
    sources: List[Dict[str, Any]] = []

    cur_source: Optional[Dict[str, Any]] = None
    cur_receiver: Optional[Dict[str, Any]] = None
    cur_node: Optional[Dict[str, Any]] = None   # subscriber or dependent
    cur_info: Optional[Dict[str, Any]] = None   # node["info"]
    in_ls = False

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
            level = seg.el(3)
            if level == "20":
                cur_source = {"payer": {}, "information_receivers": []}
                sources.append(cur_source)
                cur_receiver = cur_node = cur_info = None
            elif level == "21":
                cur_receiver = {"provider": {}, "subscribers": []}
                if cur_source is not None:
                    cur_source["information_receivers"].append(cur_receiver)
                cur_node = cur_info = None
            elif level == "22":
                cur_node = _new_node()
                if cur_receiver is not None:
                    cur_receiver["subscribers"].append(cur_node)
                cur_info = cur_node["info"]
            elif level == "23":
                dep = _new_node()
                dep.pop("dependents", None)
                if cur_node is not None:
                    cur_node["dependents"].append(dep)
                cur_node = dep
                cur_info = dep["info"]

        elif sid == "NM1":
            role = seg.el(1)
            name = C.parse_name(seg)
            if role == "PR" and cur_source is not None and not cur_receiver:
                cur_source["payer"] = name
            elif role in ("1P", "2B", "FA", "36") and cur_receiver is not None and cur_node is None:
                cur_receiver["provider"] = name
            elif in_ls and cur_node is not None:
                cur_node.setdefault("related_providers", []).append(name)
            elif cur_info is not None:
                cur_info.update(name)
            elif cur_source is not None and not cur_receiver:
                cur_source["payer"] = name

        elif sid == "TRN" and cur_node is not None:
            cur_node["trace_numbers"].append(
                {"trace_number": seg.el(2), "originating_company": seg.el(3)}
            )
        elif sid == "REF" and cur_info is not None:
            cur_info.setdefault("references", []).append(
                {"qualifier": seg.el(1), "value": seg.el(2), "description": seg.el(3)}
            )
        elif sid == "N3" and cur_info is not None:
            cur_info["address_1"] = seg.el(1)
            if seg.el(2):
                cur_info["address_2"] = seg.el(2)
        elif sid == "N4" and cur_info is not None:
            cur_info["city"] = seg.el(1)
            cur_info["state"] = seg.el(2)
            cur_info["postal_code"] = seg.el(3)
        elif sid == "DMG" and cur_info is not None:
            cur_info["date_of_birth"] = C.fmt_date(seg.el(2))
            cur_info["gender"] = C.GENDER.get(seg.el(3), seg.el(3))
        elif sid == "DTP" and cur_node is not None:
            cur_node["dates"].append(
                {"qualifier": seg.el(1), "value": C.fmt_dtp(seg.el(3))}
            )
        elif sid == "EB" and cur_node is not None:
            cur_node["eligibility"].append(_parse_eb(seg, delim))
        elif sid == "EQ" and cur_node is not None:
            cur_node.setdefault("inquiries", []).append({
                "service_type_codes": seg.el(1).split(delim.repetition) if seg.el(1) else [],
                "coverage_level_code": seg.el(3),
            })
        elif sid == "LS":
            in_ls = True
        elif sid == "LE":
            in_ls = False

    return {
        "form": "270 Eligibility/Benefit Inquiry" if is_inquiry
        else "271 Eligibility/Benefit Response",
        "source_transaction": "ANSI X12 270" if is_inquiry else "ANSI X12 271",
        "header": header,
        "information_sources": sources,
    }
