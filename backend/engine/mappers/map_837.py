"""837 (Professional / Institutional) claim mapper.

Maps a tokenized 837 EDI document to a claim-shaped JSON structure. Professional
(837P) claims produce CMS-1500 (02/12) box names; Institutional (837I) claims
produce UB-04 box names (revenue codes, DRG, occurrence/value/condition codes,
type-of-bill, admission info).

Ported from the proven standalone parser and extended for institutional claims.
Exposes the standard mapper interface: ``to_json(doc) -> dict``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.x12_reader import Delimiters, EdiDocument, Segment

# --------------------------------------------------------------------------- #
#  Reference maps (common X12 code -> human-readable value)
# --------------------------------------------------------------------------- #
ENTITY_IDENTIFIER = {
    "85": "Billing Provider",
    "87": "Pay-To Provider",
    "IL": "Insured / Subscriber",
    "QC": "Patient",
    "PR": "Payer",
    "DN": "Referring Provider",
    "82": "Rendering Provider",
    "71": "Attending Provider",
    "72": "Operating Provider",
    "73": "Other Operating Provider",
    "77": "Service Facility Location",
    "DK": "Ordering Provider",
    "DQ": "Supervising Provider",
}

GENDER = {"M": "Male", "F": "Female", "U": "Unknown"}

# HI code-list qualifiers grouped by meaning.
DIAG_QUALIFIERS = {
    "ABK": "ICD-10 Principal Diagnosis",
    "ABF": "ICD-10 Other Diagnosis",
    "ABJ": "ICD-10 Admitting Diagnosis",
    "APR": "Patient Reason for Visit",
    "ABN": "External Cause of Injury",
    "BK": "ICD-9 Principal Diagnosis",
    "BF": "ICD-9 Other Diagnosis",
}
PROC_QUALIFIERS = {
    "BBR": "ICD-10 Principal Procedure",
    "BBQ": "ICD-10 Other Procedure",
    "BR": "ICD-9 Principal Procedure",
    "BQ": "ICD-9 Other Procedure",
}
ADMISSION_TYPE = {
    "1": "Emergency", "2": "Urgent", "3": "Elective",
    "4": "Newborn", "5": "Trauma", "9": "Information Not Available",
}


def _parse_name(seg: Segment) -> Dict[str, Any]:
    entity_code = seg.el(1)
    entity_type = seg.el(2)  # 1 = person, 2 = non-person
    return {
        "entity_role_code": entity_code,
        "entity_role": ENTITY_IDENTIFIER.get(entity_code, entity_code),
        "entity_type": "Organization" if entity_type == "2" else "Person",
        "last_name_or_org": seg.el(3),
        "first_name": seg.el(4),
        "middle_name": seg.el(5),
        "suffix": seg.el(7),
        "id_qualifier": seg.el(8),
        "id": seg.el(9),
    }


def _fmt_date(raw: str) -> str:
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def _fmt_dtp(raw: str) -> str:
    """Format a DTP date value: D8 (single), RD8 (range), or DT (date-time)."""
    if "-" in raw and len(raw) == 17:  # RD8: CCYYMMDD-CCYYMMDD
        start, end = raw.split("-")
        return f"{_fmt_date(start)}/{_fmt_date(end)}"
    if len(raw) == 12 and raw.isdigit():  # DT: CCYYMMDDHHMM
        return f"{_fmt_date(raw[:8])} {raw[8:10]}:{raw[10:12]}"
    return _fmt_date(raw)


def _ptr_letter(index: int) -> str:
    return chr(ord("A") + index) if 0 <= index < 12 else str(index + 1)


def to_json(doc: EdiDocument) -> Dict[str, Any]:
    """Convert a tokenized 837 document into a claim-shaped dict."""
    return _Parser(doc.segments, doc.delim).parse()


class _Parser:
    """Loop-based 837 parser. Tracks the current NM1 entity and attaches
    following N3/N4/DMG/REF to it. HL-level entities (subscriber/patient/payer/
    billing) are held as context and copied onto each CLM.
    """

    def __init__(self, segments: List[Segment], delim: Delimiters):
        self.segments = segments
        self.delim = delim
        self.institutional = self._is_institutional(segments)

    @staticmethod
    def _is_institutional(segments: List[Segment]) -> bool:
        """837I uses implementation guide X223; 837P uses X222."""
        for s in segments:
            if s.seg_id == "GS" and "X223" in s.el(8).upper():
                return True
            if s.seg_id == "ST" and "X223" in s.el(3).upper():
                return True
        return False

    def parse(self) -> Dict[str, Any]:
        claims: List[Dict[str, Any]] = []
        header: Dict[str, Any] = {}

        current_claim: Optional[Dict[str, Any]] = None
        current_entity: Optional[Dict[str, Any]] = None
        current_service: Optional[Dict[str, Any]] = None

        context: Dict[str, Any] = {}
        context_sbr: Dict[str, Any] = {}

        for seg in self.segments:
            sid = seg.seg_id

            if sid == "ISA":
                header["interchange"] = {
                    "sender_id": seg.el(6).strip(),
                    "receiver_id": seg.el(8).strip(),
                    "date": seg.el(9),
                    "time": seg.el(10),
                    "control_number": seg.el(13),
                    "usage": "Production" if seg.el(15) == "P" else "Test",
                }
            elif sid == "GS":
                header["functional_group"] = {
                    "sender_code": seg.el(2),
                    "receiver_code": seg.el(3),
                    "date": _fmt_date(seg.el(4)),
                    "time": seg.el(5),
                    "control_number": seg.el(6),
                    "version": seg.el(8),
                }
            elif sid == "BHT":
                header["transaction"] = {
                    "hierarchical_structure": seg.el(1),
                    "purpose_code": seg.el(2),
                    "reference_id": seg.el(3),
                    "date": _fmt_date(seg.el(4)),
                    "time": seg.el(5),
                    "claim_type": seg.el(6),
                }

            # --- Claim start ---------------------------------------------- #
            elif sid == "CLM":
                current_claim = self._new_claim()
                current_claim["insured"] = context.get("insured", {})
                current_claim["patient"] = context.get("patient", context.get("insured", {}))
                current_claim["payer"] = context.get("payer", {})
                if "billing" in context:
                    current_claim["providers"]["billing"] = context["billing"]
                if "service_facility" in context:
                    current_claim["providers"]["service_facility"] = context["service_facility"]
                current_claim.update(context_sbr)
                current_claim["patient_account_no"] = seg.el(1)
                current_claim["total_charge"] = seg.el(2)
                facility_code = seg.comp(5, 1, self.delim)
                frequency = seg.comp(5, 3, self.delim)
                current_claim["claim_frequency_code"] = frequency
                if self.institutional:
                    current_claim["facility_type_code"] = facility_code
                    current_claim["box_4_type_of_bill"] = f"{facility_code}{frequency}"
                else:
                    current_claim["place_of_service_code"] = facility_code
                current_claim["accept_assignment"] = seg.el(7)
                current_claim["patient_signature"] = seg.el(9)
                current_claim["insured_signature"] = seg.el(10)
                claims.append(current_claim)
                current_entity = None
                current_service = None

            # --- Institutional claim codes (CL1) -------------------------- #
            elif sid == "CL1" and current_claim is not None:
                current_claim["admission"] = {
                    "admission_type_code": seg.el(1),
                    "admission_type": ADMISSION_TYPE.get(seg.el(1), seg.el(1)),
                    "admission_source_code": seg.el(2),
                    "patient_status_code": seg.el(3),
                }

            # --- Name loops ----------------------------------------------- #
            elif sid == "NM1":
                entity = _parse_name(seg)
                current_entity = entity
                self._attach_entity(header, current_claim, context, entity)

            elif sid == "N3" and current_entity is not None:
                current_entity["address_1"] = seg.el(1)
                if seg.el(2):
                    current_entity["address_2"] = seg.el(2)
            elif sid == "N4" and current_entity is not None:
                current_entity["city"] = seg.el(1)
                current_entity["state"] = seg.el(2)
                current_entity["postal_code"] = seg.el(3)

            elif sid == "DMG" and current_entity is not None:
                current_entity["date_of_birth"] = _fmt_date(seg.el(2))
                current_entity["gender"] = GENDER.get(seg.el(3), seg.el(3))

            elif sid == "REF" and current_entity is not None:
                current_entity.setdefault("references", []).append(
                    {"qualifier": seg.el(1), "value": seg.el(2)}
                )

            # --- Subscriber / payer info ---------------------------------- #
            elif sid == "SBR":
                sbr_fields = {
                    "payer_responsibility": seg.el(1),
                    "group_number": seg.el(3),
                    "group_name": seg.el(4),
                    "insurance_type_code": seg.el(9),
                }
                context_sbr = sbr_fields
                if current_claim is not None:
                    current_claim.update(sbr_fields)

            # --- HI (diagnoses / procedures / institutional codes) -------- #
            elif sid == "HI" and current_claim is not None:
                for idx in range(1, len(seg.elements) + 1):
                    composite = seg.el(idx)
                    if composite:
                        self._route_hi(current_claim, composite)

            # --- Service lines -------------------------------------------- #
            elif sid == "LX":
                current_service = None
            elif sid == "SV1" and current_claim is not None:  # professional
                current_service = {
                    "box_24d_procedure_code": seg.comp(1, 2, self.delim),
                    "box_24d_modifiers": [m for m in (seg.comp(1, i, self.delim) for i in range(3, 7)) if m],
                    "box_24f_charges": seg.el(2),
                    "units_qualifier": seg.el(3),
                    "box_24g_units": seg.el(4),
                    "box_24e_diagnosis_pointers": (
                        seg.el(7).split(self.delim.component) if seg.el(7) else []
                    ),
                }
                current_claim["service_lines"].append(current_service)
            elif sid == "SV2" and current_claim is not None:  # institutional
                current_service = {
                    "box_42_revenue_code": seg.el(1),
                    "box_44_hcpcs_procedure": seg.comp(2, 2, self.delim),
                    "box_44_modifiers": [m for m in (seg.comp(2, i, self.delim) for i in range(3, 7)) if m],
                    "box_47_line_charge": seg.el(3),
                    "units_qualifier": seg.el(4),
                    "box_46_units": seg.el(5),
                }
                current_claim["service_lines"].append(current_service)
            elif sid == "DTP" and current_service is not None and seg.el(1) == "472":
                key = "service_date" if self.institutional else "box_24a_service_date"
                current_service[key] = _fmt_dtp(seg.el(3))
            elif sid == "DTP" and current_claim is not None:
                self._route_claim_date(current_claim, seg)

        return {
            "form": "UB-04 (837I)" if self.institutional else "CMS-1500 (02/12)",
            "source_transaction": "ANSI X12 837I" if self.institutional else "ANSI X12 837P",
            "header": header,
            "claims": claims,
            "claim_count": len(claims),
        }

    # ----- HI / DTP routing ------------------------------------------------ #
    def _route_hi(self, claim: Dict[str, Any], composite: str) -> None:
        parts = composite.split(self.delim.component)
        qualifier = parts[0] if parts else ""
        code = parts[1] if len(parts) > 1 else ""
        if not code:
            return

        if qualifier in DIAG_QUALIFIERS:
            diags = claim["box_21_diagnoses"]
            diags.append({
                "qualifier": qualifier,
                "qualifier_desc": DIAG_QUALIFIERS[qualifier],
                "code": code,
                "pointer": _ptr_letter(len(diags)),
            })
        elif qualifier in PROC_QUALIFIERS:
            claim.setdefault("procedures", []).append({
                "qualifier": qualifier,
                "qualifier_desc": PROC_QUALIFIERS[qualifier],
                "code": code,
                "date": _fmt_dtp(parts[3]) if len(parts) > 3 and parts[3] else "",
            })
        elif qualifier == "DR":
            claim["drg"] = {"code": code}
        elif qualifier == "BH":  # occurrence information: code : D8 : date
            claim.setdefault("occurrence_codes", []).append({
                "code": code,
                "date": _fmt_dtp(parts[3]) if len(parts) > 3 and parts[3] else "",
            })
        elif qualifier == "BI":  # occurrence span: code : RD8 : range
            claim.setdefault("occurrence_span_codes", []).append({
                "code": code,
                "dates": _fmt_dtp(parts[3]) if len(parts) > 3 and parts[3] else "",
            })
        elif qualifier == "BE":  # value information: code : : : amount
            claim.setdefault("value_codes", []).append({
                "code": code,
                "amount": parts[4] if len(parts) > 4 else "",
            })
        elif qualifier == "BG":  # condition information
            claim.setdefault("condition_codes", []).append({"code": code})
        else:
            # Unknown qualifier — keep it visible rather than dropping it.
            claim.setdefault("other_hi_codes", []).append(
                {"qualifier": qualifier, "code": code}
            )

    def _route_claim_date(self, claim: Dict[str, Any], seg: Segment) -> None:
        qualifier = seg.el(1)
        value = _fmt_dtp(seg.el(3))
        if qualifier == "434":
            claim["statement_dates"] = value
        elif qualifier == "435":
            claim["admission_date"] = value
        elif qualifier == "096":
            claim["discharge_hour"] = value
        else:
            claim.setdefault("dates", []).append({
                "qualifier": qualifier, "format": seg.el(2), "value": value,
            })

    # ----- helpers --------------------------------------------------------- #
    @staticmethod
    def _new_claim() -> Dict[str, Any]:
        return {
            "box_21_diagnoses": [],
            "service_lines": [],
            "providers": {},
            "insured": {},
            "patient": {},
            "payer": {},
        }

    @staticmethod
    def _attach_entity(header: Dict[str, Any],
                       claim: Optional[Dict[str, Any]],
                       context: Dict[str, Any],
                       entity: Dict[str, Any]) -> None:
        role = entity["entity_role_code"]

        context_slot = {
            "IL": "insured",
            "QC": "patient",
            "PR": "payer",
            "85": "billing",
            "87": "billing",
        }.get(role)
        if context_slot:
            context[context_slot] = entity
            if claim is not None:
                if context_slot in ("insured", "patient", "payer"):
                    claim[context_slot] = entity
                else:
                    claim["providers"]["billing"] = entity
            return

        if claim is None:
            header.setdefault("entities", []).append(entity)
            return

        provider_slot = {
            "82": "rendering",
            "71": "attending",
            "72": "operating",
            "73": "other_operating",
            "77": "service_facility",
            "DN": "referring",
            "P3": "referring",
        }.get(role)
        if provider_slot:
            claim["providers"][provider_slot] = entity
        else:
            claim.setdefault("other_entities", []).append(entity)
