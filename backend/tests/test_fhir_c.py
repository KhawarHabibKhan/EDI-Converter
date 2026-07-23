"""Tests for the FHIR pipeline (V2-C): 834 → Coverage, 270/271 →
CoverageEligibility, 276/277 → Task."""

import json

from fastapi.testclient import TestClient

from engine import converter, xml_reader, xml_writer
from engine.fhir import common
from engine.fhir import writer as fhir_writer
from main import app

client = TestClient(app)


def _bundle(raw, code):
    return fhir_writer.to_fhir(converter.convert_edi(raw, code), code)


def _res(bundle, rtype):
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == rtype]


def _refs_resolve(bundle):
    ids = {e["resource"]["id"] for e in bundle["entry"]}

    def walk(obj):
        if isinstance(obj, dict):
            if "reference" in obj and isinstance(obj["reference"], str) and "/" in obj["reference"]:
                assert obj["reference"].split("/", 1)[1] in ids, f"dangling {obj['reference']}"
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(bundle)


# --------------------------------------------------------------------------- #
#  834 → Coverage
# --------------------------------------------------------------------------- #
def test_834_produces_coverage(sample_834):
    bundle = _bundle(sample_834, "834")
    coverages = _res(bundle, "Coverage")
    assert coverages  # at least one HD line
    cov = coverages[0]
    assert cov["status"] == "active"
    assert cov["beneficiary"]["reference"].startswith("Patient/")
    assert cov["payor"][0]["reference"].startswith("Organization/")
    assert cov["relationship"]["coding"][0]["code"] == "self"
    _refs_resolve(bundle)


def test_834_multiple_coverage_lines(sample_834):
    # First member has HLT + DEN → two Coverage resources.
    bundle = _bundle(sample_834, "834")
    first_patient_covs = [c for c in _res(bundle, "Coverage") if c["id"].startswith("coverage-1-")]
    assert len(first_patient_covs) == 2
    lines = {c["type"]["coding"][0]["code"] for c in first_patient_covs}
    assert {"HLT", "DEN"} <= lines


# --------------------------------------------------------------------------- #
#  270 / 271 → CoverageEligibility
# --------------------------------------------------------------------------- #
def test_270_produces_request(sample_270):
    bundle = _bundle(sample_270, "270")
    reqs = _res(bundle, "CoverageEligibilityRequest")
    assert len(reqs) == 1
    req = reqs[0]
    assert req["status"] == "active"
    assert req["purpose"] == ["benefits"]
    assert req["insurer"]["reference"].startswith("Organization/")
    assert req["created"]
    # EQ*30 → one item with that service-type category.
    assert req["item"][0]["category"]["coding"][0]["code"] == "30"
    _refs_resolve(bundle)


def test_271_produces_response_with_items(sample_271):
    bundle = _bundle(sample_271, "271")
    resp = _res(bundle, "CoverageEligibilityResponse")[0]
    assert resp["outcome"] == "complete"
    # request + coverage references are required by R4 and must resolve.
    assert resp["request"]["reference"].startswith("CoverageEligibilityRequest/")
    assert resp["insurance"][0]["coverage"]["reference"].startswith("Coverage/")
    assert resp["insurance"][0]["item"]  # EB loops mapped to items
    _refs_resolve(bundle)


def test_271_eligibility_code_carried(sample_271):
    resp = _res(_bundle(sample_271, "271"), "CoverageEligibilityResponse")[0]
    systems = {
        b["type"]["coding"][0]["system"]
        for item in resp["insurance"][0]["item"]
        for b in item.get("benefit", [])
    }
    assert common.SYSTEM["eligibility_info"] in systems


# --------------------------------------------------------------------------- #
#  276 / 277 → Task
# --------------------------------------------------------------------------- #
def test_277_produces_task(sample_277):
    bundle = _bundle(sample_277, "277")
    task = _res(bundle, "Task")[0]
    assert task["status"] == "completed"
    assert task["intent"] == "order"
    assert task["identifier"][0]["value"] == "CLAIM10012345"
    assert task["businessStatus"]["coding"][0]["code"] == "A2"
    assert task["for"]["reference"].startswith("Patient/")
    assert task["output"]  # STC statuses surfaced
    _refs_resolve(bundle)


# --------------------------------------------------------------------------- #
#  round-trip + endpoint coverage for all V2-C types
# --------------------------------------------------------------------------- #
def test_roundtrip_all_c_types(sample_834, sample_270, sample_271, sample_277):
    for raw, code in [(sample_834, "834"), (sample_270, "270"), (sample_271, "271"), (sample_277, "277")]:
        b_edi = _bundle(raw, code)
        b_json = fhir_writer.to_fhir(json.loads(json.dumps(converter.convert_edi(raw, code))), code)
        b_xml = fhir_writer.to_fhir(xml_reader.to_dict(xml_writer.to_xml(converter.convert_edi(raw, code))), code)
        assert b_edi == b_json == b_xml, f"round-trip mismatch for {code}"


def test_fhir_endpoint_all_c_types(sample_834, sample_270, sample_271, sample_277):
    expected = {
        "834": "Coverage",
        "270": "CoverageEligibilityRequest",
        "271": "CoverageEligibilityResponse",
        "277": "Task",
    }
    for raw, code in [(sample_834, "834"), (sample_270, "270"), (sample_271, "271"), (sample_277, "277")]:
        resp = client.post("/edi/fhir", files={"file": (f"{code}.edi", raw.encode("utf-8"), "text/plain")})
        assert resp.status_code == 200, code
        types = [e["resource"]["resourceType"] for e in resp.json()["entry"]]
        assert expected[code] in types, code
