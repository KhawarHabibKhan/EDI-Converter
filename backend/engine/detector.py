"""Transaction-type detection.

Reads the ST segment (and, for 837, the implementation-guide version in ST03/
GS08) to decide which mapper should handle a file. Powers the "Auto-detect"
option in the UI.
"""

from __future__ import annotations

from engine import x12_reader
from engine.x12_reader import EdiDocument

# Human-readable names for messages / the UI.
TRANSACTION_NAMES = {
    "837P": "Health Care Claim: Professional",
    "837I": "Health Care Claim: Institutional",
    "835": "Health Care Claim Payment/Advice",
    "834": "Benefit Enrollment & Maintenance",
    "271": "Eligibility Benefit Response",
    "270": "Eligibility Benefit Inquiry",
    "277": "Health Care Claim Status Response",
    "276": "Health Care Claim Status Request",
}


class DetectionError(Exception):
    """Raised when no transaction type can be determined."""


def detect_from_doc(doc: EdiDocument) -> str:
    """Detect the transaction type from an already-parsed document."""
    st = doc.first("ST")
    if st is None or not st.el(1):
        raise DetectionError("No ST (transaction set header) segment found.")
    code = st.el(1).strip()

    if code == "837":
        # 837P uses implementation guide X222; 837I uses X223.
        version = st.el(3)
        if not version:
            gs = doc.first("GS")
            version = gs.el(8) if gs else ""
        return "837I" if "X223" in version.upper() else "837P"

    return code


def detect_transaction_type(raw: str) -> str:
    """Detect the transaction type from raw EDI text."""
    return detect_from_doc(x12_reader.parse(raw))
