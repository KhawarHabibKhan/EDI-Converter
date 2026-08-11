"""SNIP Level 3 — Balancing.

Pure arithmetic checks (exact ``Decimal``) that amounts reconcile:

* **837 (P/I):** claim total ``CLM02`` == Σ service-line charges
  (``SV1``-02 professional / ``SV2``-03 institutional).
* **835 service line:** ``SVC02`` (charge) == ``SVC03`` (paid) + Σ that line's
  ``CAS`` adjustment amounts.
* **835 claim (when service lines are present):** ``CLP03`` == Σ ``SVC02`` and
  ``CLP04`` == Σ ``SVC03``.
* **835 transaction:** ``BPR02`` (total actual provider payment) == Σ ``CLP04``
  − Σ ``PLB`` adjustment amounts. PLB amounts are **sign-aware**: the TR3 states
  the provider-level adjustment is *subtracted* from the sum of claim payments,
  so a negative PLB amount (money returned to the provider) increases BPR02.

No external data — arithmetic only. When an operand is missing/unparseable the
check is skipped (Level 2 already reports the missing/invalid element). Amounts
compare with exact ``Decimal`` equality. docx/v3/5-snip-rule-reference.md §5.3.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from engine.validation.issue import ERROR, make
from engine.x12_reader import EdiDocument, Segment


def check(doc: EdiDocument, txn_type: str) -> List[Dict[str, Any]]:
    if txn_type in ("837P", "837I", "837"):
        return _check_837(doc)
    if txn_type == "835":
        return _check_835(doc)
    return []


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _dec(raw: Any) -> Optional[Decimal]:
    s = (str(raw) if raw is not None else "").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _fmt(d: Decimal) -> str:
    return f"{d:f}"


def _cas_amount_sum(seg: Segment) -> Decimal:
    """Sum the adjustment amounts in a CAS segment (amounts at el 3, 6, 9, …)."""
    total = Decimal("0")
    idx = 3
    while idx <= len(seg.elements):
        amt = _dec(seg.el(idx))
        if amt is not None:
            total += amt
        idx += 3
    return total


def _plb_amount_sum(seg: Segment) -> Decimal:
    """Sum the adjustment amounts in a PLB segment.

    PLB carries up to six reason/amount pairs after the fiscal-period date:
    ``PLB03/04``, ``PLB05/06`` … ``PLB13/14`` — so the amounts sit at the even
    positions 4, 6, 8, 10, 12, 14. Amounts keep their sign.
    """
    total = Decimal("0")
    for idx in range(4, 15, 2):
        if idx > len(seg.elements):
            break
        amt = _dec(seg.el(idx))
        if amt is not None:
            total += amt
    return total


# --------------------------------------------------------------------------- #
#  837 — claim total vs service-line charges
# --------------------------------------------------------------------------- #
def _check_837(doc: EdiDocument) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    clm: Optional[Dict[str, Any]] = None

    def finalize(c: Optional[Dict[str, Any]]) -> None:
        if not c or not c["has_lines"] or c["total"] is None:
            return
        if c["total"] != c["lines"]:
            issues.append(make(
                ERROR, 3,
                f"CLM02 claim total {_fmt(c['total'])} does not equal the sum of "
                f"service-line charges {_fmt(c['lines'])}.",
                "CLM", c["pos"],
            ))

    for pos, s in enumerate(doc.segments, start=1):
        sid = s.seg_id
        if sid == "CLM":
            finalize(clm)
            clm = {"total": _dec(s.el(2)), "pos": pos, "lines": Decimal("0"), "has_lines": False}
        elif sid == "SV1" and clm is not None:      # professional charge = SV1-02
            amt = _dec(s.el(2))
            if amt is not None:
                clm["lines"] += amt
                clm["has_lines"] = True
        elif sid == "SV2" and clm is not None:      # institutional charge = SV2-03
            amt = _dec(s.el(3))
            if amt is not None:
                clm["lines"] += amt
                clm["has_lines"] = True

    finalize(clm)
    return issues


# --------------------------------------------------------------------------- #
#  835 — line and claim balancing
# --------------------------------------------------------------------------- #
def _check_835(doc: EdiDocument) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    claim: Optional[Dict[str, Any]] = None
    service: Optional[Dict[str, Any]] = None
    txn: Optional[Dict[str, Any]] = None

    def finalize_service(sv: Optional[Dict[str, Any]]) -> None:
        if not sv or sv["charge"] is None or sv["paid"] is None:
            return
        expected = sv["paid"] + sv["cas"]
        if sv["charge"] != expected:
            issues.append(make(
                ERROR, 3,
                f"SVC line: charge {_fmt(sv['charge'])} does not equal paid "
                f"{_fmt(sv['paid'])} + adjustments {_fmt(sv['cas'])} (= {_fmt(expected)}).",
                "SVC", sv["pos"],
            ))

    def finalize_claim(c: Optional[Dict[str, Any]]) -> None:
        if not c or not c["lines"]:
            return
        if c["charge"] is not None and c["charge"] != c["line_charge"]:
            issues.append(make(
                ERROR, 3,
                f"CLP03 claim charge {_fmt(c['charge'])} does not equal the sum of "
                f"service-line charges {_fmt(c['line_charge'])}.",
                "CLP", c["pos"],
            ))
        if c["paid"] is not None and c["paid"] != c["line_paid"]:
            issues.append(make(
                ERROR, 3,
                f"CLP04 claim payment {_fmt(c['paid'])} does not equal the sum of "
                f"service-line payments {_fmt(c['line_paid'])}.",
                "CLP", c["pos"],
            ))

    def finalize_txn(t: Optional[Dict[str, Any]]) -> None:
        """BPR02 == Σ CLP04 − Σ PLB amounts (the PLB total is subtracted)."""
        if not t or t["bpr"] is None or not t["claims"] or t["skip"]:
            return
        expected = t["clp"] - t["plb"]
        if t["bpr"] != expected:
            issues.append(make(
                ERROR, 3,
                f"BPR02 total payment {_fmt(t['bpr'])} does not equal the sum of claim "
                f"payments {_fmt(t['clp'])} minus provider-level adjustments "
                f"{_fmt(t['plb'])} (= {_fmt(expected)}).",
                "BPR", t["pos"],
            ))

    for pos, s in enumerate(doc.segments, start=1):
        sid = s.seg_id
        # --- transaction scope: BPR opens it, PLB and CLP04 feed it ---------- #
        if sid == "BPR":
            # One BPR per 835 transaction set — it opens a new balancing scope.
            finalize_txn(txn)
            txn = {"bpr": _dec(s.el(2)), "pos": pos, "clp": Decimal("0"),
                   "plb": Decimal("0"), "claims": 0, "skip": False}
        elif sid == "PLB" and txn is not None:
            txn["plb"] += _plb_amount_sum(s)
        elif sid == "CLP" and txn is not None:
            paid = _dec(s.el(4))
            if paid is None:
                txn["skip"] = True              # Level 2 already reports the bad element
            else:
                txn["clp"] += paid
            txn["claims"] += 1

        # --- claim and service-line scopes ----------------------------------- #
        if sid == "CLP":
            finalize_service(service)
            finalize_claim(claim)
            service = None
            claim = {
                "charge": _dec(s.el(3)), "paid": _dec(s.el(4)), "pos": pos,
                "lines": 0, "line_charge": Decimal("0"), "line_paid": Decimal("0"),
            }
        elif sid == "SVC" and claim is not None:
            finalize_service(service)
            service = {"charge": _dec(s.el(2)), "paid": _dec(s.el(3)), "pos": pos, "cas": Decimal("0")}
            claim["lines"] += 1
            if service["charge"] is not None:
                claim["line_charge"] += service["charge"]
            if service["paid"] is not None:
                claim["line_paid"] += service["paid"]
        elif sid == "CAS" and service is not None:
            service["cas"] += _cas_amount_sum(s)
        # CAS before the first SVC is claim-level; not used by the Σ-lines identity.

    finalize_service(service)
    finalize_claim(claim)
    finalize_txn(txn)
    return issues
