"""Tests for the shared XML serializer and the /edi/xml endpoint."""

from engine import converter, xml_writer


def test_to_xml_basic_structure():
    data = {"a": 1, "b": {"c": "x"}, "list": [{"k": "v"}, {"k": "w"}]}
    xml = xml_writer.to_xml(data, root="Root")
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<Root>" in xml and "</Root>" in xml
    assert "<a>1</a>" in xml
    assert "<c>x</c>" in xml
    # list items are wrapped in <item>
    assert xml.count("<item>") == 2


def test_to_xml_escapes_and_empty():
    xml = xml_writer.to_xml({"amp": "a & b < c", "empty": {}, "none": None})
    assert "a &amp; b &lt; c" in xml
    assert "<empty/>" in xml
    assert "<none/>" in xml


def test_convert_837p_to_xml(sample_837p):
    data = converter.convert_edi(sample_837p, "837P")
    xml = xml_writer.to_xml(data)
    assert "<source_transaction>ANSI X12 837P</source_transaction>" in xml
    assert "<total_charge>350.00</total_charge>" in xml
    # well-formed: parses without error
    import xml.dom.minidom as minidom

    minidom.parseString(xml)  # raises if malformed
