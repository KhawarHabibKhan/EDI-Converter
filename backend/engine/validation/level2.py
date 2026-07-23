"""SNIP Level 2 — Requirement.

Dispatches to the per-transaction-type rule module (each encodes its TR3
implementation-guide required segments/elements/loops + basic data types).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from engine.validation.rules import t270_271, t276_277, t834, t835, t837i, t837p
from engine.x12_reader import EdiDocument

_DISPATCH: Dict[str, Callable[[EdiDocument, str], List[Dict[str, Any]]]] = {
    "837P": t837p.check,
    "837I": t837i.check,
    "835": t835.check,
    "834": t834.check,
    "270": t270_271.check,
    "271": t270_271.check,
    "276": t276_277.check,
    "277": t276_277.check,
}


def check(doc: EdiDocument, txn_type: str) -> List[Dict[str, Any]]:
    """Run Level-2 requirement rules for the detected transaction type."""
    fn = _DISPATCH.get(txn_type)
    if fn is None:
        return []
    return fn(doc, txn_type)


def supported_types() -> list[str]:
    return sorted(_DISPATCH)
