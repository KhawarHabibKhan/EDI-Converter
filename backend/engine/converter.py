"""Conversion entry point.

Ties the reader, the detector, and the per-transaction mappers together. This
is the single function the web layer calls. No HTTP knowledge lives here.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from engine import detector, x12_reader
from engine.mappers import map_271, map_277, map_834, map_835, map_837


class UnsupportedTransactionError(Exception):
    """Raised when we have no mapper for the requested/detected type."""


# Dispatch table: transaction type -> mapper function taking an EdiDocument.
# Phases 3-5 add 835 / 834 / 271 / 277 here.
_MAPPERS: Dict[str, Callable[[x12_reader.EdiDocument], Dict[str, Any]]] = {
    "837P": map_837.to_json,
    "837I": map_837.to_json,   # same mapper, branches on implementation guide
    "837": map_837.to_json,    # generic alias
    "835": map_835.to_json,
    "834": map_834.to_json,
    "270": map_271.to_json,   # eligibility inquiry (same structure as 271)
    "271": map_271.to_json,
    "276": map_277.to_json,   # claim status request (same structure as 277)
    "277": map_277.to_json,
}

# Types we recognize but don't map yet (for friendly messages). Empty now.
_PLANNED: Dict[str, str] = {}


def convert_edi(raw: str, transaction_type: str = "auto") -> Dict[str, Any]:
    """Convert raw EDI text to a JSON-ready dict.

    Args:
        raw: X12 EDI content as text.
        transaction_type: ``"auto"`` (default) detects the type from the file,
            or one of the keys in ``_MAPPERS`` to force it.

    Raises:
        ValueError: if the input contains no EDI segments.
        UnsupportedTransactionError: if no mapper exists for the type.
    """
    doc = x12_reader.parse(raw)

    key = (transaction_type or "auto").strip()
    if key.lower() == "auto":
        try:
            key = detector.detect_from_doc(doc)
        except detector.DetectionError as exc:
            raise UnsupportedTransactionError(str(exc))
    key = key.upper()

    if key not in _MAPPERS:
        name = detector.TRANSACTION_NAMES.get(key, "this transaction")
        planned = _PLANNED.get(key)
        hint = f" It is planned for {planned}." if planned else ""
        raise UnsupportedTransactionError(
            f"Detected {key} ({name}), which is not supported yet.{hint} "
            f"Supported now: {', '.join(sorted(_MAPPERS))}."
        )
    return _MAPPERS[key](doc)


def supported_types() -> list[str]:
    """List transaction types the converter currently supports."""
    return sorted(_MAPPERS)
