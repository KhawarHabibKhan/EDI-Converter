"""Tests for SNIP Level 2 (Requirement) validation — v3.

Covers the runner, per-transaction-type requirement rules, cumulative behavior
with Level 1, the `?snip_level=` endpoint, and Level-1 back-compat.
"""

import pytest
from fastapi.testclient import TestClient

from engine.validation import runner
from main import app

client = TestClient(app)

ALL = [
    ("sample_837p", "837P"), ("sample_837i", "837I"), ("sample_835", "835"),
    ("sample_834", "834"), ("sample_270", "270"), ("sample_271", "271"),
    ("sample_277", "277"),
]


def _errors(issues, level=None):
    return [i for i in issues if i["severity"] == "ERROR" and (level is None or i["level"] == level)]


# --------------------------------------------------------------------------- #
#  Clean valid files pass Level 2
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fixture,code", ALL)
def test_valid_files_pass_level2(request, fixture, code):
    raw = request.getfixturevalue(fixture)
    res = runner.validate(raw, 2)
    assert res["transaction_type"] == code
    assert res["snip_level"] == 2
    assert _errors(res["issues"]) == [], f"{code}: {[e['message'] for e in _errors(res['issues'])]}"


def test_every_issue_is_labeled_with_a_level(sample_837p):
    # Even clean files: any warnings carry a level; broken ones too.
    res = runner.validate(sample_837p, 2)
    assert all("level" in i and i["level"] in (1, 2) for i in res["issues"])


# --------------------------------------------------------------------------- #
#  Requirement rules fire on missing segments/elements
# --------------------------------------------------------------------------- #
def test_837p_missing_service_line(sample_837p):
    broken = sample_837p.replace("SV1*HC:99213:25*150.00*UN*1***1~", "").replace(
        "SV1*HC:71046*200.00*UN*1***1~", ""
    )
    errs = _errors(runner.validate(broken, 2)["issues"], level=2)
    assert any("SV1" in e["segment"] for e in errs)


def test_837p_missing_billing_provider(sample_837p):
    broken = sample_837p.replace("NM1*85*2*DOCTORS EXPRESS CLINIC*****XX*1234567890~", "")
    msgs = " ".join(e["message"] for e in _errors(runner.validate(broken, 2)["issues"], level=2))
    assert "NM1*85" in msgs


def test_837p_bad_claim_amount_datatype(sample_837p):
    broken = sample_837p.replace("CLM*PATACCT001*350.00", "CLM*PATACCT001*ABC")
    msgs = " ".join(e["message"] for e in _errors(runner.validate(broken, 2)["issues"], level=2))
    assert "CLM02" in msgs and "not a valid amount" in msgs


def test_835_missing_payee(sample_835):
    broken = sample_835.replace("N1*PE*GENERAL HOSPITAL*XX*1234567893~", "")
    msgs = " ".join(e["message"] for e in _errors(runner.validate(broken, 2)["issues"], level=2))
    assert "N1*PE" in msgs


def test_834_missing_sponsor(sample_834):
    broken = sample_834.replace("N1*P5*ACME EMPLOYER*FI*590000000~", "")
    msgs = " ".join(e["message"] for e in _errors(runner.validate(broken, 2)["issues"], level=2))
    assert "N1*P5" in msgs


def test_270_missing_inquiry(sample_270):
    broken = sample_270.replace("EQ*30~", "")
    msgs = " ".join(e["message"] for e in _errors(runner.validate(broken, 2)["issues"], level=2))
    assert "EQ" in msgs


def test_277_missing_status(sample_277):
    broken = sample_277.replace("STC*A2:20:PR*20240112**800*300~", "").replace(
        "STC*A2:20:PR*20240112**500*200~", ""
    )
    msgs = " ".join(e["message"] for e in _errors(runner.validate(broken, 2)["issues"], level=2))
    assert "STC" in msgs


# --------------------------------------------------------------------------- #
#  Cumulative + level gating
# --------------------------------------------------------------------------- #
def test_cumulative_includes_level1(sample_837p):
    # Break both an envelope count (L1) and a requirement (L2).
    broken = sample_837p.replace("SE*27*0001~", "SE*99*0001~").replace(
        "NM1*PR*2*ACME INSURANCE COMPANY*****PI*PAYER001~", ""
    )
    issues = runner.validate(broken, 2)["issues"]
    assert _errors(issues, level=1), "expected a Level-1 envelope error"
    assert _errors(issues, level=2), "expected a Level-2 requirement error"


def test_level1_only_skips_requirement_rules(sample_837p):
    broken = sample_837p.replace("NM1*85*2*DOCTORS EXPRESS CLINIC*****XX*1234567890~", "")
    # At level 1, the missing billing provider (a Level-2 rule) is NOT reported.
    res = runner.validate(broken, 1)
    assert res["snip_level"] == 1
    assert not _errors(res["issues"], level=2)


# --------------------------------------------------------------------------- #
#  Endpoint
# --------------------------------------------------------------------------- #
def test_endpoint_default_is_highest_and_labels(sample_837p):
    from engine.validation import HIGHEST_LEVEL

    resp = client.post("/edi/validate", files={"file": ("s.edi", sample_837p.encode("utf-8"), "text/plain")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["snip_level"] == HIGHEST_LEVEL  # default = highest implemented
    assert body["transaction_type"] == "837P"
    assert body["valid"] is True


def test_endpoint_level1_param(sample_837p):
    broken = sample_837p.replace("NM1*85*2*DOCTORS EXPRESS CLINIC*****XX*1234567890~", "")
    resp = client.post(
        "/edi/validate?snip_level=1",
        files={"file": ("s.edi", broken.encode("utf-8"), "text/plain")},
    )
    body = resp.json()
    assert body["snip_level"] == 1
    # Level-2 requirement issue is not surfaced at level 1.
    assert all(i["level"] == 1 for i in body["issues"])


def test_endpoint_rejects_out_of_range_level(sample_837p):
    resp = client.post(
        "/edi/validate?snip_level=9",
        files={"file": ("s.edi", sample_837p.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 422  # FastAPI query validation (le=HIGHEST_LEVEL)
