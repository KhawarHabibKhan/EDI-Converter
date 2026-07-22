"""834 (Benefit Enrollment & Maintenance) mapper.

Maps the sponsor/payer, and each member's demographics, references, and health
coverage (HD) with begin/end dates.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.mappers import _common as C
from engine.x12_reader import EdiDocument

MAINTENANCE_TYPE = {
    "001": "Change", "021": "Addition", "024": "Cancel/Terminate",
    "025": "Reinstatement", "030": "Audit/Compare",
}
BENEFIT_STATUS = {"A": "Active", "C": "COBRA", "S": "Surviving Insured", "T": "Tax Equity"}
INSURANCE_LINE = {
    "HLT": "Health", "DEN": "Dental", "VIS": "Vision", "HMO": "HMO",
    "PPO": "PPO", "PDG": "Pharmacy", "LTD": "Long-Term Disability",
    "AK": "Prescription Drug", "DCP": "Dental Capitation",
}


def to_json(doc: EdiDocument) -> Dict[str, Any]:
    header: Dict[str, Any] = {}
    sponsor: Dict[str, Any] = {}
    payer: Dict[str, Any] = {}
    members: List[Dict[str, Any]] = []

    current_member: Optional[Dict[str, Any]] = None
    current_coverage: Optional[Dict[str, Any]] = None
    current_n1: Optional[Dict[str, Any]] = None
    in_member = False

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
        elif sid == "BGN":
            header["begin"] = {
                "purpose_code": seg.el(1),
                "reference_id": seg.el(2),
                "date": C.fmt_date(seg.el(3)),
                "time": seg.el(4),
            }

        # --- Sponsor / payer (N1) — only before member (INS) loops ---- #
        elif sid == "N1" and not in_member:
            entity = {
                "entity_role_code": seg.el(1),
                "entity_role": C.ENTITY_IDENTIFIER.get(seg.el(1), seg.el(1)),
                "name": seg.el(2),
                "id_qualifier": seg.el(3),
                "id": seg.el(4),
            }
            current_n1 = entity
            if seg.el(1) == "P5":
                sponsor.update(entity)
            elif seg.el(1) == "IN":
                payer.update(entity)

        # --- Member loop (INS) ---------------------------------------- #
        elif sid == "INS":
            in_member = True
            current_member = {
                "subscriber_indicator": seg.el(1),  # Y = subscriber, N = dependent
                "relationship_code": seg.el(2),
                "maintenance_type_code": seg.el(3),
                "maintenance_type": MAINTENANCE_TYPE.get(seg.el(3), seg.el(3)),
                "benefit_status_code": seg.el(5),
                "benefit_status": BENEFIT_STATUS.get(seg.el(5), seg.el(5)),
                "references": [],
                "coverages": [],
            }
            members.append(current_member)
            current_coverage = None
            current_n1 = None
        elif sid == "REF" and current_member is not None:
            current_member["references"].append(
                {"qualifier": seg.el(1), "value": seg.el(2)}
            )
        elif sid == "NM1" and current_member is not None and seg.el(1) in ("IL", "74"):
            current_member["member"] = C.parse_name(seg)
        elif sid == "N3" and current_member is not None and "member" in current_member:
            current_member["member"]["address_1"] = seg.el(1)
        elif sid == "N4" and current_member is not None and "member" in current_member:
            current_member["member"]["city"] = seg.el(1)
            current_member["member"]["state"] = seg.el(2)
            current_member["member"]["postal_code"] = seg.el(3)
        elif sid == "DMG" and current_member is not None and "member" in current_member:
            current_member["member"]["date_of_birth"] = C.fmt_date(seg.el(2))
            current_member["member"]["gender"] = C.GENDER.get(seg.el(3), seg.el(3))

        # --- Health coverage (HD) ------------------------------------- #
        elif sid == "HD" and current_member is not None:
            current_coverage = {
                "maintenance_type_code": seg.el(1),
                "maintenance_type": MAINTENANCE_TYPE.get(seg.el(1), seg.el(1)),
                "insurance_line_code": seg.el(3),
                "insurance_line": INSURANCE_LINE.get(seg.el(3), seg.el(3)),
                "plan_coverage_description": seg.el(4),
                "dates": [],
            }
            current_member["coverages"].append(current_coverage)
        elif sid == "DTP":
            entry = {"qualifier": seg.el(1), "value": C.fmt_dtp(seg.el(3))}
            if current_coverage is not None:
                current_coverage["dates"].append(entry)
            elif current_member is not None:
                current_member.setdefault("dates", []).append(entry)

    _ = current_n1  # N1 sub-segments not tracked further in v1
    return {
        "form": "834 Benefit Enrollment",
        "source_transaction": "ANSI X12 834",
        "header": header,
        "sponsor": sponsor,
        "payer": payer,
        "members": members,
        "member_count": len(members),
    }
