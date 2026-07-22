"""Shared JSON/dict → XML serializer.

Every transaction mapper returns a plain dict, so a single serializer here
turns any of them (837, 835, 834, 271, 277, …) into XML. This keeps XML output
DRY: add a new mapper and it gets XML for free.

Standard library only (``xml.sax.saxutils`` for escaping) — no new dependency.
"""

from __future__ import annotations

import re
from typing import Any
from xml.sax.saxutils import escape

_INVALID = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_tag(name: Any) -> str:
    """Coerce a dict key into a valid XML tag name."""
    s = _INVALID.sub("_", str(name))
    if not s or not re.match(r"[A-Za-z_]", s[0]):
        s = "_" + s
    return s


def _node(tag: str, value: Any, depth: int) -> str:
    indent = "  " * depth
    t = _safe_tag(tag)

    if isinstance(value, dict):
        if not value:
            return f"{indent}<{t}/>"
        inner = "\n".join(_node(k, v, depth + 1) for k, v in value.items())
        return f"{indent}<{t}>\n{inner}\n{indent}</{t}>"

    if isinstance(value, (list, tuple)):
        if not value:
            return f"{indent}<{t}/>"
        inner = "\n".join(_node("item", v, depth + 1) for v in value)
        return f"{indent}<{t}>\n{inner}\n{indent}</{t}>"

    if value is None:
        return f"{indent}<{t}/>"

    if isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = escape(str(value))
    return f"{indent}<{t}>{text}</{t}>"


def to_xml(data: Any, root: str = "EdiDocument") -> str:
    """Serialize a mapper's dict output to a pretty-printed XML document."""
    body = _node(root, data, 0)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"
