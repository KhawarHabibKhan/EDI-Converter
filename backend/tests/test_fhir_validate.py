"""Tests for the FHIR structural validator (V2-D) and /edi/fhir/validate."""

import pytest
from fastapi.testclient import TestClient

from engine import converter
from engine.fhir import validator
from engine.fhir import writer as fhir_writer
from main import app

client = TestClient(app)

ALL = [
    ("sample_837p", "837P"), ("sample_837i", "837I"), ("sample_835", "835"),
    ("sample_834", "834"), ("sample_270", "270"), ("sample_271", "271"),
    ("sample_277", "277"),
]


@pytest.mark.parametrize("fixture,code", ALL)
def test_generated_bundles_are_valid(request, fixture, code):
    raw = request.getfixturevalue(fixture)
    bundle = fhir_writer.to_fhir(converter.convert_edi(raw, code), code)
    report = validator.validate_report(bundle)
    assert report["valid"], f"{code} produced errors: {report['issues']}"
    assert report["error_count"] == 0


# --------------------------------------------------------------------------- #
#  Regressions found by the official HL7 validator (CI job `fhir-conformance`)
# --------------------------------------------------------------------------- #
def test_eob_total_has_no_reason_element(sample_835):
    # R4 ExplanationOfBenefit.total is category + amount only. `reason` is valid
    # on item.adjudication but not here — the X12 reason rides on the category.
    bundle = fhir_writer.to_fhir(converter.convert_edi(sample_835, "835"), "835")
    eobs = [e["resource"] for e in bundle["entry"]
            if e["resource"]["resourceType"] == "ExplanationOfBenefit"]
    assert eobs
    for eob in eobs:
        for total in eob.get("total", []):
            assert set(total) <= {"category", "amount"}, f"unexpected keys: {set(total)}"
        # The CAS reason code is preserved as an extra coding on the category.
        codings = [cd["code"] for t in eob.get("total", []) for cd in t["category"].get("coding", [])]
        assert "45" in codings


def test_eligibility_items_satisfy_ces_1(sample_271):
    # ces-1: an item SHALL contain a category or a billcode, but not both.
    bundle = fhir_writer.to_fhir(converter.convert_edi(sample_271, "271"), "271")
    responses = [e["resource"] for e in bundle["entry"]
                 if e["resource"]["resourceType"] == "CoverageEligibilityResponse"]
    assert responses
    items = [i for r in responses for ins in r.get("insurance", []) for i in ins.get("item", [])]
    assert items
    for item in items:
        assert ("category" in item) != ("productOrService" in item)


def test_detects_missing_required_element():
    bad = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {"resourceType": "Claim", "id": "claim-1", "status": "active"}}],
    }
    report = validator.validate_report(bad)
    assert not report["valid"]
    # 'created', 'type', 'use', 'patient', etc. are all missing.
    msgs = " ".join(i["message"] for i in report["issues"])
    assert "created is required" in msgs
    assert "patient is required" in msgs


def test_detects_entry_without_full_url():
    # Caught by the official HL7 validator before our own checked for it —
    # relative references are unresolvable without an entry fullUrl.
    bad = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {"resourceType": "Patient", "id": "patient-1"}}],
    }
    report = validator.validate_report(bad)
    assert not report["valid"]
    assert any("missing fullUrl" in i["message"] for i in report["issues"])


def test_detects_dangling_reference():
    bad = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {
            "resourceType": "Coverage", "id": "coverage-1", "status": "active",
            "beneficiary": {"reference": "Patient/ghost"},
            "payor": [{"reference": "Organization/org-1"}],
        }}],
    }
    report = validator.validate_report(bad)
    assert not report["valid"]
    assert any("does not resolve" in i["message"] for i in report["issues"])


def test_detects_bad_status_value():
    bad = {
        "resourceType": "Bundle", "type": "collection",
        "entry": [{"resource": {
            "resourceType": "Coverage", "id": "c1", "status": "banana",
            "beneficiary": {"reference": "Patient/p1"},
            "payor": [{"reference": "Organization/o1"}],
        }},
        {"resource": {"resourceType": "Patient", "id": "p1"}},
        {"resource": {"resourceType": "Organization", "id": "o1", "name": "X"}}],
    }
    report = validator.validate_report(bad)
    assert any("value set" in i["message"] for i in report["issues"])


def test_not_a_bundle():
    report = validator.validate_report({"resourceType": "Claim"})
    assert not report["valid"]


# --------------------------------------------------------------------------- #
#  endpoint
# --------------------------------------------------------------------------- #
def test_validate_endpoint_clean(sample_837p):
    resp = client.post(
        "/edi/fhir/validate",
        files={"file": ("s.edi", sample_837p.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["error_count"] == 0


def test_validate_endpoint_accepts_json_export(sample_835):
    import json
    exported = json.dumps(converter.convert_edi(sample_835, "835")).encode("utf-8")
    resp = client.post(
        "/edi/fhir/validate",
        files={"file": ("s.json", exported, "application/json")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    # JSON export input is not raw X12 → SNIP does not apply.
    assert body["snip_level"] is None


def test_validate_endpoint_bad_input_400():
    resp = client.post(
        "/edi/fhir/validate",
        files={"file": ("x.json", b'{"nope": true}', "application/json")},
    )
    assert resp.status_code == 400


def test_validate_endpoint_surfaces_source_snip_errors(sample_837p):
    """The FHIR page must flag source problems the Converter flags — a lenient
    mapper would otherwise still produce a 'valid' Bundle from a broken 837."""
    broken = sample_837p.replace("SV1*HC:99213:25*150.00*UN*1***1~", "").replace(
        "SV1*HC:71046*200.00*UN*1***1~", ""
    )
    resp = client.post(
        "/edi/fhir/validate",
        files={"file": ("s.edi", broken.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["snip_level"] >= 2
    snip_issues = [i for i in body["issues"] if i.get("stage") == "snip"]
    assert any("SV1" in i["segment"] for i in snip_issues)


def test_validate_endpoint_clean_has_both_stages_available(sample_837p):
    """A clean 837 runs both SNIP (source) and FHIR (output) checks."""
    resp = client.post(
        "/edi/fhir/validate",
        files={"file": ("s.edi", sample_837p.encode("utf-8"), "text/plain")},
    )
    body = resp.json()
    assert body["valid"] is True
    assert body["transaction_type"] == "837P"
