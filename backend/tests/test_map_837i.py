"""Tests for 837I (Institutional / UB-04) mapping."""

from engine import converter


def test_837i_detected_and_form(sample_837i):
    result = converter.convert_edi(sample_837i, "auto")
    assert result["source_transaction"] == "ANSI X12 837I"
    assert result["form"] == "UB-04 (837I)"
    assert result["claim_count"] == 1


def test_837i_claim_header_fields(sample_837i):
    claim = converter.convert_edi(sample_837i)["claims"][0]
    assert claim["patient_account_no"] == "HOSPACCT01"
    assert claim["total_charge"] == "750"
    # Type of bill = facility type (11) + frequency (1)
    assert claim["facility_type_code"] == "11"
    assert claim["box_4_type_of_bill"] == "111"
    # Admission (CL1)
    assert claim["admission"]["admission_type_code"] == "3"
    assert claim["admission"]["admission_type"] == "Elective"
    assert claim["admission"]["patient_status_code"] == "01"
    # Statement + admission dates
    assert claim["statement_dates"] == "2024-01-10/2024-01-12"
    assert claim["admission_date"].startswith("2024-01-10")


def test_837i_institutional_codes(sample_837i):
    claim = converter.convert_edi(sample_837i)["claims"][0]

    # DRG
    assert claim["drg"]["code"] == "871"
    # Diagnoses: principal + other + admitting + patient reason
    quals = {d["qualifier"] for d in claim["box_21_diagnoses"]}
    assert {"ABK", "ABF", "ABJ", "APR"} <= quals
    # Procedures (ICD-10-PCS)
    assert claim["procedures"][0]["code"] == "0DTJ4ZZ"
    assert claim["procedures"][0]["date"] == "2024-01-11"
    # Occurrence / value / condition
    assert claim["occurrence_codes"][0]["code"] == "11"
    assert claim["value_codes"][0]["amount"] == "150"
    assert claim["condition_codes"][0]["code"] == "07"
    # Attending provider
    assert claim["providers"]["attending"]["last_name_or_org"] == "SURGEON"


def test_837i_service_lines_are_ub04(sample_837i):
    claim = converter.convert_edi(sample_837i)["claims"][0]
    assert len(claim["service_lines"]) == 2
    line = claim["service_lines"][0]
    assert line["box_42_revenue_code"] == "0300"
    assert line["box_44_hcpcs_procedure"] == "80053"
    assert line["box_47_line_charge"] == "250"
    assert line["box_46_units"] == "1"
    assert line["service_date"] == "2024-01-10"


def test_837i_forced_type_also_works(sample_837i):
    # Forcing 837I explicitly should match auto-detection.
    forced = converter.convert_edi(sample_837i, "837I")
    assert forced["form"] == "UB-04 (837I)"
