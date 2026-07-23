"""Tests for the FHIR pipeline (V2-B): 835 → ExplanationOfBenefit Bundle."""

import json

from fastapi.testclient import TestClient

from engine import converter, xml_reader, xml_writer
from engine.fhir import common
from engine.fhir import writer as fhir_writer
from main import app

client = TestClient(app)


def _bundle(raw):
    return fhir_writer.to_fhir(converter.convert_edi(raw, "835"), "835")


def _resource(bundle, rtype):
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == rtype]


def test_835_produces_eob_bundle(sample_835):
    bundle = _bundle(sample_835)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert "ExplanationOfBenefit" in types
    assert "Patient" in types
    assert "Coverage" in types
    assert types.count("Organization") == 2  # payer + payee

    eob = _resource(bundle, "ExplanationOfBenefit")[0]
    assert eob["status"] == "active"
    assert eob["use"] == "claim"
    assert eob["outcome"] == "complete"
    assert eob["created"] == "2024-12-25"


def test_eob_references_resolve(sample_835):
    bundle = _bundle(sample_835)
    ids = {e["resource"]["id"] for e in bundle["entry"]}
    eob = _resource(bundle, "ExplanationOfBenefit")[0]

    def target(ref):
        return ref["reference"].split("/", 1)[1]

    assert target(eob["patient"]) in ids
    assert target(eob["insurer"]) in ids   # payer
    assert target(eob["provider"]) in ids  # payee
    assert target(eob["insurance"][0]["coverage"]) in ids


def test_eob_totals_and_payment(sample_835):
    eob = _resource(_bundle(sample_835), "ExplanationOfBenefit")[0]
    cats = {t["category"]["coding"][0]["code"]: t["amount"]["value"] for t in eob["total"]}
    assert cats["submitted"] == 800.0
    assert cats["benefit"] == 500.0
    assert eob["payment"]["amount"] == {"value": 945.0, "currency": "USD"}
    assert eob["payment"]["identifier"]["value"] == "CHECK12345"


def test_eob_item_adjudication(sample_835):
    eob = _resource(_bundle(sample_835), "ExplanationOfBenefit")[0]
    item = eob["item"][0]
    codes = {a["category"]["coding"][0]["code"] for a in item["adjudication"]}
    assert "submitted" in codes and "benefit" in codes
    # CAS adjustment carried through with its X12 group + reason codes.
    cas = [a for a in item["adjudication"] if a["category"]["coding"][0]["system"] == common.SYSTEM["adjustment_group"]]
    assert cas and cas[0]["reason"]["coding"][0]["code"]


def test_eob_plb_surfaced_as_note(sample_835):
    eob = _resource(_bundle(sample_835), "ExplanationOfBenefit")[0]
    texts = " ".join(n["text"] for n in eob.get("processNote", []))
    assert "Provider-level adjustment" in texts


def test_roundtrip_edi_json_xml_equivalent(sample_835):
    b_edi = _bundle(sample_835)
    b_json = fhir_writer.to_fhir(json.loads(json.dumps(converter.convert_edi(sample_835, "835"))), "835")
    b_xml = fhir_writer.to_fhir(xml_reader.to_dict(xml_writer.to_xml(converter.convert_edi(sample_835, "835"))), "835")
    assert b_edi == b_json == b_xml


def test_fhir_endpoint_835(sample_835):
    resp = client.post(
        "/edi/fhir",
        files={"file": ("r.edi", sample_835.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/fhir+json")
    assert any(
        e["resource"]["resourceType"] == "ExplanationOfBenefit" for e in resp.json()["entry"]
    )
