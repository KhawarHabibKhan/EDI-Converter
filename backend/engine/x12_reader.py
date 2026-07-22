"""Low-level X12 EDI reader.

Turns raw EDI text into a navigable list of segments, auto-detecting the
delimiters from the fixed-position ISA header. Shared by every mapper so the
tokenizing logic lives in exactly one place.

Ported from the proven standalone parser (Health care EDI/edi_1500_to_json.py).
Pure Python, no third-party dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Delimiters:
    """Delimiters used inside an X12 interchange."""

    segment: str = "~"
    element: str = "*"
    component: str = ":"
    repetition: str = "^"


def detect_delimiters(raw: str) -> Delimiters:
    """Derive delimiters from the fixed-position ISA segment.

    The ISA segment is exactly 106 characters:
      - element separator   = index 3
      - repetition separator = index 82 (ISA11)
      - component separator  = index 104 (ISA16)
      - segment terminator   = index 105
    Falls back to sensible defaults when there is no ISA header.
    """
    d = Delimiters()
    isa_pos = raw.find("ISA")
    if isa_pos != -1 and len(raw) >= isa_pos + 106:
        d.element = raw[isa_pos + 3]
        d.repetition = raw[isa_pos + 82]
        d.component = raw[isa_pos + 104]
        d.segment = raw[isa_pos + 105]
    return d


@dataclass
class Segment:
    """A single EDI segment: an id plus its ordered elements."""

    seg_id: str
    elements: List[str]

    def el(self, idx: int, default: str = "") -> str:
        """1-based element accessor (EDI convention). el(1) => elements[0]."""
        return self.elements[idx - 1] if 0 < idx <= len(self.elements) else default

    def comp(self, el_idx: int, comp_idx: int, delim: "Delimiters", default: str = "") -> str:
        """Access a component within a composite element (both 1-based)."""
        value = self.el(el_idx)
        parts = value.split(delim.component)
        return parts[comp_idx - 1] if 0 < comp_idx <= len(parts) else default


@dataclass
class EdiDocument:
    """A tokenized EDI file: its segments plus the delimiters used."""

    segments: List[Segment]
    delim: Delimiters

    def first(self, seg_id: str) -> Segment | None:
        """Return the first segment with the given id, or None."""
        for seg in self.segments:
            if seg.seg_id == seg_id:
                return seg
        return None


def tokenize(raw: str, delim: Delimiters) -> List[Segment]:
    """Split raw EDI text into a flat list of Segment objects."""
    segments: List[Segment] = []
    # Normalize newlines so files with segment terminators + CRLF both work.
    cleaned = raw.replace("\r", "").replace("\n", "")
    for chunk in cleaned.split(delim.segment):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(delim.element)
        seg_id = parts[0].strip()
        elements = list(parts[1:])
        segments.append(Segment(seg_id, elements))
    return segments


def parse(raw: str) -> EdiDocument:
    """Parse raw EDI text into an EdiDocument (segments + delimiters).

    Raises:
        ValueError: if no EDI segments are found.
    """
    delim = detect_delimiters(raw)
    segments = tokenize(raw, delim)
    if not segments:
        raise ValueError("No EDI segments found in input.")
    return EdiDocument(segments=segments, delim=delim)
