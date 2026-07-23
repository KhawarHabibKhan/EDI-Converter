"""Tests for the input adapter — detect EDI / our JSON / our XML → (dict, type)."""

import json

import pytest

from engine import converter, input_adapter, xml_writer


def test_detects_and_loads_edi(sample_837p):
    data, ttype = input_adapter.detect_and_load(sample_837p, "s.edi")
    assert ttype == "837P"
    assert data["source_transaction"] == "ANSI X12 837P"


def test_detects_837i(sample_837i):
    data, ttype = input_adapter.detect_and_load(sample_837i, "i.edi")
    assert ttype == "837I"


def test_loads_our_json(sample_837p):
    exported = json.dumps(converter.convert_edi(sample_837p, "837P"))
    data, ttype = input_adapter.detect_and_load(exported, "s.json")
    assert ttype == "837P"
    assert data["claims"][0]["total_charge"] == "350.00"


def test_loads_our_xml(sample_837p):
    exported = xml_writer.to_xml(converter.convert_edi(sample_837p, "837P"))
    data, ttype = input_adapter.detect_and_load(exported, "s.xml")
    assert ttype == "837P"
    assert data["source_transaction"] == "ANSI X12 837P"


def test_content_sniffing_ignores_wrong_extension(sample_837p):
    # EDI content in a .dat file is still detected as EDI.
    data, ttype = input_adapter.detect_and_load(sample_837p, "misnamed.dat")
    assert ttype == "837P"


def test_rejects_foreign_json():
    with pytest.raises(input_adapter.InputFormatError):
        input_adapter.detect_and_load('{"hello": "world"}', "x.json")


def test_rejects_unrecognized_text():
    with pytest.raises(input_adapter.InputFormatError):
        input_adapter.detect_and_load("just some plain words here", "x.unknown")
