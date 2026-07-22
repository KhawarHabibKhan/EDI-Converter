"""Shared helpers for the transaction mappers (name/date parsing, code maps)."""

from __future__ import annotations

from typing import Any, Dict

from engine.x12_reader import Segment

GENDER = {"M": "Male", "F": "Female", "U": "Unknown"}

ENTITY_IDENTIFIER = {
    "PR": "Payer",
    "PE": "Payee",
    "QC": "Patient",
    "IL": "Insured / Subscriber",
    "1P": "Provider",
    "P3": "Primary Care Provider",
    "1P ": "Provider",
    "2B": "Third-Party Administrator",
    "36": "Employer",
    "GP": "Gateway Provider",
    "77": "Service Facility",
    "85": "Billing Provider",
    "82": "Rendering Provider",
    "P5": "Plan Sponsor",
    "IN": "Insurer",
    "41": "Submitter",
    "40": "Receiver",
    "03": "Dependent",
}


def parse_name(seg: Segment) -> Dict[str, Any]:
    """Parse an NM1 name segment into a dict."""
    entity_code = seg.el(1)
    entity_type = seg.el(2)  # 1 = person, 2 = non-person
    return {
        "entity_role_code": entity_code,
        "entity_role": ENTITY_IDENTIFIER.get(entity_code, entity_code),
        "entity_type": "Organization" if entity_type == "2" else "Person",
        "last_name_or_org": seg.el(3),
        "first_name": seg.el(4),
        "middle_name": seg.el(5),
        "suffix": seg.el(7),
        "id_qualifier": seg.el(8),
        "id": seg.el(9),
    }


def fmt_date(raw: str) -> str:
    """CCYYMMDD -> CCYY-MM-DD; pass through anything else."""
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def fmt_dtp(raw: str) -> str:
    """Format a DTP/DTM date value: D8 single, RD8 range, DT date-time."""
    if "-" in raw and len(raw) == 17:
        start, end = raw.split("-")
        return f"{fmt_date(start)}/{fmt_date(end)}"
    if len(raw) == 12 and raw.isdigit():
        return f"{fmt_date(raw[:8])} {raw[8:10]}:{raw[10:12]}"
    return fmt_date(raw)


def add_address(entity: Dict[str, Any], n3: Segment | None, n4: Segment | None) -> None:
    if n3 is not None:
        entity["address_1"] = n3.el(1)
        if n3.el(2):
            entity["address_2"] = n3.el(2)
    if n4 is not None:
        entity["city"] = n4.el(1)
        entity["state"] = n4.el(2)
        entity["postal_code"] = n4.el(3)
