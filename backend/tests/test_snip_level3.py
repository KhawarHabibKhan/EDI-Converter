"""Tests for SNIP Level 3 (Balancing) validation — v3.

Covers 837 claim-total-vs-lines and 835 line/claim payment math, cumulative
behavior, level gating, and the endpoint default.
"""

from fastapi.testclient import TestClient

from engine.validation import runner
from main import app

client = TestClient(app)


def _l3_errors(issues):
    return [i for i in issues if i["severity"] == "ERROR" and i["level"] == 3]


# --------------------------------------------------------------------------- #
#  Valid files balance
# --------------------------------------------------------------------------- #
def test_837p_balances(sample_837p):
    assert _l3_errors(runner.validate(sample_837p, 3)["issues"]) == []


def test_837i_balances(sample_837i):
    # Fixture corrected so CLM02 (750) == Σ SV2 line charges (250 + 500).
    assert _l3_errors(runner.validate(sample_837i, 3)["issues"]) == []


def test_835_balances(sample_835):
    assert _l3_errors(runner.validate(sample_835, 3)["issues"]) == []


# --------------------------------------------------------------------------- #
#  837 — claim total vs service lines
# --------------------------------------------------------------------------- #
def test_837p_claim_total_mismatch(sample_837p):
    broken = sample_837p.replace("SV1*HC:99213:25*150.00*UN*1***1~", "SV1*HC:99213:25*100.00*UN*1***1~")
    errs = _l3_errors(runner.validate(broken, 3)["issues"])
    assert any(e["segment"] == "CLM" and "does not equal the sum" in e["message"] for e in errs)


def test_837i_claim_total_mismatch(sample_837i):
    broken = sample_837i.replace("SV2*0300*HC:80053*250*UN*1~", "SV2*0300*HC:80053*200*UN*1~")
    errs = _l3_errors(runner.validate(broken, 3)["issues"])
    assert any(e["segment"] == "CLM" for e in errs)


# --------------------------------------------------------------------------- #
#  835 — line and claim payment math
# --------------------------------------------------------------------------- #
def test_835_service_line_imbalance(sample_835):
    # Change a line's paid amount so paid + adjustments != charge.
    broken = sample_835.replace("SVC*HC:99213*500*300**1~", "SVC*HC:99213*500*250**1~")
    errs = _l3_errors(runner.validate(broken, 3)["issues"])
    assert any(e["segment"] == "SVC" for e in errs)


def test_835_claim_charge_imbalance(sample_835):
    # Change the claim charge so it no longer equals the sum of line charges.
    broken = sample_835.replace("CLP*PATACCT001*1*800*500*250*", "CLP*PATACCT001*1*900*500*250*")
    errs = _l3_errors(runner.validate(broken, 3)["issues"])
    assert any(e["segment"] == "CLP" and "CLP03" in e["message"] for e in errs)


# --------------------------------------------------------------------------- #
#  Cumulative + gating
# --------------------------------------------------------------------------- #
def test_cumulative_includes_lower_levels(sample_837p):
    # Break the envelope (L1), a requirement (L2) and balancing (L3) at once.
    broken = (
        sample_837p
        .replace("SE*27*0001~", "SE*99*0001~")                                   # L1
        .replace("NM1*PR*2*ACME INSURANCE COMPANY*****PI*PAYER001~", "")          # L2
        .replace("SV1*HC:99213:25*150.00*UN*1***1~", "SV1*HC:99213:25*100.00*UN*1***1~")  # L3
    )
    issues = runner.validate(broken, 3)["issues"]
    levels = {i["level"] for i in issues if i["severity"] == "ERROR"}
    assert {1, 2, 3} <= levels


def test_level2_does_not_run_balancing(sample_837p):
    broken = sample_837p.replace("SV1*HC:99213:25*150.00*UN*1***1~", "SV1*HC:99213:25*100.00*UN*1***1~")
    res = runner.validate(broken, 2)
    assert res["snip_level"] == 2
    assert _l3_errors(res["issues"]) == []  # balancing is a Level-3 rule


# --------------------------------------------------------------------------- #
#  Endpoint
# --------------------------------------------------------------------------- #
def test_endpoint_default_runs_level3(sample_837p):
    broken = sample_837p.replace("SV1*HC:99213:25*150.00*UN*1***1~", "SV1*HC:99213:25*100.00*UN*1***1~")
    resp = client.post("/edi/validate", files={"file": ("s.edi", broken.encode("utf-8"), "text/plain")})
    body = resp.json()
    assert body["snip_level"] == 3
    assert any(i["level"] == 3 for i in body["issues"])
