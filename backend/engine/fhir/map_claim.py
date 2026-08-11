"""837P / 837I  →  FHIR R4 ``Claim`` (+ referenced resources).

Consumes the v1 normalized dict produced by ``engine.mappers.map_837`` (never
raw X12) and returns a flat list of FHIR resource dicts: the ``Claim`` plus the
``Patient``, ``Coverage``, and ``Organization`` resources it references. The
writer collects these into one Bundle.

Each claim in the document gets its own resource set with deterministic,
claim-scoped local ids (``patient-1``, ``coverage-1``, ``org-payer-1``,
``claim-1``) so references resolve unambiguously even for multi-claim files.

See docx/v2/5-fhir-mapping-reference.md §5.3 for the field-level mapping.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.fhir import common as c


def to_fhir(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map an 837 normalized dict to a list of FHIR resources."""
    institutional = "837I" in str(data.get("source_transaction", ""))
    created = _created(data.get("header") or {})
    resources: List[Dict[str, Any]] = []
    for idx, claim in enumerate(data.get("claims") or [], start=1):
        resources.extend(_claim_resources(claim, idx, institutional, created))
    return resources


def _created(header: Dict[str, Any]) -> Optional[str]:
    """Claim.created (required, R4) — take the transaction (BHT) date, else GS."""
    txn = header.get("transaction") or {}
    fg = header.get("functional_group") or {}
    return c._clean(txn.get("date")) or c._clean(fg.get("date"))


def _claim_resources(
    claim: Dict[str, Any], n: int, institutional: bool, created: Optional[str]
) -> List[Dict[str, Any]]:
    patient_src = claim.get("patient") or claim.get("insured") or {}
    insured_src = claim.get("insured") or patient_src
    payer_src = claim.get("payer") or {}
    billing_src = (claim.get("providers") or {}).get("billing") or {}

    ids = {
        "patient": f"patient-{n}",
        "coverage": f"coverage-{n}",
        "payer": f"org-payer-{n}",
        "billing": f"provider-billing-{n}",
        "claim": f"claim-{n}",
    }

    resources: List[Dict[str, Any]] = []

    patient = _patient(patient_src, insured_src, ids["patient"])
    resources.append(patient)

    payer_org = _organization(payer_src, ids["payer"])
    resources.append(payer_org)

    coverage = _coverage(claim, insured_src, ids)
    resources.append(coverage)

    billing_res = _billing_provider(billing_src, ids["billing"])
    if billing_res is not None:
        resources.append(billing_res)

    claim_res = _claim(claim, n, institutional, ids, billing_res, created)
    resources.append(claim_res)

    return [c.prune(r) for r in resources]


# --------------------------------------------------------------------------- #
#  Referenced resources
# --------------------------------------------------------------------------- #
def _patient(patient_src: Dict[str, Any], insured_src: Dict[str, Any], pid: str) -> Dict[str, Any]:
    name = c.human_name(
        patient_src.get("last_name_or_org"), patient_src.get("first_name")
    )
    gender = c.GENDER_CODE.get(str(patient_src.get("gender", "")).strip())
    member_id = c.identifier(insured_src.get("id"))
    return {
        "resourceType": "Patient",
        "id": pid,
        "identifier": [member_id] if member_id else None,
        "name": [name] if name else None,
        "gender": gender,
        "birthDate": c._clean(patient_src.get("date_of_birth")),
        "address": ([c.address(patient_src)] if c.address(patient_src) else None),
    }


def _organization(payer_src: Dict[str, Any], oid: str) -> Dict[str, Any]:
    ident = c.identifier(payer_src.get("id"))
    return {
        "resourceType": "Organization",
        "id": oid,
        "identifier": [ident] if ident else None,
        "name": c._clean(payer_src.get("last_name_or_org")) or "Unknown Payer",
    }


def _coverage(claim: Dict[str, Any], insured_src: Dict[str, Any], ids: Dict[str, str]) -> Dict[str, Any]:
    group = c._clean(claim.get("group_number"))
    klass = None
    if group:
        klass = [{
            "type": c.codeable_concept("group", c.SYSTEM["coverage_class"]),
            "value": group,
            "name": c._clean(claim.get("group_name")),
        }]
    return {
        "resourceType": "Coverage",
        "id": ids["coverage"],
        "status": "active",
        "subscriberId": c._clean(insured_src.get("id")),
        "beneficiary": c.reference("Patient", ids["patient"]),
        "payor": [c.reference("Organization", ids["payer"])],
        "class": klass,
    }


def _billing_provider(billing_src: Dict[str, Any], bid: str) -> Optional[Dict[str, Any]]:
    if not billing_src:
        return None
    is_org = billing_src.get("entity_type") == "Organization"
    npi = None
    if str(billing_src.get("id_qualifier", "")).strip() == "XX":
        npi = c.identifier(billing_src.get("id"), c.SYSTEM["npi"])
    elif billing_src.get("id"):
        npi = c.identifier(billing_src.get("id"))

    if is_org:
        return {
            "resourceType": "Organization",
            "id": bid,
            "identifier": [npi] if npi else None,
            "name": c._clean(billing_src.get("last_name_or_org")) or "Unknown Provider",
        }
    name = c.human_name(billing_src.get("last_name_or_org"), billing_src.get("first_name"))
    return {
        "resourceType": "Practitioner",
        "id": bid,
        "identifier": [npi] if npi else None,
        "name": [name] if name else None,
    }


# --------------------------------------------------------------------------- #
#  Claim
# --------------------------------------------------------------------------- #
def _claim(
    claim: Dict[str, Any],
    n: int,
    institutional: bool,
    ids: Dict[str, str],
    billing_res: Optional[Dict[str, Any]],
    created: Optional[str],
) -> Dict[str, Any]:
    claim_type = "institutional" if institutional else "professional"

    provider_ref = None
    if billing_res is not None:
        provider_ref = c.reference(billing_res["resourceType"], ids["billing"])

    diagnoses, ptr_index = _diagnoses(claim.get("box_21_diagnoses") or [])

    res: Dict[str, Any] = {
        "resourceType": "Claim",
        "id": ids["claim"],
        "status": "active",
        "type": c.codeable_concept(claim_type, c.SYSTEM["claim_type"]),
        "use": "claim",
        "patient": c.reference("Patient", ids["patient"]),
        "created": created,
        "insurer": c.reference("Organization", ids["payer"]),
        "provider": provider_ref or c.data_absent(),
        "priority": c.codeable_concept("normal", c.SYSTEM["process_priority"]),
        "identifier": _identifiers(claim),
        "diagnosis": diagnoses or None,
        "insurance": [{
            "sequence": 1,
            "focal": True,
            "coverage": c.reference("Coverage", ids["coverage"]),
        }],
        "item": _items(claim, institutional, ptr_index) or None,
        "total": c.money(claim.get("total_charge")),
    }
    return res


def _identifiers(claim: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    ident = c.identifier(claim.get("patient_account_no"))
    return [ident] if ident else None


def _diagnoses(raw: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Build Claim.diagnosis[] and a map from X12 pointer -> FHIR sequence.

    X12 service lines point at diagnoses by letter (A, B, …) or 1-based number;
    both resolve to the diagnosis's position, which is the FHIR ``sequence``.
    """
    diagnoses: List[Dict[str, Any]] = []
    ptr_index: Dict[str, int] = {}
    for i, diag in enumerate(raw, start=1):
        code = c._clean(diag.get("code"))
        if not code:
            continue
        system = c.DIAG_SYSTEM_BY_QUALIFIER.get(
            str(diag.get("qualifier", "")).strip(), c.SYSTEM["icd10cm"]
        )
        if system == c.SYSTEM["icd10cm"]:
            code = c.icd10cm_code(code)     # X12 "J0300" -> ICD-10-CM "J03.00"
        diagnoses.append({
            "sequence": i,
            "diagnosisCodeableConcept": c.codeable_concept(code, system),
        })
        # Both the pointer letter (A/B/C) and the ordinal number map to sequence.
        ptr_index[str(i)] = i
        letter = c._clean(diag.get("pointer"))
        if letter:
            ptr_index[letter] = i
    return diagnoses, ptr_index


def _items(
    claim: Dict[str, Any], institutional: bool, ptr_index: Dict[str, int]
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for i, line in enumerate(claim.get("service_lines") or [], start=1):
        items.append(_item(line, i, institutional, ptr_index))
    return items


def _item(
    line: Dict[str, Any], seq: int, institutional: bool, ptr_index: Dict[str, int]
) -> Dict[str, Any]:
    if institutional:
        proc = line.get("box_44_hcpcs_procedure")
        modifiers = line.get("box_44_modifiers") or []
        net = line.get("box_47_line_charge")
        units = line.get("box_46_units")
        serviced = line.get("service_date")
    else:
        proc = line.get("box_24d_procedure_code")
        modifiers = line.get("box_24d_modifiers") or []
        net = line.get("box_24f_charges")
        units = line.get("box_24g_units")
        serviced = line.get("box_24a_service_date")

    proc_system = c.SYSTEM["cpt"]  # CPT/HCPCS share the productOrService slot
    product = c.codeable_concept(proc, proc_system)

    modifier_concepts = [
        c.codeable_concept(m, proc_system) for m in modifiers if c._clean(m)
    ]

    diag_seq = _resolve_pointers(line.get("box_24e_diagnosis_pointers") or [], ptr_index)

    item: Dict[str, Any] = {
        "sequence": seq,
        "productOrService": product or c.data_absent(),
        "modifier": modifier_concepts or None,
        "net": c.money(net),
        "quantity": c.quantity(units),
        "servicedDate": _serviced_date(serviced),
        "diagnosisSequence": diag_seq or None,
    }
    if institutional:
        item["revenue"] = c.codeable_concept(
            line.get("box_42_revenue_code"), c.SYSTEM["revenue"]
        )
    return item


def _serviced_date(value: Any) -> Optional[str]:
    """servicedDate expects a single date; our range format is 'start/end'."""
    v = c._clean(value)
    if v is None:
        return None
    # A DTP range renders as "start/end"; take the start for servicedDate.
    return v.split("/")[0].split(" ")[0]


def _resolve_pointers(pointers: List[Any], ptr_index: Dict[str, int]) -> List[int]:
    out: List[int] = []
    for p in pointers:
        key = c._clean(p)
        if key is None:
            continue
        seq = ptr_index.get(key)
        if seq is None and key.isdigit():
            seq = int(key)
        if seq is not None and seq not in out:
            out.append(seq)
    return out
