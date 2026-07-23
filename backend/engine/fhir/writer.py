"""FHIR writer — dispatch a normalized dict to its resource mapper and Bundle it.

Mirrors the v1 ``converter`` dispatch pattern: a table maps transaction type to
a per-resource mapper. Types with no FHIR mapper yet raise ``UnsupportedFhirError``
with a message naming the phase they arrive in (like v1's unsupported-type path).

The public entry point is ``to_fhir(dict, transaction_type) -> Bundle dict``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from engine.fhir import (
    common,
    map_claim,
    map_coverage,
    map_eligibility,
    map_eob,
    map_task,
)


class UnsupportedFhirError(Exception):
    """Raised when no FHIR mapper exists for the transaction type yet."""


# transaction type -> resource mapper (dict -> list[resource dicts]).
_MAPPERS: Dict[str, Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = {
    "837P": map_claim.to_fhir,
    "837I": map_claim.to_fhir,
    "837": map_claim.to_fhir,
    "835": map_eob.to_fhir,
    "834": map_coverage.to_fhir,
    "270": map_eligibility.to_fhir,
    "271": map_eligibility.to_fhir,
    "276": map_task.to_fhir,
    "277": map_task.to_fhir,
}

# Recognized types that map in a later phase — for friendly messages. All eight
# X12 types now have a FHIR mapper, so this is empty.
_PLANNED: Dict[str, str] = {}


def _resolve_type(data: Dict[str, Any], transaction_type: str) -> str:
    """Normalize the transaction type from the arg or the dict's source field."""
    key = (transaction_type or "auto").strip().upper()
    if key and key != "AUTO":
        return key
    # Derive from our dict: e.g. "ANSI X12 837P" -> "837P".
    source = str(data.get("source_transaction", "")).upper()
    for candidate in list(_MAPPERS) + list(_PLANNED):
        if candidate in source:
            return candidate
    return key


def to_fhir(data: Dict[str, Any], transaction_type: str = "auto") -> Dict[str, Any]:
    """Convert a normalized dict to a FHIR Bundle (type: collection).

    Raises:
        UnsupportedFhirError: if the type has no FHIR mapper yet.
    """
    key = _resolve_type(data, transaction_type)
    mapper = _MAPPERS.get(key)
    if mapper is None:
        planned = _PLANNED.get(key)
        hint = f" It arrives in {planned}." if planned else ""
        raise UnsupportedFhirError(
            f"FHIR conversion for {key or 'this transaction'} is not available "
            f"yet.{hint} Supported now: {', '.join(sorted(_MAPPERS))}."
        )
    resources = mapper(data)
    return common.bundle(resources)


def supported_types() -> list[str]:
    """List transaction types with a FHIR mapper today."""
    return sorted(_MAPPERS)
