"""Tests for transaction-type detection and auto-dispatch."""

import pytest

from engine import converter, detector


def _st(code: str, version: str = "") -> str:
    """Minimal EDI with an ISA (for delimiters) and one ST segment."""
    isa = (
        "ISA*00*          *00*          *ZZ*SUB            *ZZ*REC            "
        "*240115*1200*^*00501*000000001*0*P*:~"
    )
    ver = f"*{version}" if version else ""
    return f"{isa}ST*{code}*0001{ver}~"


@pytest.mark.parametrize(
    "code,version,expected",
    [
        ("837", "005010X222A1", "837P"),
        ("837", "005010X223A2", "837I"),
        ("837", "", "837P"),  # no version → default professional
        ("835", "", "835"),
        ("834", "", "834"),
        ("271", "", "271"),
        ("277", "", "277"),
    ],
)
def test_detect_transaction_type(code, version, expected):
    assert detector.detect_transaction_type(_st(code, version)) == expected


def test_detect_from_real_837p(sample_837p):
    assert detector.detect_transaction_type(sample_837p) == "837P"


def test_detect_no_st_raises():
    with pytest.raises(detector.DetectionError):
        detector.detect_transaction_type("ISA*00*  ~GS*HC*a*b*20240101*1200*1*X*005010~")


def test_auto_convert_837p(sample_837p):
    result = converter.convert_edi(sample_837p, "auto")
    assert result["source_transaction"] == "ANSI X12 837P"
    assert result["claim_count"] == 1


def test_auto_convert_unsupported_type_message():
    # 999 (functional acknowledgment) is not a mapped type.
    with pytest.raises(converter.UnsupportedTransactionError) as exc:
        converter.convert_edi(_st("999"), "auto")
    assert "999" in str(exc.value)
