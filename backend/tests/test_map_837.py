"""Tests for the 837P mapper and the converter entry point."""

from engine import converter


def test_convert_sample_837p_basic(sample_837p):
    result = converter.convert_edi(sample_837p, "837P")

    assert result["source_transaction"] == "ANSI X12 837P"
    assert result["claim_count"] == 1

    claim = result["claims"][0]
    assert claim["patient_account_no"] == "PATACCT001"
    assert claim["total_charge"] == "350.00"

    # Insured / payer / providers carried down from HL context.
    assert claim["insured"]["last_name_or_org"] == "SMITH"
    assert claim["insured"]["first_name"] == "JOHN"
    assert claim["payer"]["last_name_or_org"] == "ACME INSURANCE COMPANY"
    assert claim["providers"]["billing"]["last_name_or_org"] == "DOCTORS EXPRESS CLINIC"
    assert claim["providers"]["rendering"]["last_name_or_org"] == "JONES"

    # Diagnoses and service lines.
    assert len(claim["box_21_diagnoses"]) == 2
    assert claim["box_21_diagnoses"][0]["code"] == "J209"
    assert claim["box_21_diagnoses"][0]["pointer"] == "A"
    assert len(claim["service_lines"]) == 2
    assert claim["service_lines"][0]["box_24d_procedure_code"] == "99213"
    assert claim["service_lines"][0]["box_24d_modifiers"] == ["25"]


def test_convert_all_fields_837p(all_fields_837p):
    result = converter.convert_edi(all_fields_837p, "837P")

    assert result["claim_count"] == 1
    claim = result["claims"][0]

    # This richer file uses '>' repetition and ':' component separators.
    assert claim["patient_account_no"] == "36463774"
    assert claim["insured"]["last_name_or_org"] == "SMITH"
    assert claim["patient"]["first_name"] == "TED"
    assert claim["patient"]["date_of_birth"] == "1973-05-01"
    # Only the real ICD-10 diagnosis qualifiers (ABK/ABF) count as diagnoses;
    # other HI qualifiers in this synthetic file are routed to their own buckets.
    assert len(claim["box_21_diagnoses"]) == 2
    assert claim["box_21_diagnoses"][0]["code"] == "J0300"
    assert len(claim["service_lines"]) == 4

    # A service line with a date range (RD8) is formatted as start/end.
    dates = [ln.get("box_24a_service_date") for ln in claim["service_lines"]]
    assert any("/" in (d or "") for d in dates)


def test_auto_delimiter_detection(all_fields_837p):
    # No exception and correct type despite non-default separators.
    result = converter.convert_edi(all_fields_837p)
    assert "837P" in result["source_transaction"]


def test_unsupported_type_raises(sample_837p):
    import pytest

    with pytest.raises(converter.UnsupportedTransactionError):
        converter.convert_edi(sample_837p, "999")


def test_empty_input_raises():
    import pytest

    with pytest.raises(ValueError):
        converter.convert_edi("   ")
