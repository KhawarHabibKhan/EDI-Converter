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

    # X12 only gained a repetition separator in version 4030. In earlier
    # versions ISA11 holds the Interchange Control Standards Identifier — the
    # letter "U" — so treating that byte as a delimiter would split real data on
    # the letter U. Eligibility service-type codes such as "UC" contain it.
    supports_repetition: bool = True

    def split_repeats(self, value: str) -> List[str]:
        """Split a repeating element, honouring the interchange version.

        Returns the value as a single-item list when the interchange predates
        repetition separators, rather than splitting on a non-delimiter.
        """
        if not value:
            return []
        if not self.supports_repetition:
            return [value]
        return value.split(self.repetition)


# The repetition separator arrived in X12 4030. ISA12 encodes the version as a
# 5-character code, NOT as the release number: 4010 is "00401", 4020 "00402",
# 4030 "00403", 5010 "00501". So the numeric threshold is 403, not 4030 —
# comparing against 4030 would reject every real interchange.
_REPETITION_MIN_VERSION = 403


def _supports_repetition(version: str, isa11: str) -> bool:
    """Decide whether ISA11 is a repetition separator for this interchange."""
    # Separators are punctuation by convention. An alphanumeric ISA11 is the
    # standards identifier ("U"), never a delimiter — this catches pre-4030
    # files even when ISA12 is malformed or missing.
    if isa11.isalnum():
        return False
    try:
        return int(version) >= _REPETITION_MIN_VERSION
    except ValueError:
        # Unparseable version, but ISA11 is punctuation: trust the byte.
        return True


def detect_delimiters(raw: str) -> Delimiters:
    """Derive delimiters from the fixed-position ISA segment.

    The ISA segment is exactly 106 characters:
      - element separator    = index 3
      - repetition separator = index 82 (ISA11) — 4030 and later only
      - version              = indexes 84-88 (ISA12)
      - component separator  = index 104 (ISA16)
      - segment terminator   = index 105
    Falls back to sensible defaults when there is no ISA header.
    """
    d = Delimiters()
    isa_pos = raw.find("ISA")
    if isa_pos != -1 and len(raw) >= isa_pos + 106:
        d.element = raw[isa_pos + 3]
        d.component = raw[isa_pos + 104]
        d.segment = raw[isa_pos + 105]

        isa11 = raw[isa_pos + 82]
        version = raw[isa_pos + 84 : isa_pos + 89].strip()
        if _supports_repetition(version, isa11):
            d.repetition = isa11
        else:
            d.supports_repetition = False
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
