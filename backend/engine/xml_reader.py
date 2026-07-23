"""Our-schema XML  →  normalized dict  (the reverse of ``xml_writer``).

``xml_writer`` emits a regular, deterministic shape:

* a **dict** becomes an element whose children are named by key,
* a **list** becomes an element whose children are all ``<item>``,
* a **scalar** becomes an element with text,
* ``None`` / empty dict / empty list become a self-closing ``<tag/>``.

This module walks that structure back into a Python dict so the FHIR pipeline
can accept a v1 XML export as input. Because the writer's shape is regular, the
inverse is deterministic. Standard library (``xml.etree.ElementTree``) only.

Note: XML carries no type information, so scalars come back as strings (as they
largely were in the mapper output). The FHIR builders parse amounts/quantities
from strings, so this is lossless for our purposes.
"""

from __future__ import annotations

from typing import Any, Dict, List
from xml.etree import ElementTree as ET


class XmlReadError(Exception):
    """Raised when the input is not well-formed XML."""


def _element_to_value(el: ET.Element) -> Any:
    children = list(el)

    if not children:
        # Leaf: scalar text, or a self-closing element (None / empty container).
        text = (el.text or "").strip()
        return text if text else None

    # A list is an element whose every child is <item>.
    if all(child.tag == "item" for child in children):
        return [_element_to_value(child) for child in children]

    # Otherwise it's a dict keyed by child tag names.
    result: Dict[str, Any] = {}
    for child in children:
        result[child.tag] = _element_to_value(child)
    return result


def to_dict(xml_text: str) -> Dict[str, Any]:
    """Parse our-schema XML text into a normalized dict.

    Returns the value of the root element (``EdiDocument``), which for a valid
    v1 export is always a dict.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise XmlReadError(f"Input is not well-formed XML: {exc}") from exc

    value = _element_to_value(root)
    if not isinstance(value, dict):
        raise XmlReadError(
            "XML does not match the expected EDI-Converter schema "
            "(root element has no field children)."
        )
    return value
