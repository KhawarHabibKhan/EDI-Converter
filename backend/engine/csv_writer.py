"""Convert a mapper's dict output to CSV (tabular) text.

Dispatches on transaction type to produce a sensible flat, one-row-per-detail
layout (per service line, per payment, per member coverage, per benefit, per
status). Standard library only.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List


def _name(entity: Dict[str, Any] | None) -> str:
    if not entity:
        return ""
    last = entity.get("last_name_or_org") or entity.get("name") or ""
    first = entity.get("first_name") or ""
    return f"{last}, {first}" if first else last


def _rows_837(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for claim in data.get("claims", []):
        base = {
            "transaction": data.get("source_transaction"),
            "patient_account_no": claim.get("patient_account_no"),
            "total_charge": claim.get("total_charge"),
            "type_of_bill": claim.get("box_4_type_of_bill", ""),
            "insured": _name(claim.get("insured")),
            "payer": _name(claim.get("payer")),
            "billing_provider": _name(claim.get("providers", {}).get("billing")),
        }
        lines = claim.get("service_lines") or [{}]
        for ln in lines:
            rows.append({
                **base,
                "revenue_code": ln.get("box_42_revenue_code", ""),
                "procedure": ln.get("box_24d_procedure_code") or ln.get("box_44_hcpcs_procedure", ""),
                "charge": ln.get("box_24f_charges") or ln.get("box_47_line_charge", ""),
                "units": ln.get("box_24g_units") or ln.get("box_46_units", ""),
                "service_date": ln.get("box_24a_service_date") or ln.get("service_date", ""),
            })
    return rows


def _rows_835(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    payer = _name(data.get("payer"))
    payee = _name(data.get("payee"))
    for claim in data.get("claims", []):
        base = {
            "transaction": data.get("source_transaction"),
            "patient_control_number": claim.get("patient_control_number"),
            "claim_status_code": claim.get("claim_status_code"),
            "total_charge": claim.get("total_charge"),
            "total_paid": claim.get("total_paid"),
            "patient_responsibility": claim.get("patient_responsibility"),
            "payer": payer,
            "payee": payee,
        }
        svcs = claim.get("service_payments") or [{}]
        for svc in svcs:
            rows.append({
                **base,
                "procedure": svc.get("procedure_code", ""),
                "line_charge": svc.get("charge_amount", ""),
                "line_paid": svc.get("paid_amount", ""),
                "units": svc.get("units", ""),
            })
    return rows


def _rows_834(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for m in data.get("members", []):
        base = {
            "transaction": data.get("source_transaction"),
            "member": _name(m.get("member")),
            "subscriber_indicator": m.get("subscriber_indicator"),
            "maintenance_type": m.get("maintenance_type"),
            "benefit_status": m.get("benefit_status"),
        }
        covs = m.get("coverages") or [{}]
        for cov in covs:
            dates = cov.get("dates") or []
            rows.append({
                **base,
                "insurance_line": cov.get("insurance_line", ""),
                "plan": cov.get("plan_coverage_description", ""),
                "coverage_date": dates[0]["value"] if dates else "",
            })
    return rows


def _rows_eligibility(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for src in data.get("information_sources", []):
        payer = _name(src.get("payer"))
        for recv in src.get("information_receivers", []):
            provider = _name(recv.get("provider"))
            for sub in recv.get("subscribers", []):
                subscriber = _name(sub.get("info"))
                items = sub.get("eligibility") or sub.get("inquiries") or [{}]
                for e in items:
                    rows.append({
                        "transaction": data.get("source_transaction"),
                        "payer": payer,
                        "provider": provider,
                        "subscriber": subscriber,
                        "eligibility_code": e.get("eligibility_code", ""),
                        "eligibility": e.get("eligibility", ""),
                        "service_type_codes": "|".join(e.get("service_type_codes", [])),
                        "plan_description": e.get("plan_description", ""),
                    })
    return rows


def _rows_status(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for claim in data.get("claims", []):
        statuses = claim.get("statuses") or [{}]
        for st in statuses:
            rows.append({
                "transaction": data.get("source_transaction"),
                "trace_number": claim.get("trace_number"),
                "category_code": st.get("category_code", ""),
                "status_code": st.get("status_code", ""),
                "entity_code": st.get("entity_code", ""),
                "total_charge": st.get("total_charge", ""),
                "paid_amount": st.get("paid_amount", ""),
            })
    return rows


def _rows_generic(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{k: v for k, v in data.items() if not isinstance(v, (dict, list))}]


def _build_rows(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    src = str(data.get("source_transaction", ""))
    if "837" in src:
        return _rows_837(data)
    if "835" in src:
        return _rows_835(data)
    if "834" in src:
        return _rows_834(data)
    if "271" in src or "270" in src:
        return _rows_eligibility(data)
    if "277" in src or "276" in src:
        return _rows_status(data)
    return _rows_generic(data)


def to_csv(data: Dict[str, Any]) -> str:
    """Serialize a mapper's dict output to CSV text."""
    rows = _build_rows(data)
    if not rows:
        return ""
    # Column order = first-seen across all rows.
    columns: List[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buf.getvalue()
