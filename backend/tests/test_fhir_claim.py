"""Tests for the FHIR pipeline (V2-A): 837 → Claim Bundle.

Covers the resource mapper, the writer/dispatch, common builders, the
EDI/JSON/XML round-trip equivalence, and the /edi/fhir endpoint.
"""

import json

import pytest
from fastapi.testclient import TestClient

from engine import converter, xml_writer
from engine.fhir import common
from engine.fhir import writer as fhir_writer
from main import app

client = TestClient(app)


# --------------------------------------------------------------------------- #
#  common builders
# --------------------------------------------------------------------------- #
def test_codeable_concept_never_bare_code():
    cc = common.codeable_concept("J209", common.SYSTEM["icd10cm"])
    assert cc == {"coding": [{"code": "J209", "system": common.SYSTEM["icd10cm"]}]}
    assert common.codeable_concept("") is None


def test_icd10cm_codes_get_their_decimal_point():
    # X12 carries ICD-10-CM undotted; the FHIR code system is defined with the dot.
    assert common.icd10cm_code("J0300") == "J03.00"
    assert common.icd10cm_code("Z1159") == "Z11.59"
    assert common.icd10cm_code("J209") == "J20.9"
    assert common.icd10cm_code("A00") == "A00"      # 3-char category: no dot
    assert common.icd10cm_code("J20.9") == "J20.9"  # already dotted: untouched
    assert common.icd10cm_code("") is None


def test_bundle_entries_carry_a_resolvable_full_url():
    # Relative references only resolve against the entry's fullUrl base.
    b = common.bundle([{"resourceType": "Patient", "id": "patient-1"}])
    assert b["entry"][0]["fullUrl"] == f"{common.BUNDLE_BASE_URL}/Patient/patient-1"


def test_money_parses_strings():
    assert common.money("350.00") == {"value": 350.0, "currency": "USD"}
    assert common.money("") is None
    assert common.money("abc") is None


def test_prune_drops_none_and_empties():
    assert common.prune({"a": 1, "b": None, "c": {}, "d": [], "e": {"x": None}}) == {"a": 1}


# --------------------------------------------------------------------------- #
#  writer / mapper
# --------------------------------------------------------------------------- #
def _bundle_from_edi(raw, ttype):
    data = converter.convert_edi(raw, ttype)
    return fhir_writer.to_fhir(data, ttype)


def _resource(bundle, rtype):
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == rtype]


def test_837p_produces_claim_bundle(sample_837p):
    bundle = _bundle_from_edi(sample_837p, "837P")
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"

    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert "Claim" in types
    assert "Patient" in types
    assert "Coverage" in types
    assert "Organization" in types

    claim = _resource(bundle, "Claim")[0]
    assert claim["status"] == "active"
    assert claim["use"] == "claim"
    assert claim["type"]["coding"][0]["code"] == "professional"
    assert claim["total"] == {"value": 350.0, "currency": "USD"}


def test_claim_references_resolve(sample_837p):
    bundle = _bundle_from_edi(sample_837p, "837P")
    ids = {e["resource"]["id"] for e in bundle["entry"]}
    claim = _resource(bundle, "Claim")[0]

    # Every reference the Claim makes points at a resource in the Bundle.
    def target(ref):
        return ref["reference"].split("/", 1)[1]

    assert target(claim["patient"]) in ids
    assert target(claim["insurer"]) in ids
    assert target(claim["insurance"][0]["coverage"]) in ids


def test_diagnosis_and_items_mapped(sample_837p):
    bundle = _bundle_from_edi(sample_837p, "837P")
    claim = _resource(bundle, "Claim")[0]
    assert len(claim["diagnosis"]) >= 1
    diag = claim["diagnosis"][0]
    assert diag["sequence"] == 1
    assert diag["diagnosisCodeableConcept"]["coding"][0]["system"] == common.SYSTEM["icd10cm"]

    item = claim["item"][0]
    assert item["sequence"] == 1
    assert item["productOrService"]["coding"][0]["code"]
    assert item["net"]["currency"] == "USD"


def test_837i_is_institutional_with_revenue(sample_837i):
    bundle = _bundle_from_edi(sample_837i, "837I")
    claim = _resource(bundle, "Claim")[0]
    assert claim["type"]["coding"][0]["code"] == "institutional"
    assert "revenue" in claim["item"][0]


def test_unsupported_type_raises():
    # All eight X12 types now map; a type with no FHIR mapper (e.g. 999) errors.
    with pytest.raises(fhir_writer.UnsupportedFhirError) as exc:
        fhir_writer.to_fhir({"source_transaction": "ANSI X12 999"}, "999")
    assert "999" in str(exc.value)


def test_roundtrip_edi_json_xml_equivalent(sample_837p):
    b_edi = _bundle_from_edi(sample_837p, "837P")
    b_json = fhir_writer.to_fhir(
        json.loads(json.dumps(converter.convert_edi(sample_837p, "837P"))), "837P"
    )
    from engine import xml_reader
    b_xml = fhir_writer.to_fhir(
        xml_reader.to_dict(xml_writer.to_xml(converter.convert_edi(sample_837p, "837P"))),
        "837P",
    )
    assert b_edi == b_json == b_xml


# --------------------------------------------------------------------------- #
#  /edi/fhir endpoint
# --------------------------------------------------------------------------- #
def test_fhir_endpoint_edi(sample_837p):
    resp = client.post(
        "/edi/fhir",
        files={"file": ("s.edi", sample_837p.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/fhir+json")
    bundle = resp.json()
    assert bundle["resourceType"] == "Bundle"
    assert any(e["resource"]["resourceType"] == "Claim" for e in bundle["entry"])


def test_fhir_endpoint_accepts_json_export(sample_837p):
    exported = json.dumps(converter.convert_edi(sample_837p, "837P")).encode("utf-8")
    resp = client.post(
        "/edi/fhir",
        files={"file": ("s.json", exported, "application/json")},
    )
    assert resp.status_code == 200
    assert any(e["resource"]["resourceType"] == "Claim" for e in resp.json()["entry"])


def test_fhir_endpoint_accepts_xml_export(sample_837p):
    exported = xml_writer.to_xml(converter.convert_edi(sample_837p, "837P")).encode("utf-8")
    resp = client.post(
        "/edi/fhir",
        files={"file": ("s.xml", exported, "application/xml")},
    )
    assert resp.status_code == 200
    assert any(e["resource"]["resourceType"] == "Claim" for e in resp.json()["entry"])


def test_fhir_endpoint_unsupported_type_400():
    # 999 (functional acknowledgment) has no v1 mapper → clean 400.
    edi = (
        "ISA*00*          *00*          *ZZ*SUB            *ZZ*REC            "
        "*240115*1200*^*00501*000000001*0*P*:~ST*999*0001~"
    )
    resp = client.post(
        "/edi/fhir",
        files={"file": ("ack.edi", edi.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 400
    assert "999" in resp.json()["detail"]


def test_fhir_endpoint_rejects_foreign_json():
    resp = client.post(
        "/edi/fhir",
        files={"file": ("x.json", b'{"hello":"world"}', "application/json")},
    )
    assert resp.status_code == 400
