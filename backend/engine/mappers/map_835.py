"""835 (Health Care Claim Payment / Advice) mapper — remittance / ERA.

Maps payer/payee, per-claim payments (CLP), service payments (SVC), claim &
service adjustments (CAS), and provider-level adjustments (PLB).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.mappers import _common as C
from engine.x12_reader import Delimiters, EdiDocument, Segment

PAYMENT_METHOD = {"ACH": "ACH", "CHK": "Check", "FWT": "Wire", "NON": "No payment"}
CREDIT_DEBIT = {"C": "Credit", "D": "Debit"}
ADJ_GROUP = {
    "CO": "Contractual Obligation",
    "PR": "Patient Responsibility",
    "OA": "Other Adjustment",
    "PI": "Payer Initiated Reduction",
    "CR": "Correction & Reversal",
}


def _adjustments(seg: Segment) -> List[Dict[str, Any]]:
    """CAS: group code + up to 6 (reason, amount, quantity) triplets."""
    group = seg.el(1)
    out: List[Dict[str, Any]] = []
    idx = 2
    while idx <= len(seg.elements):
        reason = seg.el(idx)
        if reason:
            out.append({
                "group_code": group,
                "group": ADJ_GROUP.get(group, group),
                "reason_code": reason,
                "amount": seg.el(idx + 1),
                "quantity": seg.el(idx + 2),
            })
        idx += 3
    return out


def to_json(doc: EdiDocument) -> Dict[str, Any]:
    delim: Delimiters = doc.delim
    header: Dict[str, Any] = {}
    payer: Dict[str, Any] = {}
    payee: Dict[str, Any] = {}
    claims: List[Dict[str, Any]] = []
    provider_adjustments: List[Dict[str, Any]] = []

    current_n1: Optional[Dict[str, Any]] = None
    current_claim: Optional[Dict[str, Any]] = None
    current_service: Optional[Dict[str, Any]] = None

    for seg in doc.segments:
        sid = seg.seg_id

        if sid == "ISA":
            header["interchange"] = {
                "sender_id": seg.el(6).strip(),
                "receiver_id": seg.el(8).strip(),
                "control_number": seg.el(13),
                "usage": "Production" if seg.el(15) == "P" else "Test",
            }
        elif sid == "GS":
            header["functional_group"] = {"version": seg.el(8)}
        elif sid == "BPR":
            header["payment"] = {
                "transaction_handling_code": seg.el(1),
                "total_paid_amount": seg.el(2),
                "credit_debit": CREDIT_DEBIT.get(seg.el(3), seg.el(3)),
                "payment_method_code": seg.el(4),
                "payment_method": PAYMENT_METHOD.get(seg.el(4), seg.el(4)),
                "payment_date": C.fmt_date(seg.el(16)),
            }
        elif sid == "TRN":
            header.setdefault("payment", {})
            header["payment"]["trace_number"] = seg.el(2)
            header["payment"]["payer_identifier"] = seg.el(3)
        elif sid == "DTM" and current_claim is None:
            header.setdefault("dates", []).append(
                {"qualifier": seg.el(1), "value": C.fmt_dtp(seg.el(2))}
            )

        # --- Payer / payee (N1 loops) --------------------------------- #
        elif sid == "N1":
            entity = {
                "entity_role_code": seg.el(1),
                "entity_role": C.ENTITY_IDENTIFIER.get(seg.el(1), seg.el(1)),
                "name": seg.el(2),
                "id_qualifier": seg.el(3),
                "id": seg.el(4),
            }
            current_n1 = entity
            if seg.el(1) == "PR":
                payer.update(entity)
            elif seg.el(1) == "PE":
                payee.update(entity)
        elif sid == "N3" and current_n1 is not None:
            current_n1["address_1"] = seg.el(1)
        elif sid == "N4" and current_n1 is not None:
            current_n1["city"] = seg.el(1)
            current_n1["state"] = seg.el(2)
            current_n1["postal_code"] = seg.el(3)

        # --- Claim payment (CLP) -------------------------------------- #
        elif sid == "CLP":
            current_claim = {
                "patient_control_number": seg.el(1),
                "claim_status_code": seg.el(2),
                "total_charge": seg.el(3),
                "total_paid": seg.el(4),
                "patient_responsibility": seg.el(5),
                "claim_filing_indicator": seg.el(6),
                "payer_claim_control_number": seg.el(7),
                "adjustments": [],
                "service_payments": [],
            }
            claims.append(current_claim)
            current_service = None
        elif sid == "NM1" and current_claim is not None:
            role = seg.el(1)
            person = C.parse_name(seg)
            if role == "QC":
                current_claim["patient"] = person
            elif role == "IL":
                current_claim["insured"] = person
            else:
                current_claim.setdefault("other_entities", []).append(person)

        # --- Service payment (SVC) ------------------------------------ #
        elif sid == "SVC" and current_claim is not None:
            current_service = {
                "procedure_code": seg.comp(1, 2, delim),
                "charge_amount": seg.el(2),
                "paid_amount": seg.el(3),
                "revenue_code": seg.el(4),
                "units": seg.el(5),
                "adjustments": [],
            }
            current_claim["service_payments"].append(current_service)
        elif sid == "DTM" and current_service is not None:
            current_service.setdefault("dates", []).append(
                {"qualifier": seg.el(1), "value": C.fmt_dtp(seg.el(2))}
            )
        elif sid == "AMT" and current_service is not None:
            current_service.setdefault("amounts", []).append(
                {"qualifier": seg.el(1), "amount": seg.el(2)}
            )

        # --- Adjustments (CAS) ---------------------------------------- #
        elif sid == "CAS":
            adjustments = _adjustments(seg)
            if current_service is not None:
                current_service["adjustments"].extend(adjustments)
            elif current_claim is not None:
                current_claim["adjustments"].extend(adjustments)

        # --- Provider-level adjustment (PLB) -------------------------- #
        elif sid == "PLB":
            provider_adjustments.append({
                "provider_id": seg.el(1),
                "fiscal_period_date": C.fmt_date(seg.el(2)),
                "adjustment_reason": seg.comp(3, 1, delim),
                "amount": seg.el(4),
            })

    return {
        "form": "835 Remittance Advice",
        "source_transaction": "ANSI X12 835",
        "header": header,
        "payer": payer,
        "payee": payee,
        "claims": claims,
        "claim_count": len(claims),
        "provider_adjustments": provider_adjustments,
    }
