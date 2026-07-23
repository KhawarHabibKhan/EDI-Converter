"""Tests for SNIP Level 4 (Situational) validation — v3.

Covers 837 accident / COB / admission dependencies, 834 coverage begin dates,
cumulative behavior, level gating, and the endpoint default.
"""

import pytest
from fastapi.testclient import TestClient

from engine.validation import runner
from main import app

client = TestClient(app)


def _l4(raw, level=4):
    return [i for i in runner.validate(raw, level)["issues"] if i["severity"] == "ERROR" and i["level"] == 4]


# --------------------------------------------------------------------------- #
#  Valid files have no situational violations
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fixture", [
    "sample_837p", "sample_837i", "sample_835", "sample_834",
    "sample_270", "sample_271", "sample_277",
])
def test_valid_files_pass_level4(request, fixture):
    raw = request.getfixturevalue(fixture)
    assert _l4(raw) == []


# --------------------------------------------------------------------------- #
#  837 — accident / COB / admission
# --------------------------------------------------------------------------- #
def test_accident_requires_accident_date(sample_837p):
    # Add CLM11 (related-causes = auto accident) but no DTP*439.
    broken = sample_837p.replace(
        "CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y~",
        "CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y**AA~",
    )
    errs = _l4(broken)
    assert any("accident" in e["message"].lower() and "DTP*439" in e["message"] for e in errs)


def test_accident_with_date_is_clean(sample_837p):
    ok = sample_837p.replace(
        "CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y~",
        "CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y**AA~DTP*439*D8*20240108~",
    )
    assert not any("accident" in e["message"].lower() for e in _l4(ok))


def test_non_primary_payer_requires_other_payer_loop(sample_837p):
    broken = sample_837p.replace("SBR*P*18*GRP1001*ACME PPO****CI~", "SBR*S*18*GRP1001*ACME PPO****CI~")
    errs = _l4(broken)
    assert any("non-primary" in e["message"] and e["segment"] == "SBR" for e in errs)


def test_institutional_admission_requires_admission_date(sample_837i):
    broken = sample_837i.replace("DTP*435*DT*202401101430~\n", "").replace("DTP*435*DT*202401101430~", "")
    errs = _l4(broken)
    assert any("admission" in e["message"].lower() and "DTP*435" in e["message"] for e in errs)


# --------------------------------------------------------------------------- #
#  834 — coverage begin date
# --------------------------------------------------------------------------- #
def test_coverage_requires_begin_date(sample_834):
    # Drop the DTP*348 that follows the first HD.
    broken = sample_834.replace(
        "HD*021**HLT*GOLD PLAN~\nDTP*348*D8*20240101~\nHD*021**DEN",
        "HD*021**HLT*GOLD PLAN~\nHD*021**DEN",
        1,
    )
    errs = _l4(broken)
    assert any(e["segment"] == "HD" and "DTP*348" in e["message"] for e in errs)


# --------------------------------------------------------------------------- #
#  Cumulative + gating + endpoint
# --------------------------------------------------------------------------- #
def test_level3_does_not_run_situational(sample_837p):
    broken = sample_837p.replace(
        "CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y~",
        "CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y**AA~",
    )
    res = runner.validate(broken, 3)
    assert res["snip_level"] == 3
    assert not [i for i in res["issues"] if i["level"] == 4]


def test_cumulative_all_levels(sample_837p):
    broken = (
        sample_837p
        .replace("SE*27*0001~", "SE*99*0001~")                                              # L1
        .replace("NM1*PR*2*ACME INSURANCE COMPANY*****PI*PAYER001~", "")                     # L2
        .replace("SV1*HC:99213:25*150.00*UN*1***1~", "SV1*HC:99213:25*100.00*UN*1***1~")     # L3
        .replace("CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y~", "CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y**AA~")  # L4
    )
    levels = {i["level"] for i in runner.validate(broken, 4)["issues"] if i["severity"] == "ERROR"}
    assert {1, 2, 3, 4} <= levels


def test_endpoint_default_runs_level4(sample_837p):
    from engine.validation import HIGHEST_LEVEL

    broken = sample_837p.replace(
        "CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y~",
        "CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y**AA~",
    )
    resp = client.post("/edi/validate", files={"file": ("s.edi", broken.encode("utf-8"), "text/plain")})
    body = resp.json()
    assert body["snip_level"] == HIGHEST_LEVEL
    assert any(i["level"] == 4 for i in body["issues"])
