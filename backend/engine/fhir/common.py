"""Shared FHIR builders + the canonical code-system URI table.

These helpers keep every resource mapper honest and DRY: coded values always
become a ``CodeableConcept`` with a ``system`` URI, links always become a
``Reference``, money always carries a currency, and so on. Nothing here knows
about X12 — mappers translate our normalized dict into these primitives.

FHIR paths/URIs follow the FHIR R4 base spec (see docx/v2/3-fhir-rules.md §3.5).
Standard library only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
#  Code-system URIs (canonical list — docx/v2/3-fhir-rules.md §3.5)
# --------------------------------------------------------------------------- #
SYSTEM = {
    "icd10cm": "http://hl7.org/fhir/sid/icd-10-cm",
    "icd10pcs": "http://www.cms.gov/Medicare/Coding/ICD10",
    "cpt": "http://www.ama-assn.org/go/cpt",
    "hcpcs": "https://bluebutton.cms.gov/resources/codesystem/hcpcs",
    "npi": "http://hl7.org/fhir/sid/us-npi",
    "claim_type": "http://terminology.hl7.org/CodeSystem/claim-type",
    "adjudication": "http://terminology.hl7.org/CodeSystem/adjudication",
    "adjustment_group": "https://x12.org/codes/claim-adjustment-group-codes",
    "adjustment_reason": "https://x12.org/codes/claim-adjustment-reason-codes",
    "gender": "http://hl7.org/fhir/administrative-gender",
    "revenue": "https://www.nubc.org/CodeSystem/RevenueCodes",
    "data_absent": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
    "process_priority": "http://terminology.hl7.org/CodeSystem/processpriority",
    # V2-C
    "coverage_class": "http://terminology.hl7.org/CodeSystem/coverage-class",
    "subscriber_relationship": "http://terminology.hl7.org/CodeSystem/subscriber-relationship",
    "insurance_line": "https://x12.org/codes/insurance-line-codes",
    "service_type": "https://x12.org/codes/service-type-codes",
    "eligibility_info": "https://x12.org/codes/eligibility-benefit-info-codes",
    "benefit_network": "http://terminology.hl7.org/CodeSystem/benefit-network",
    "claim_status_category": "https://x12.org/codes/claim-status-category-codes",
    "claim_status": "https://x12.org/codes/claim-status-codes",
}

# X12 diagnosis-qualifier -> code system (ICD-10 vs ICD-9). We emit ICD-10 CM
# for the modern qualifiers; unknown/legacy fall back to ICD-10-CM as the base.
DIAG_SYSTEM_BY_QUALIFIER = {
    "ABK": SYSTEM["icd10cm"], "ABF": SYSTEM["icd10cm"],
    "ABJ": SYSTEM["icd10cm"], "APR": SYSTEM["icd10cm"],
    "ABN": SYSTEM["icd10cm"],
}

# X12 administrative gender (our mapper expands M/F/U to words) -> FHIR code.
GENDER_CODE = {
    "Male": "male", "Female": "female", "Unknown": "unknown",
    "M": "male", "F": "female", "U": "unknown",
}

DEFAULT_CURRENCY = "USD"


# --------------------------------------------------------------------------- #
#  Primitive builders
# --------------------------------------------------------------------------- #
def _clean(value: Any) -> Optional[str]:
    """Return a trimmed non-empty string, or None."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def icd10cm_code(code: Any) -> Optional[str]:
    """Format an X12 diagnosis code as ICD-10-CM expects it in FHIR.

    X12 carries ICD-10-CM **without** the decimal point (``J0300``), but the
    ``http://hl7.org/fhir/sid/icd-10-cm`` code system is defined with it
    (``J03.00``) — so passing the X12 form straight through produces codes the
    HL7 validator rejects as unknown. The category is always the first three
    characters; anything after that is the subclassification.
    """
    s = _clean(code)
    if not s or "." in s:
        return s
    return f"{s[:3]}.{s[3:]}" if len(s) > 3 else s


def reference(resource_type: str, local_id: str) -> Dict[str, str]:
    """A FHIR Reference: {"reference": "Patient/patient-1"}."""
    return {"reference": f"{resource_type}/{local_id}"}


def identifier(value: Any, system: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """A FHIR Identifier carrying a business id. None if value is empty."""
    v = _clean(value)
    if v is None:
        return None
    ident: Dict[str, Any] = {"value": v}
    if system:
        ident["system"] = system
    return ident


def codeable_concept(
    code: Any, system: Optional[str] = None, display: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """A FHIR CodeableConcept: a code tagged with the system it came from.

    Never emit a bare code (docx/v2/3-fhir-rules.md §3.4).
    """
    c = _clean(code)
    if c is None:
        return None
    coding: Dict[str, Any] = {"code": c}
    if system:
        coding["system"] = system
    disp = _clean(display)
    if disp:
        coding["display"] = disp
    return {"coding": [coding]}


def money(amount: Any, currency: str = DEFAULT_CURRENCY) -> Optional[Dict[str, Any]]:
    """A FHIR Money. Parses our string amounts to a number; None if unparseable."""
    a = _clean(amount)
    if a is None:
        return None
    try:
        value = round(float(a), 2)
    except (TypeError, ValueError):
        return None
    return {"value": value, "currency": currency}


def quantity(value: Any) -> Optional[Dict[str, Any]]:
    """A FHIR Quantity (unit-less count). None if empty/unparseable."""
    v = _clean(value)
    if v is None:
        return None
    try:
        num = float(v)
    except (TypeError, ValueError):
        return None
    if num.is_integer():
        num = int(num)
    return {"value": num}


def human_name(
    family: Any, given: Any = None, entity_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """A FHIR HumanName. Organizations have no name here (they use .name)."""
    fam = _clean(family)
    giv = _clean(given)
    if fam is None and giv is None:
        return None
    name: Dict[str, Any] = {}
    if fam:
        name["family"] = fam
    if giv:
        name["given"] = [giv]
    return name or None


def address(entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a FHIR Address from our N3/N4 fields on an entity dict."""
    if not isinstance(entity, dict):
        return None
    line = [
        v for v in (_clean(entity.get("address_1")), _clean(entity.get("address_2")))
        if v
    ]
    addr: Dict[str, Any] = {}
    if line:
        addr["line"] = line
    for src, dst in (("city", "city"), ("state", "state"), ("postal_code", "postalCode")):
        v = _clean(entity.get(src))
        if v:
            addr[dst] = v
    return addr or None


def data_absent(field: str = "unknown") -> Dict[str, Any]:
    """A data-absent-reason extension for a FHIR-required value we don't have.

    Used instead of inventing clinical/financial data (docx/v2/3-fhir-rules.md).
    """
    return {
        "extension": [{
            "url": "http://hl7.org/fhir/StructureDefinition/data-absent-reason",
            "valueCode": field,
        }]
    }


def prune(obj: Any) -> Any:
    """Recursively drop None values and empty dicts/lists so resources stay clean.

    Keeps zeros and empty strings only if explicitly present as non-None.
    """
    if isinstance(obj, dict):
        cleaned = {k: prune(v) for k, v in obj.items()}
        return {k: v for k, v in cleaned.items() if v is not None and v != {} and v != []}
    if isinstance(obj, list):
        items = [prune(v) for v in obj]
        return [v for v in items if v is not None and v != {} and v != []]
    return obj


# Base for Bundle entry ``fullUrl``. Our references are relative ("Patient/p-1"),
# and FHIR resolves a relative reference against the base of the entry's
# fullUrl — so without one, nothing inside the Bundle is resolvable and the HL7
# validator reports every reference as unresolved. This host is a stable
# placeholder: the Bundles are conversion output, not records served from an
# actual FHIR server.
BUNDLE_BASE_URL = "http://edi-converter.local/fhir"


def entry(resource: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a resource as a Bundle entry (with a resolvable ``fullUrl``)."""
    rtype, rid = resource.get("resourceType"), resource.get("id")
    if not rtype or not rid:
        return {"resource": resource}
    return {"fullUrl": f"{BUNDLE_BASE_URL}/{rtype}/{rid}", "resource": resource}


def bundle(resources: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Assemble a FHIR Bundle (type: collection) from a list of resources."""
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [entry(r) for r in resources],
    }
