"""Hand-built FHIR R4 structural validator (V2-D).

Validates a generated FHIR **Bundle** against base FHIR R4 structure — the same
zero-runtime-dependency philosophy as the rest of the engine. It checks:

* Bundle shape (``resourceType`` / ``type`` / ``entry``),
* required elements per resource type (for the types this project emits),
* status/code values against their base R4 value sets,
* **reference integrity** — every ``{"reference": "Type/id"}`` resolves to a
  resource present in the Bundle (Bundle is ``type: collection``),
* coding hygiene — a ``code`` should carry a ``system`` (base R4 recommendation),
* ``data-absent-reason`` extensions are surfaced as informational notes.

Scope: **base FHIR R4 structure**, not Implementation-Guide certification.
Full profile validation (CARIN Blue Button / US Core / Da Vinci via the official
HL7 validator) is a CI concern documented as the remaining V2-D follow-up; see
docx/v2/3-fhir-rules.md §3.3 and docx/v2/4-fhir-phases.md (V2-D).
"""

from __future__ import annotations

from typing import Any, Dict, List

ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"

# Required top-level elements per resource type (base FHIR R4, for the resources
# this engine emits). Organization is handled specially (name-or-identifier).
_REQUIRED: Dict[str, List[str]] = {
    "Coverage": ["status", "beneficiary", "payor"],
    "Claim": ["status", "type", "use", "patient", "created", "provider", "priority", "insurance"],
    "ExplanationOfBenefit": [
        "status", "type", "use", "patient", "created", "insurer", "provider", "outcome", "insurance",
    ],
    "CoverageEligibilityRequest": ["status", "purpose", "patient", "created", "insurer"],
    "CoverageEligibilityResponse": [
        "status", "purpose", "patient", "created", "request", "outcome", "insurer", "insurance",
    ],
    "Task": ["status", "intent"],
    "Patient": [],
    "Practitioner": [],
}

_FINANCIAL_STATUS = {"active", "cancelled", "draft", "entered-in-error"}
_VALUE_SETS: Dict[tuple, set] = {
    ("Claim", "status"): _FINANCIAL_STATUS,
    ("Claim", "use"): {"claim", "preauthorization", "predetermination"},
    ("ExplanationOfBenefit", "status"): _FINANCIAL_STATUS,
    ("ExplanationOfBenefit", "use"): {"claim", "preauthorization", "predetermination"},
    ("ExplanationOfBenefit", "outcome"): {"queued", "complete", "error", "partial"},
    ("Coverage", "status"): _FINANCIAL_STATUS,
    ("CoverageEligibilityRequest", "status"): _FINANCIAL_STATUS,
    ("CoverageEligibilityResponse", "status"): _FINANCIAL_STATUS,
    ("CoverageEligibilityResponse", "outcome"): {"queued", "complete", "error", "partial"},
    ("Task", "status"): {
        "draft", "requested", "received", "accepted", "rejected", "ready", "cancelled",
        "in-progress", "on-hold", "failed", "completed", "entered-in-error",
    },
    ("Task", "intent"): {
        "unknown", "proposal", "plan", "order", "original-order", "reflex-order",
        "filler-order", "instance-order", "option",
    },
    ("Patient", "gender"): {"male", "female", "other", "unknown"},
}

_DATA_ABSENT_URL = "http://hl7.org/fhir/StructureDefinition/data-absent-reason"


def validate_bundle(bundle: Any) -> List[Dict[str, Any]]:
    """Validate a FHIR Bundle dict. Returns a list of issue dicts.

    Each issue: ``{"severity", "path", "message"}``.
    """
    issues: List[Dict[str, Any]] = []

    if not isinstance(bundle, dict):
        return [_issue(ERROR, "Bundle", "Result is not a FHIR resource object.")]
    if bundle.get("resourceType") != "Bundle":
        issues.append(_issue(ERROR, "Bundle", "resourceType is not 'Bundle'."))
    if not bundle.get("type"):
        issues.append(_issue(ERROR, "Bundle.type", "Bundle.type is required."))

    entries = bundle.get("entry")
    if not isinstance(entries, list) or not entries:
        issues.append(_issue(WARNING, "Bundle.entry", "Bundle has no entries."))
        return issues

    # Index resource ids for reference-integrity checks.
    present: set = set()
    for e in entries:
        res = (e or {}).get("resource") if isinstance(e, dict) else None
        if isinstance(res, dict) and res.get("resourceType") and res.get("id"):
            present.add(f"{res['resourceType']}/{res['id']}")

    for i, e in enumerate(entries):
        res = (e or {}).get("resource") if isinstance(e, dict) else None
        base = f"Bundle.entry[{i}]"
        if not isinstance(res, dict):
            issues.append(_issue(ERROR, base, "Entry has no resource object."))
            continue
        issues.extend(_validate_resource(res, base, present))

    return issues


def validate_report(bundle: Any) -> Dict[str, Any]:
    """Validate and summarise. Shape mirrors the v1 validator's report so the
    frontend can render it with the same component."""
    issues = validate_bundle(bundle)
    errors = sum(1 for it in issues if it["severity"] == ERROR)
    warnings = sum(1 for it in issues if it["severity"] == WARNING)
    return {
        "valid": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "info_count": sum(1 for it in issues if it["severity"] == INFO),
        "issue_count": len(issues),
        "issues": issues,
    }


# --------------------------------------------------------------------------- #
#  Per-resource checks
# --------------------------------------------------------------------------- #
def _validate_resource(res: Dict[str, Any], base: str, present: set) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    rtype = res.get("resourceType")
    path = f"{base}.resource({rtype}/{res.get('id', '?')})"

    if not rtype:
        return [_issue(ERROR, base, "Resource has no resourceType.")]

    # Required elements.
    for field in _REQUIRED.get(rtype, []):
        if _missing(res.get(field)):
            issues.append(_issue(ERROR, f"{path}.{field}", f"{rtype}.{field} is required but missing."))

    # Organization: name or identifier must be present (constraint org-1).
    if rtype == "Organization" and _missing(res.get("name")) and _missing(res.get("identifier")):
        issues.append(_issue(ERROR, path, "Organization requires a name or identifier."))

    # Value-set checks.
    for (vs_type, field), allowed in _VALUE_SETS.items():
        if vs_type != rtype:
            continue
        val = res.get(field)
        values = val if isinstance(val, list) else ([val] if val is not None else [])
        for v in values:
            if isinstance(v, str) and v not in allowed:
                issues.append(_issue(WARNING, f"{path}.{field}",
                                     f"{rtype}.{field} value '{v}' is outside the base R4 value set."))

    # Deep checks: references, codings, data-absent.
    issues.extend(_deep_checks(res, path, present))
    return issues


def _deep_checks(obj: Any, path: str, present: set) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    if isinstance(obj, dict):
        # Reference integrity.
        ref = obj.get("reference")
        if isinstance(ref, str) and "/" in ref and ref not in present:
            issues.append(_issue(ERROR, path, f"Reference '{ref}' does not resolve within the Bundle."))

        # Coding hygiene: code without system.
        if "code" in obj and isinstance(obj.get("code"), str) and not obj.get("system"):
            issues.append(_issue(WARNING, path, "A coding has a code but no system URI."))

        # data-absent-reason extension.
        if obj.get("url") == _DATA_ABSENT_URL:
            issues.append(_issue(INFO, path, "A required value was absent in the source and marked data-absent."))

        for k, v in obj.items():
            issues.extend(_deep_checks(v, f"{path}.{k}", present))

    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            issues.extend(_deep_checks(v, f"{path}[{idx}]", present))

    return issues


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _issue(severity: str, path: str, message: str) -> Dict[str, Any]:
    return {"severity": severity, "path": path, "message": message}
