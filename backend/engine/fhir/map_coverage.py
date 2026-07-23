"""834  →  FHIR R4 ``Coverage`` (+ referenced resources).

Consumes the v1 normalized dict from ``engine.mappers.map_834``. Each member
(INS loop) becomes a ``Patient``; each of that member's health-coverage lines
(HD loop) becomes a ``Coverage`` resource pointing at the member and the payer
``Organization``.

Base FHIR R4 structure only. See docx/v2/5-fhir-mapping-reference.md §5.5.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.fhir import common as c

# X12 834 relationship / subscriber-indicator → FHIR subscriber-relationship.
_RELATIONSHIP = {
    "18": "self", "01": "spouse", "19": "child", "20": "other",
    "53": "common", "G8": "other",
}


def to_fhir(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    payer_src = data.get("payer") or {}
    resources: List[Dict[str, Any]] = []
    for m_idx, member in enumerate(data.get("members") or [], start=1):
        resources.extend(_member_resources(member, m_idx, payer_src))
    return resources


def _member_resources(
    member: Dict[str, Any], n: int, payer_src: Dict[str, Any]
) -> List[Dict[str, Any]]:
    person = member.get("member") or {}
    ids = {"patient": f"patient-{n}", "payer": f"org-payer-{n}"}

    resources: List[Dict[str, Any]] = [
        _patient(person, ids["patient"]),
        _organization(payer_src, ids["payer"]),
    ]

    coverages = member.get("coverages") or []
    if not coverages:
        # No HD line — still emit a Coverage so the member's enrollment is present.
        resources.append(_coverage(member, {}, n, 1, ids))
    for j, cov in enumerate(coverages, start=1):
        resources.append(_coverage(member, cov, n, j, ids))

    return [c.prune(r) for r in resources]


def _patient(person: Dict[str, Any], pid: str) -> Dict[str, Any]:
    name = c.human_name(person.get("last_name_or_org"), person.get("first_name"))
    member_id = c.identifier(person.get("id"))
    return {
        "resourceType": "Patient",
        "id": pid,
        "identifier": [member_id] if member_id else None,
        "name": [name] if name else None,
        "gender": c.GENDER_CODE.get(str(person.get("gender", "")).strip()),
        "birthDate": c._clean(person.get("date_of_birth")),
        "address": ([c.address(person)] if c.address(person) else None),
    }


def _organization(payer_src: Dict[str, Any], oid: str) -> Dict[str, Any]:
    ident = c.identifier(payer_src.get("id"))
    return {
        "resourceType": "Organization",
        "id": oid,
        "identifier": [ident] if ident else None,
        "name": c._clean(payer_src.get("name")) or "Unknown Payer",
    }


def _coverage(
    member: Dict[str, Any],
    cov: Dict[str, Any],
    n: int,
    j: int,
    ids: Dict[str, str],
) -> Dict[str, Any]:
    references = member.get("references") or []

    return {
        "resourceType": "Coverage",
        "id": f"coverage-{n}-{j}",
        "status": _status(member),
        "type": c.codeable_concept(
            cov.get("insurance_line_code"),
            c.SYSTEM["insurance_line"],
            cov.get("insurance_line"),
        ),
        "subscriberId": _ref_value(references, "0F"),
        "beneficiary": c.reference("Patient", ids["patient"]),
        "relationship": _relationship(member),
        "period": _period(cov.get("dates") or []),
        "payor": [c.reference("Organization", ids["payer"])],
        "class": _classes(references, cov),
    }


def _status(member: Dict[str, Any]) -> str:
    # A member terminated (maintenance 024) reads as cancelled; else active.
    if str(member.get("maintenance_type_code", "")).strip() == "024":
        return "cancelled"
    return "active"


def _relationship(member: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if str(member.get("subscriber_indicator", "")).strip().upper() == "Y":
        code = "self"
    else:
        code = _RELATIONSHIP.get(str(member.get("relationship_code", "")).strip(), "other")
    return c.codeable_concept(code, c.SYSTEM["subscriber_relationship"])


def _period(dates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    period: Dict[str, Any] = {}
    for d in dates:
        qual = str(d.get("qualifier", "")).strip()
        value = c._clean(d.get("value"))
        if not value:
            continue
        # A range value "start/end" fills both ends.
        if "/" in value:
            start, end = value.split("/", 1)
            period.setdefault("start", start.split(" ")[0])
            period.setdefault("end", end.split(" ")[0])
            continue
        single = value.split(" ")[0]
        if qual in ("348", "356"):      # benefit begin / eligibility begin
            period["start"] = single
        elif qual in ("349", "357"):    # benefit end / eligibility end
            period["end"] = single
        else:
            period.setdefault("start", single)
    return period or None


def _classes(references: List[Dict[str, Any]], cov: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    classes: List[Dict[str, Any]] = []
    group = _ref_value(references, "1L")
    if group:
        classes.append({
            "type": c.codeable_concept("group", c.SYSTEM["coverage_class"]),
            "value": group,
        })
    plan = c._clean(cov.get("plan_coverage_description"))
    if plan:
        classes.append({
            "type": c.codeable_concept("plan", c.SYSTEM["coverage_class"]),
            "value": plan,
        })
    return classes or None


def _ref_value(references: List[Dict[str, Any]], qualifier: str) -> Optional[str]:
    for ref in references:
        if str(ref.get("qualifier", "")).strip() == qualifier:
            return c._clean(ref.get("value"))
    return None
