"""835  →  FHIR R4 ``ExplanationOfBenefit`` (+ referenced resources).

Consumes the v1 normalized dict produced by ``engine.mappers.map_835`` (never
raw X12) and returns a flat list of FHIR resource dicts: one
``ExplanationOfBenefit`` per remittance claim (CLP) plus the ``Patient``,
``Coverage`` and ``Organization`` (payer / payee) resources it references.

Money flows map to ``adjudication``/``total`` (submitted vs benefit), CAS
adjustments become ``adjudication`` entries tagged with the X12 group/reason
codes, the BPR/TRN payment becomes ``payment``, and PLB provider-level
adjustments are surfaced as ``processNote`` entries.

Base FHIR R4 structure only — CARIN Blue Button profile conformance is V2-D.
See docx/v2/5-fhir-mapping-reference.md §5.4.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.fhir import common as c


def to_fhir(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map an 835 normalized dict to a list of FHIR resources."""
    header = data.get("header") or {}
    payment = header.get("payment") or {}
    payer_src = data.get("payer") or {}
    payee_src = data.get("payee") or {}
    provider_adjustments = data.get("provider_adjustments") or []

    resources: List[Dict[str, Any]] = []
    for idx, claim in enumerate(data.get("claims") or [], start=1):
        resources.extend(
            _claim_resources(claim, idx, payment, payer_src, payee_src, provider_adjustments)
        )
    return resources


def _claim_resources(
    claim: Dict[str, Any],
    n: int,
    payment: Dict[str, Any],
    payer_src: Dict[str, Any],
    payee_src: Dict[str, Any],
    provider_adjustments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    patient_src = claim.get("patient") or claim.get("insured") or {}
    ids = {
        "patient": f"patient-{n}",
        "coverage": f"coverage-{n}",
        "payer": f"org-payer-{n}",
        "payee": f"org-payee-{n}",
        "eob": f"eob-{n}",
    }

    resources: List[Dict[str, Any]] = [
        _patient(patient_src, ids["patient"]),
        _organization(payer_src, ids["payer"], "Unknown Payer"),
        _organization(payee_src, ids["payee"], "Unknown Payee"),
        _coverage(patient_src, ids),
        _eob(claim, n, ids, payment, provider_adjustments),
    ]
    return [c.prune(r) for r in resources]


# --------------------------------------------------------------------------- #
#  Referenced resources
# --------------------------------------------------------------------------- #
def _patient(src: Dict[str, Any], pid: str) -> Dict[str, Any]:
    name = c.human_name(src.get("last_name_or_org"), src.get("first_name"))
    member_id = c.identifier(src.get("id"))
    return {
        "resourceType": "Patient",
        "id": pid,
        "identifier": [member_id] if member_id else None,
        "name": [name] if name else None,
    }


def _organization(src: Dict[str, Any], oid: str, fallback: str) -> Dict[str, Any]:
    # 835 N1 entities carry a flat "name"; NPI-qualified ids use system us-npi.
    system = c.SYSTEM["npi"] if str(src.get("id_qualifier", "")).strip() == "XX" else None
    ident = c.identifier(src.get("id"), system)
    return {
        "resourceType": "Organization",
        "id": oid,
        "identifier": [ident] if ident else None,
        "name": c._clean(src.get("name")) or fallback,
    }


def _coverage(patient_src: Dict[str, Any], ids: Dict[str, str]) -> Dict[str, Any]:
    return {
        "resourceType": "Coverage",
        "id": ids["coverage"],
        "status": "active",
        "subscriberId": c._clean(patient_src.get("id")),
        "beneficiary": c.reference("Patient", ids["patient"]),
        "payor": [c.reference("Organization", ids["payer"])],
    }


# --------------------------------------------------------------------------- #
#  ExplanationOfBenefit
# --------------------------------------------------------------------------- #
def _eob(
    claim: Dict[str, Any],
    n: int,
    ids: Dict[str, str],
    payment: Dict[str, Any],
    provider_adjustments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    services = claim.get("service_payments") or []
    # Heuristic: a revenue code on any line implies an institutional claim.
    institutional = any(c._clean(s.get("revenue_code")) for s in services)
    eob_type = "institutional" if institutional else "professional"

    res: Dict[str, Any] = {
        "resourceType": "ExplanationOfBenefit",
        "id": ids["eob"],
        "status": "active",
        "type": c.codeable_concept(eob_type, c.SYSTEM["claim_type"]),
        "use": "claim",
        "patient": c.reference("Patient", ids["patient"]),
        "created": c._clean(payment.get("payment_date")),
        "insurer": c.reference("Organization", ids["payer"]),
        "provider": c.reference("Organization", ids["payee"]),
        "outcome": "complete",
        "identifier": _identifiers(claim),
        "insurance": [{
            "focal": True,
            "coverage": c.reference("Coverage", ids["coverage"]),
        }],
        "item": _items(services) or None,
        "total": _totals(claim),
        "payment": _payment(payment),
        "processNote": _process_notes(claim, provider_adjustments) or None,
    }
    return res


def _identifiers(claim: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    idents = [
        c.identifier(claim.get("patient_control_number")),
        c.identifier(claim.get("payer_claim_control_number")),
    ]
    idents = [i for i in idents if i]
    return idents or None


def _items(services: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for i, svc in enumerate(services, start=1):
        adjudication = [
            _adjudication("submitted", c.SYSTEM["adjudication"], svc.get("charge_amount")),
            _adjudication("benefit", c.SYSTEM["adjudication"], svc.get("paid_amount")),
        ]
        adjudication += _cas_adjudications(svc.get("adjustments") or [])
        item: Dict[str, Any] = {
            "sequence": i,
            "productOrService": c.codeable_concept(svc.get("procedure_code"), c.SYSTEM["cpt"])
            or c.data_absent(),
            "revenue": c.codeable_concept(svc.get("revenue_code"), c.SYSTEM["revenue"]),
            "quantity": c.quantity(svc.get("units")),
            "servicedDate": _serviced_date(svc.get("dates") or []),
            "adjudication": [a for a in adjudication if a],
        }
        items.append(item)
    return items


def _totals(claim: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    totals = [
        _adjudication("submitted", c.SYSTEM["adjudication"], claim.get("total_charge")),
        _adjudication("benefit", c.SYSTEM["adjudication"], claim.get("total_paid")),
    ]
    # Claim-level CAS adjustments (before any SVC) surface as extra totals so no
    # money is dropped, tagged with their X12 group/reason codes.
    totals += [_as_total(a) for a in _cas_adjudications(claim.get("adjustments") or [])]
    totals = [t for t in totals if t]
    return totals or None


def _as_total(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Reshape an adjudication entry for ``ExplanationOfBenefit.total``.

    ``total`` is only ``category`` + ``amount`` in R4 — unlike
    ``item.adjudication`` it has no ``reason`` element, and emitting one makes
    the resource invalid. Keep the X12 reason code by carrying it as a second
    coding on the category rather than dropping the information.
    """
    total: Dict[str, Any] = {"category": entry["category"], "amount": entry["amount"]}
    reason_codings = (entry.get("reason") or {}).get("coding") or []
    if reason_codings:
        total["category"] = {"coding": (entry["category"].get("coding") or []) + reason_codings}
    return total


def _payment(payment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    amount = c.money(payment.get("total_paid_amount"))
    trace = c.identifier(payment.get("trace_number"))
    date = c._clean(payment.get("payment_date"))
    if not (amount or trace or date):
        return None
    return {"amount": amount, "identifier": trace, "date": date}


def _process_notes(
    claim: Dict[str, Any], provider_adjustments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    pr = c._clean(claim.get("patient_responsibility"))
    if pr:
        notes.append({"type": "display", "text": f"Patient responsibility: {pr}"})
    for adj in provider_adjustments:
        parts = [
            f"provider {c._clean(adj.get('provider_id')) or '?'}",
            f"reason {c._clean(adj.get('adjustment_reason')) or '?'}",
            f"amount {c._clean(adj.get('amount')) or '?'}",
        ]
        notes.append({"type": "display", "text": "Provider-level adjustment (PLB): " + ", ".join(parts)})
    return notes


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _adjudication(
    category_code: str,
    system: str,
    amount: Any,
    reason_code: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    money = c.money(amount)
    if money is None:
        return None
    entry: Dict[str, Any] = {"category": c.codeable_concept(category_code, system), "amount": money}
    if reason_code:
        entry["reason"] = c.codeable_concept(reason_code, c.SYSTEM["adjustment_reason"])
    return entry


def _cas_adjudications(adjustments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for adj in adjustments:
        entry = _adjudication(
            c._clean(adj.get("group_code")) or "adjustment",
            c.SYSTEM["adjustment_group"],
            adj.get("amount"),
            reason_code=c._clean(adj.get("reason_code")),
        )
        if entry:
            out.append(entry)
    return out


def _serviced_date(dates: List[Dict[str, Any]]) -> Optional[str]:
    """Pick the service date (DTM 472) from a service payment's dates."""
    for d in dates:
        if str(d.get("qualifier", "")).strip() == "472":
            value = c._clean(d.get("value"))
            if value:
                return value.split("/")[0].split(" ")[0]
    return None
