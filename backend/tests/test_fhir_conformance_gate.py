"""The CI conformance verdict (`scripts/check_fhir_conformance.py`).

The gate decides whether an HL7-validator run fails the build: everything blocks
except CPT "unknown code" findings, which are waived because CPT is AMA-licensed
and HL7 ships only a fragment of it (same reasoning as SNIP Level 5's
``CPT_MEMBERSHIP`` flag). Both output formats the CLI can produce are covered.
"""

import importlib.util
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_fhir_conformance", BACKEND / "scripts" / "check_fhir_conformance.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

CPT_MSG = "Unknown code '99299' in the CodeSystem 'http://www.ama-assn.org/go/cpt' version '2023'"
REAL_MSG = "Constraint failed: ces-1: 'SHALL contain a category or a billcode but not both.'"

TEXT_REPORT = f"""\
----------------------------------------------------------------------------------
bundles/837P-all-fields.bundle.json 02:51:15
[7, 8] Bundle.entry[0].resource: Warning - Constraint failed: dom-6: 'narrative'
[175, 14] Bundle.entry[4].resource/*Claim/claim-1*/.item[0].productOrService.coding[0].code: Error - {CPT_MSG}
"""


def _outcome_bundle(*messages):
    return json.dumps({
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {
            "resourceType": "OperationOutcome",
            "extension": [{
                "url": "http://hl7.org/fhir/StructureDefinition/operationoutcome-file",
                "valueString": "bundles\\\\271-sample.bundle.json",
            }],
            "issue": [
                {"severity": "error", "expression": ["Bundle.entry[5]"],
                 "details": {"text": m}} for m in messages
            ] + [{"severity": "warning", "details": {"text": "narrative missing"}}],
        }}],
    })


def _verdict(raw, tmp_path, name="report.json"):
    path = tmp_path / name
    path.write_text(raw, encoding="utf-8")
    return gate.main(path)


def test_text_report_waives_cpt_only_findings(tmp_path, capsys):
    assert _verdict(TEXT_REPORT, tmp_path) == 0
    out = capsys.readouterr().out
    assert "WAIVED" in out and "PASS" in out


def test_outcome_bundle_waives_cpt_only_findings(tmp_path, capsys):
    assert _verdict(_outcome_bundle(CPT_MSG), tmp_path) == 0
    assert "PASS" in capsys.readouterr().out


def test_real_conformance_error_fails_the_build(tmp_path, capsys):
    assert _verdict(_outcome_bundle(REAL_MSG), tmp_path) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "ces-1" in out


def test_real_error_still_fails_alongside_a_waived_one(tmp_path, capsys):
    # A waiver must never mask a genuine finding in the same run.
    assert _verdict(_outcome_bundle(CPT_MSG, REAL_MSG), tmp_path) == 1
    out = capsys.readouterr().out
    assert "WAIVED" in out and "FAIL" in out


def test_clean_report_passes(tmp_path, capsys):
    assert _verdict(json.dumps({"resourceType": "Bundle", "type": "collection", "entry": []}), tmp_path) == 0
    assert "PASS" in capsys.readouterr().out
