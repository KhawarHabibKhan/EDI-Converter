"""Tests for SNIP Level 5 (Code sets) validation — v3.

Covers the codesets loader, ICD-10-CM / ICD-10-PCS / HCPCS membership, Place of
Service, the gated CPT format-only path, cumulative behavior, level gating, and
the endpoint default.
"""

import pytest
from fastapi.testclient import TestClient

from engine.validation import codesets, runner
from main import app

client = TestClient(app)


def _l5(raw, level=5):
    return [
        i for i in runner.validate(raw, level)["issues"]
        if i["severity"] == "ERROR" and i["level"] == 5
    ]


# --------------------------------------------------------------------------- #
#  codesets loader
# --------------------------------------------------------------------------- #
def test_codesets_membership():
    assert codesets.contains("pos", "11")
    assert not codesets.contains("pos", "00")
    assert codesets.contains("icd10cm", "J209")
    assert codesets.contains("icd10cm", "J20.9")          # dots normalized away
    assert not codesets.contains("icd10cm", "ZZ999")
    assert codesets.contains("icd10pcs", "0DTJ4ZZ")
    assert codesets.contains("hcpcs", "J1885")
    assert not codesets.contains("hcpcs", "Q9999")
    assert not codesets.contains("pos", "")               # empty is never a member


def test_codesets_all_sets_loaded():
    for name in ("icd10cm", "icd10pcs", "hcpcs", "pos"):
        assert codesets.available(name), f"{name} set is empty/missing"


# --------------------------------------------------------------------------- #
#  Clean fixtures pass Level 5
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fixture", ["sample_837p", "sample_837i"])
def test_valid_837_pass_level5(request, fixture):
    raw = request.getfixturevalue(fixture)
    assert _l5(raw) == [], [e["message"] for e in _l5(raw)]


def test_non_837_types_have_no_level5_rules(sample_835, sample_834):
    assert _l5(sample_835) == []
    assert _l5(sample_834) == []


# --------------------------------------------------------------------------- #
#  Membership failures fire
# --------------------------------------------------------------------------- #
def test_unknown_diagnosis_flagged(sample_837p):
    broken = sample_837p.replace("HI*ABK:J209*ABF:R05~", "HI*ABK:ZZ999*ABF:R05~")
    assert any("ZZ999" in e["message"] and "ICD-10-CM" in e["message"] for e in _l5(broken))


def test_unknown_pcs_procedure_flagged(sample_837i):
    broken = sample_837i.replace("HI*BBR:0DTJ4ZZ:D8:20240111~", "HI*BBR:9XXXXXX:D8:20240111~")
    assert any("ICD-10-PCS" in e["message"] for e in _l5(broken))


def test_unknown_pos_flagged(sample_837p):
    broken = sample_837p.replace(
        "CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y~",
        "CLM*PATACCT001*350.00***00:B:1*Y*A*Y*Y~",
    )
    assert any("Place-of-service" in e["message"] and "'00'" in e["message"] for e in _l5(broken))


def test_unknown_hcpcs_flagged(sample_837p):
    broken = sample_837p.replace("SV1*HC:99213:25*150.00*UN*1***1~", "SV1*HC:Q9999*150.00*UN*1***1~")
    assert any("Q9999" in e["message"] and "HCPCS" in e["message"] for e in _l5(broken))


def test_valid_hcpcs_passes(sample_837p):
    ok = sample_837p.replace("SV1*HC:99213:25*150.00*UN*1***1~", "SV1*HC:J1885*150.00*UN*1***1~")
    assert not any("J1885" in e["message"] for e in _l5(ok))


# --------------------------------------------------------------------------- #
#  CPT is gated — format-only + INFO note, never an error
# --------------------------------------------------------------------------- #
def test_cpt_is_format_only_with_info_note(sample_837p):
    issues = runner.validate(sample_837p, 5)["issues"]
    # 99213 / 71046 are CPT-range → no Level-5 ERROR ...
    assert not [i for i in issues if i["severity"] == "ERROR" and i["level"] == 5]
    # ... but an INFO note records that CPT membership was not checked.
    notes = [i for i in issues if i["level"] == 5 and i["severity"] == "INFO"]
    assert any("CPT" in n["message"] for n in notes)


# --------------------------------------------------------------------------- #
#  Gating + endpoint
# --------------------------------------------------------------------------- #
def test_level4_does_not_run_codesets(sample_837p):
    broken = sample_837p.replace("HI*ABK:J209*ABF:R05~", "HI*ABK:ZZ999*ABF:R05~")
    res = runner.validate(broken, 4)
    assert res["snip_level"] == 4
    assert not [i for i in res["issues"] if i["level"] == 5]


def test_endpoint_default_runs_level5(sample_837p):
    from engine.validation import HIGHEST_LEVEL

    broken = sample_837p.replace("HI*ABK:J209*ABF:R05~", "HI*ABK:ZZ999*ABF:R05~")
    resp = client.post("/edi/validate", files={"file": ("s.edi", broken.encode("utf-8"), "text/plain")})
    body = resp.json()
    assert body["snip_level"] == HIGHEST_LEVEL == 5
    assert any(i["level"] == 5 for i in body["issues"])
