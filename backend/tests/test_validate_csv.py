"""Tests for the structural validator and the CSV writer."""

from engine import converter, csv_writer, validator


# --------------------------------------------------------------------------- #
#  Validator
# --------------------------------------------------------------------------- #
def test_valid_file_has_no_errors(sample_837p):
    issues = validator.validate_edi(sample_837p)
    errors = [i for i in issues if i["severity"] == "ERROR"]
    assert errors == []


def test_se_count_mismatch_detected():
    # SE01 claims 99 segments; actual is far fewer.
    edi = (
        "ISA*00*          *00*          *ZZ*A              *ZZ*B              "
        "*240115*1200*^*00501*000000001*0*P*:~"
        "GS*HC*A*B*20240115*1200*1*X*005010X222A1~"
        "ST*837*0001*005010X222A1~BHT*0019*00*R*20240115*1200*CH~"
        "SE*99*0001~GE*1*1~IEA*1*000000001~"
    )
    issues = validator.validate_edi(edi)
    msgs = " ".join(i["message"] for i in issues)
    assert "SE01 segment count" in msgs


def test_control_number_mismatch_detected():
    edi = (
        "ISA*00*          *00*          *ZZ*A              *ZZ*B              "
        "*240115*1200*^*00501*000000001*0*P*:~"
        "GS*HC*A*B*20240115*1200*1*X*005010X222A1~"
        "ST*837*0001*005010X222A1~SE*3*0001~"
        "GE*1*1~IEA*1*999999999~"  # IEA02 != ISA13
    )
    issues = validator.validate_edi(edi)
    assert any("does not match ISA13" in i["message"] for i in issues)


def test_empty_input_is_error():
    issues = validator.validate_edi("   ")
    assert issues and issues[0]["severity"] == "ERROR"


# --------------------------------------------------------------------------- #
#  CSV writer
# --------------------------------------------------------------------------- #
def test_csv_837p_one_row_per_service_line(sample_837p):
    data = converter.convert_edi(sample_837p)
    csv_text = csv_writer.to_csv(data)
    lines = [ln for ln in csv_text.splitlines() if ln.strip()]
    assert lines[0].startswith("transaction,patient_account_no")
    # header + 2 service lines
    assert len(lines) == 3
    assert "99213" in csv_text and "350.00" in csv_text


def test_csv_835_payments(sample_835):
    data = converter.convert_edi(sample_835)
    csv_text = csv_writer.to_csv(data)
    assert "patient_control_number" in csv_text
    assert "PATACCT001" in csv_text


def test_csv_271_benefits(sample_271):
    data = converter.convert_edi(sample_271)
    csv_text = csv_writer.to_csv(data)
    assert "subscriber" in csv_text
    assert "SMITH" in csv_text
