"""Tests for xml_reader — the reverse of xml_writer."""

from engine import converter, xml_reader, xml_writer


def test_roundtrip_scalars_dicts_lists():
    data = {"a": "1", "b": {"c": "x"}, "list": [{"k": "v"}, {"k": "w"}]}
    xml = xml_writer.to_xml(data, root="EdiDocument")
    back = xml_reader.to_dict(xml)
    assert back == data


def test_empty_containers_become_none():
    # xml_writer collapses None / {} / [] to a self-closing tag, so all three
    # read back as None. That is the documented, accepted ambiguity.
    xml = xml_writer.to_xml({"none": None, "empty_dict": {}, "empty_list": []})
    back = xml_reader.to_dict(xml)
    assert back == {"none": None, "empty_dict": None, "empty_list": None}


def test_escaped_characters_roundtrip():
    data = {"amp": "a & b < c > d"}
    back = xml_reader.to_dict(xml_writer.to_xml(data))
    assert back["amp"] == "a & b < c > d"


def test_837p_full_roundtrip(sample_837p):
    original = converter.convert_edi(sample_837p, "837P")
    xml = xml_writer.to_xml(original)
    back = xml_reader.to_dict(xml)
    # Numbers in the mapper output are already strings, so structure is stable.
    assert back["source_transaction"] == "ANSI X12 837P"
    assert back["claims"][0]["total_charge"] == "350.00"
    assert len(back["claims"][0]["service_lines"]) == len(
        original["claims"][0]["service_lines"]
    )


def test_malformed_xml_raises():
    import pytest

    with pytest.raises(xml_reader.XmlReadError):
        xml_reader.to_dict("<not well formed>")
