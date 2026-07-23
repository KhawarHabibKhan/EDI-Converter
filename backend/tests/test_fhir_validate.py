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
    assert body["snip_level"] == 2
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
