"""276 / 277  →  FHIR R4 ``Task`` (+ referenced resources).

Consumes the v1 normalized dict from ``engine.mappers.map_277`` (which handles
both 276 and 277). Each claim-status trace (TRN) becomes a ``Task``; the
patient / payer / provider named above the claim level become the ``Patient``
and ``Organization`` resources the Tasks reference.

* 276 (request)  → ``Task`` with ``status`` = ``requested``.
* 277 (response) → ``Task`` with ``status`` = ``completed`` and STC claim-status
  detail captured in ``businessStatus`` + ``output[]``.

Base FHIR R4 structure only. See docx/v2/5-fhir-mapping-reference.md §5.7.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.fhir import common as c


def to_fhir(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    is_request = "276" in str(data.get("source_transaction", ""))
    entities = data.get("entities") or []

    patient_src = _find(entities, ("QC", "IL"))
    payer_src = _find(entities, ("PR",))
    provider_src = _find(entities, ("1P", "82", "41", "2B"))

    ids = {"patient": "patient-1", "payer": "org-payer-1", "provider": "org-provider-1"}

    shared: List[Dict[str, Any]] = []
    if patient_src:
        shared.append(_patient(patient_src, ids["patient"]))
    if payer_src:
        shared.append(_organization(payer_src, ids["payer"]))
    if provider_src:
        shared.append(_organization(provider_src, ids["provider"]))

    tasks: List[Dict[str, Any]] = []
    for i, claim in enumerate(data.get("claims") or [], start=1):
        tasks.append(_task(claim, i, is_request, ids, bool(patient_src), bool(payer_src), bool(provider_src)))

    return [c.prune(r) for r in shared + tasks]


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


def _organization(src: Dict[str, Any], oid: str) -> Dict[str, Any]:
    ident = c.identifier(src.get("id"))
    return {
        "resourceType": "Organization",
        "id": oid,
        "identifier": [ident] if ident else None,
        "name": c._clean(src.get("last_name_or_org")) or "Unknown Organization",
    }


# --------------------------------------------------------------------------- #
#  Task
# --------------------------------------------------------------------------- #
def _task(
    claim: Dict[str, Any],
    n: int,
    is_request: bool,
    ids: Dict[str, str],
    has_patient: bool,
    has_payer: bool,
    has_provider: bool,
) -> Dict[str, Any]:
    statuses = claim.get("statuses") or []
    first = statuses[0] if statuses else {}

    return {
        "resourceType": "Task",
        "id": f"task-{n}",
        "status": "requested" if is_request else "completed",
        "intent": "order",
        "code": {"text": "Health care claim status " + ("request" if is_request else "response")},
        "identifier": _identifiers(claim),
        "authoredOn": c._clean(first.get("status_date")),
        "businessStatus": _business_status(first),
        "for": c.reference("Patient", ids["patient"]) if has_patient else None,
        "requester": c.reference("Organization", ids["provider"]) if has_provider else None,
        "owner": c.reference("Organization", ids["payer"]) if has_payer else None,
        "output": _outputs(claim, statuses),
    }


def _identifiers(claim: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    idents = [c.identifier(claim.get("trace_number"))]
    for ref in claim.get("references") or []:
        idents.append(c.identifier(ref.get("value")))
    idents = [i for i in idents if i]
    return idents or None


def _business_status(status: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    category = c._clean(status.get("category_code"))
    if not category:
        return None
    cc = c.codeable_concept(category, c.SYSTEM["claim_status_category"])
    code = c._clean(status.get("status_code"))
    if cc and code:
        cc["coding"].append({"system": c.SYSTEM["claim_status"], "code": code})
    return cc


def _outputs(claim: Dict[str, Any], statuses: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    outputs: List[Dict[str, Any]] = []
    for st in statuses:
        outputs.append(_status_output(st))
    # Service-line-level statuses, if present.
    for line in claim.get("service_lines") or []:
        proc = c._clean(line.get("procedure_code"))
        for st in line.get("statuses") or []:
            out = _status_output(st, prefix=f"line {proc}: " if proc else "")
            outputs.append(out)
    outputs = [o for o in outputs if o]
    return outputs or None


def _status_output(st: Dict[str, Any], prefix: str = "") -> Optional[Dict[str, Any]]:
    parts = []
    cat = c._clean(st.get("category_code"))
    code = c._clean(st.get("status_code"))
    if cat or code:
        parts.append(f"status {cat or '?'}:{code or '?'}")
    charge = c._clean(st.get("total_charge"))
    paid = c._clean(st.get("paid_amount"))
    if charge:
        parts.append(f"charge {charge}")
    if paid:
        parts.append(f"paid {paid}")
    if not parts:
        return None
    return {
        "type": {"text": "Claim status"},
        "valueString": prefix + ", ".join(parts),
    }


def _find(entities: List[Dict[str, Any]], roles: tuple) -> Optional[Dict[str, Any]]:
    for ent in entities:
        if str(ent.get("entity_role_code", "")).strip() in roles:
            return ent
    return None
