"""270 / 271  →  FHIR R4 ``CoverageEligibilityRequest`` / ``CoverageEligibilityResponse``.

Consumes the v1 normalized dict from ``engine.mappers.map_271`` (which handles
both 270 and 271). The X12 HL hierarchy (source → receiver → subscriber →
dependent) is flattened: every subscriber/dependent node becomes a ``Patient``
plus the eligibility resource for that node.

* 270 (inquiry)  → ``CoverageEligibilityRequest`` with `item[]` from EQ loops.
* 271 (response) → ``CoverageEligibilityResponse`` with `insurance[].item[]` from
  EB loops. Because R4 makes ``request`` and ``insurance.coverage`` required
  references, we also emit a derived ``CoverageEligibilityRequest`` stub and a
  ``Coverage`` stub so every reference resolves inside the Bundle.

Base FHIR R4 structure only. See docx/v2/5-fhir-mapping-reference.md §5.6.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.fhir import common as c


def to_fhir(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    is_request = "270" in str(data.get("source_transaction", ""))
    created = (((data.get("header") or {}).get("transaction")) or {}).get("date")

    resources: List[Dict[str, Any]] = []
    counter = 0
    for source in data.get("information_sources") or []:
        payer_src = source.get("payer") or {}
        for receiver in source.get("information_receivers") or []:
            provider_src = receiver.get("provider") or {}
            for subscriber in receiver.get("subscribers") or []:
                nodes = [subscriber] + list(subscriber.get("dependents") or [])
                for node in nodes:
                    counter += 1
                    resources.extend(
                        _node_resources(node, counter, payer_src, provider_src, created, is_request)
                    )
    return resources


def _node_resources(
    node: Dict[str, Any],
    k: int,
    payer_src: Dict[str, Any],
    provider_src: Dict[str, Any],
    created: Any,
    is_request: bool,
) -> List[Dict[str, Any]]:
    info = node.get("info") or {}
    ids = {
        "patient": f"patient-{k}",
        "payer": f"org-payer-{k}",
        "provider": f"org-provider-{k}",
        "coverage": f"coverage-{k}",
        "req": f"elig-request-{k}",
        "resp": f"elig-response-{k}",
    }

    resources: List[Dict[str, Any]] = [
        _patient(info, ids["patient"]),
        _organization(payer_src, ids["payer"], "Unknown Payer"),
    ]

    provider_res = _organization(provider_src, ids["provider"], "") if provider_src else None
    if provider_res is not None:
        resources.append(provider_res)

    if is_request:
        resources.append(_request(node, ids, created, provider_res is not None))
    else:
        # 271: Coverage + derived Request stub + Response.
        resources.append(_coverage_stub(ids))
        resources.append(_request(node, ids, created, provider_res is not None))
        resources.append(_response(node, ids, created))

    return [c.prune(r) for r in resources]


# --------------------------------------------------------------------------- #
#  Referenced resources
# --------------------------------------------------------------------------- #
def _patient(info: Dict[str, Any], pid: str) -> Dict[str, Any]:
    name = c.human_name(info.get("last_name_or_org"), info.get("first_name"))
    member_id = c.identifier(info.get("id"))
    return {
        "resourceType": "Patient",
        "id": pid,
        "identifier": [member_id] if member_id else None,
        "name": [name] if name else None,
        "gender": c.GENDER_CODE.get(str(info.get("gender", "")).strip()),
        "birthDate": c._clean(info.get("date_of_birth")),
        "address": ([c.address(info)] if c.address(info) else None),
    }


def _organization(src: Dict[str, Any], oid: str, fallback: str) -> Dict[str, Any]:
    ident = c.identifier(src.get("id"))
    name = c._clean(src.get("last_name_or_org")) or c._clean(src.get("name")) or fallback
    return {
        "resourceType": "Organization",
        "id": oid,
        "identifier": [ident] if ident else None,
        "name": name or "Unknown Organization",
    }


def _coverage_stub(ids: Dict[str, str]) -> Dict[str, Any]:
    return {
        "resourceType": "Coverage",
        "id": ids["coverage"],
        "status": "active",
        "beneficiary": c.reference("Patient", ids["patient"]),
        "payor": [c.reference("Organization", ids["payer"])],
    }


# --------------------------------------------------------------------------- #
#  Eligibility resources
# --------------------------------------------------------------------------- #
def _request(node: Dict[str, Any], ids: Dict[str, str], created: Any, has_provider: bool) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for inq in node.get("inquiries") or []:
        for st in inq.get("service_type_codes") or []:
            cat = c.codeable_concept(st, c.SYSTEM["service_type"])
            if cat:
                items.append({"category": cat})
    return {
        "resourceType": "CoverageEligibilityRequest",
        "id": ids["req"],
        "status": "active",
        "purpose": ["benefits"],
        "patient": c.reference("Patient", ids["patient"]),
        "created": c._clean(created) or _fallback_date(node),
        "provider": c.reference("Organization", ids["provider"]) if has_provider else None,
        "insurer": c.reference("Organization", ids["payer"]),
        "item": items or None,
    }


def _response(node: Dict[str, Any], ids: Dict[str, str], created: Any) -> Dict[str, Any]:
    items = [_eb_item(eb) for eb in node.get("eligibility") or []]
    items = [i for i in items if i]
    return {
        "resourceType": "CoverageEligibilityResponse",
        "id": ids["resp"],
        "status": "active",
        "purpose": ["benefits"],
        "patient": c.reference("Patient", ids["patient"]),
        "created": c._clean(created) or _fallback_date(node),
        "request": c.reference("CoverageEligibilityRequest", ids["req"]),
        "outcome": "complete",
        "insurer": c.reference("Organization", ids["payer"]),
        "insurance": [{
            "coverage": c.reference("Coverage", ids["coverage"]),
            "inforce": True,
            "item": items or None,
        }],
    }


def _eb_item(eb: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    service_types = eb.get("service_type_codes") or []
    category = c.codeable_concept(service_types[0], c.SYSTEM["service_type"]) if service_types else None

    network = None
    net_ind = str(eb.get("in_plan_network_indicator", "")).strip().upper()
    if net_ind == "Y":
        network = c.codeable_concept("in", c.SYSTEM["benefit_network"])
    elif net_ind == "N":
        network = c.codeable_concept("out", c.SYSTEM["benefit_network"])

    benefit = None
    amount = c.money(eb.get("benefit_amount"))
    elig = c.codeable_concept(
        eb.get("eligibility_code"), c.SYSTEM["eligibility_info"], eb.get("eligibility")
    )
    if amount or elig:
        benefit = [{
            "type": elig or c.codeable_concept("benefit", c.SYSTEM["eligibility_info"]),
            "allowedMoney": amount,
        }]

    if category is None:
        # R4 invariant ces-1: an item SHALL contain a category or a billcode, but
        # not both. An EB segment with no EB03 service type is a plan-level
        # benefit, so give it a text-only category rather than emitting an item
        # that satisfies neither side of the constraint.
        category = {"text": "Plan-level benefit"}

    item: Dict[str, Any] = {
        "category": category,
        "network": network,
        "name": c._clean(eb.get("plan_description")),
        "benefit": benefit,
    }
    pruned = c.prune(item)
    return pruned or None


def _fallback_date(node: Dict[str, Any]) -> Optional[str]:
    for d in node.get("dates") or []:
        value = c._clean(d.get("value"))
        if value:
            return value.split("/")[0].split(" ")[0]
    return None
