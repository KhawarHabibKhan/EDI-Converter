"""SNIP Level 5 — Code sets.

Membership validation of coded elements against the bundled, free code sets in
``validation/codesets/``: ICD-10-CM diagnoses, ICD-10-PCS inpatient procedures,
HCPCS Level II procedures, and Place of Service. An unknown code → ``ERROR``
labeled ``5``. Only 837 (P/I) carries these coded elements in v3 scope; other
transaction types have no Level-5 rules yet.

**CPT is gated.** Procedure codes in the CPT range (5-digit numeric) are
AMA-licensed, so they are **format-checked only** and never membership-validated.
When any CPT-range code is seen, the report adds one ``INFO`` note. Setting
``CPT_MEMBERSHIP = True`` (once AMA licensing is approved and a ``cpt`` set is
bundled) turns on real CPT membership — no other change needed. See
docx/v3/3-snip-rules.md §3.6 and docx/v3/5-snip-rule-reference.md §5.5.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from engine.validation import codesets
from engine.validation.issue import ERROR, INFO, make
from engine.x12_reader import EdiDocument, Segment

# HI diagnosis qualifiers that carry ICD-10-CM codes (ICD-9 BK/BF/… not checked).
_ICD10CM_DX = {"ABK", "ABF", "ABJ", "APR", "ABN"}
# HI inpatient-procedure qualifiers that carry ICD-10-PCS codes (837I).
_ICD10PCS_PROC = {"BBR", "BBQ"}
# Procedure-composite qualifier that carries an HCPCS/CPT code.
_HCPCS_QUAL = "HC"

_HCPCS_II = re.compile(r"^[A-Z]\d{4}$")   # e.g. J1885, G0008 — HCPCS Level II
_CPT = re.compile(r"^\d{5}$")             # e.g. 99213 — AMA-licensed → gated

# Off until AMA CPT licensing is confirmed (docx/v3/3-snip-rules.md §3.6).
CPT_MEMBERSHIP = False


def check(doc: EdiDocument, txn_type: str) -> List[Dict[str, Any]]:
    if txn_type in ("837P", "837I", "837"):
        return _check_837(doc, institutional=(txn_type == "837I"))
    return []


def _parts(value: str, delim) -> List[str]:
    return (value or "").split(delim.component)


def _check_837(doc: EdiDocument, institutional: bool) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    delim = doc.delim
    cpt_count = 0

    for pos, s in enumerate(doc.segments, start=1):
        sid = s.seg_id

        if sid == "HI":
            issues += _check_hi(doc, s, pos)
        elif sid == "SV1":
            issues += _check_procedure(doc, s, pos, el_idx=1, seg_id="SV1")
            cpt_count += _cpt_hit(s, 1, delim)
        elif sid == "SV2":
            issues += _check_procedure(doc, s, pos, el_idx=2, seg_id="SV2")
            cpt_count += _cpt_hit(s, 2, delim)
        elif sid == "CLM" and not institutional:
            issues += _check_pos(doc, s, pos)

    if cpt_count:
        issues.append(make(
            INFO, 5,
            f"CPT membership not validated (AMA licensing pending); {cpt_count} "
            f"CPT-range procedure code(s) were format-checked only.",
            "SV1",
        ))
    return issues


def _check_hi(doc: EdiDocument, seg: Segment, pos: int) -> List[Dict[str, Any]]:
    """Validate each diagnosis/procedure composite in an HI segment."""
    issues: List[Dict[str, Any]] = []
    for i in range(1, len(seg.elements) + 1):
        p = _parts(seg.el(i), doc.delim)
        qual = (p[0] if p else "").strip().upper()
        code = (p[1] if len(p) > 1 else "").strip().upper()
        if not code:
            continue
        if qual in _ICD10CM_DX and not codesets.contains("icd10cm", code):
            issues.append(make(ERROR, 5, f"Diagnosis code '{code}' (HI {qual}) not found in ICD-10-CM.", "HI", pos))
        elif qual in _ICD10PCS_PROC and not codesets.contains("icd10pcs", code):
            issues.append(make(ERROR, 5, f"Procedure code '{code}' (HI {qual}) not found in ICD-10-PCS.", "HI", pos))
    return issues


def _check_procedure(doc: EdiDocument, seg: Segment, pos: int, el_idx: int, seg_id: str) -> List[Dict[str, Any]]:
    """Validate one SV1/SV2 procedure composite (qualifier ':' code [':' modifiers])."""
    p = _parts(seg.el(el_idx), doc.delim)
    qual = (p[0] if p else "").strip().upper()
    code = (p[1] if len(p) > 1 else "").strip().upper()
    if not code or qual != _HCPCS_QUAL:
        return []
    if _HCPCS_II.match(code):
        if not codesets.contains("hcpcs", code):
            return [make(ERROR, 5, f"Procedure code '{code}' ({seg_id}, HCPCS Level II) not found in HCPCS.", seg_id, pos)]
        return []
    if _CPT.match(code):
        if CPT_MEMBERSHIP and not codesets.contains("cpt", code):
            return [make(ERROR, 5, f"Procedure code '{code}' ({seg_id}, CPT) not found in CPT.", seg_id, pos)]
        return []  # gated: format-only, reported via the INFO note
    return []


def _check_pos(doc: EdiDocument, seg: Segment, pos: int) -> List[Dict[str, Any]]:
    """Validate the professional place-of-service code (CLM05-01)."""
    p = _parts(seg.el(5), doc.delim)
    code = (p[0] if p else "").strip().upper()
    if code and not codesets.contains("pos", code):
        return [make(ERROR, 5, f"Place-of-service code '{code}' (CLM05-01) not found in the Place of Service code set.", "CLM", pos)]
    return []


def _cpt_hit(seg: Segment, el_idx: int, delim) -> int:
    """1 if the segment's procedure composite carries a CPT-range code, else 0."""
    p = _parts(seg.el(el_idx), delim)
    qual = (p[0] if p else "").strip().upper()
    code = (p[1] if len(p) > 1 else "").strip().upper()
    return 1 if qual == _HCPCS_QUAL and _CPT.match(code) else 0
