"""Input adapter — accept ``.edi/.dat`` (X12), ``.json``, or ``.xml`` and return
the v1 **normalized dict** plus the detected transaction type.

The FHIR pipeline is written once, against the normalized dict. This adapter is
what lets the FHIR page accept our own JSON/XML exports in addition to raw EDI:

* X12 text  → ``converter.convert_edi`` (the v1 parser + mappers), or
* our JSON  → ``json.loads`` (already the normalized dict), or
* our XML   → ``xml_reader.to_dict`` (reverse of ``xml_writer``).

Format is detected from the **content** first (robust to misnamed files), with
the filename extension as a tiebreaker. JSON/XML input must be *our* schema —
arbitrary JSON/XML is rejected with a clean error (docx/v2/3-fhir-rules.md §3.2).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from engine import converter, detector, xml_reader

# Longest / most specific codes first so "837P" wins over "837".
_KNOWN_TYPES = ["837P", "837I", "837", "835", "834", "270", "271", "276", "277"]


class InputFormatError(Exception):
    """Raised when the input is not recognizable EDI / our JSON / our XML."""


def _type_from_dict(data: Dict[str, Any]) -> str:
    """Derive the transaction code from a normalized dict's source field."""
    source = str(data.get("source_transaction", "")).upper()
    for code in _KNOWN_TYPES:
        if code in source:
            return code
    return "auto"


def _looks_like_our_dict(data: Any) -> bool:
    """Our normalized dicts carry a source_transaction and/or a claims list."""
    return isinstance(data, dict) and (
        "source_transaction" in data or "claims" in data or "header" in data
    )


def _sniff_format(text: str, ext: str) -> str:
    """Return 'edi' | 'json' | 'xml' from content, using extension as tiebreaker."""
    stripped = text.lstrip("﻿ \t\r\n")
    if stripped.startswith("<"):
        return "xml"
    if stripped[:1] in "{[":
        return "json"
    if stripped.startswith("ISA") or "ST" in stripped[:2048]:
        return "edi"
    # Fall back to the extension when the content is ambiguous.
    if ext in (".json",):
        return "json"
    if ext in (".xml",):
        return "xml"
    if ext in (".edi", ".dat", ".txt", ".x12"):
        return "edi"
    raise InputFormatError(
        "Unrecognized input format. Provide X12 EDI (.edi/.dat), or an "
        "EDI-Converter JSON/XML export (.json/.xml)."
    )


def detect_and_load(text: str, filename: str = "") -> Tuple[Dict[str, Any], str]:
    """Detect the input format and return ``(normalized_dict, transaction_type)``.

    Raises:
        InputFormatError: input is not EDI / our JSON / our XML.
        ValueError: EDI text has no segments (from the v1 parser).
        converter.UnsupportedTransactionError: EDI type has no v1 mapper.
    """
    import os

    ext = os.path.splitext(filename or "")[1].lower()
    fmt = _sniff_format(text, ext)

    if fmt == "edi":
        try:
            transaction_type = detector.detect_transaction_type(text)
        except detector.DetectionError as exc:
            raise InputFormatError(str(exc))
        data = converter.convert_edi(text, transaction_type)
        return data, transaction_type

    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputFormatError(f"Input is not valid JSON: {exc}")
        if not _looks_like_our_dict(data):
            raise InputFormatError(
                "JSON does not match the EDI-Converter schema. Upload a JSON "
                "file produced by this converter's JSON output."
            )
        return data, _type_from_dict(data)

    # fmt == "xml"
    try:
        data = xml_reader.to_dict(text)
    except xml_reader.XmlReadError as exc:
        raise InputFormatError(str(exc))
    if not _looks_like_our_dict(data):
        raise InputFormatError(
            "XML does not match the EDI-Converter schema. Upload an XML file "
            "produced by this converter's XML output."
        )
    return data, _type_from_dict(data)
