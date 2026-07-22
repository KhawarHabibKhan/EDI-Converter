"""Tests for 835 (remittance) and 834 (enrollment) mappers."""

from engine import converter


# --------------------------------------------------------------------------- #
#  835 Remittance
# --------------------------------------------------------------------------- #
def test_835_detect_and_payment(sample_835):
    result = converter.convert_edi(sample_835, "auto")
    assert result["source_transaction"] == "ANSI X12 835"
    pay = result["header"]["payment"]
    assert pay["total_paid_amount"] == "945"
    assert pay["payment_method"] == "ACH"
    assert pay["trace_number"] == "CHECK12345"


def test_835_payer_payee(sample_835):
    result = converter.convert_edi(sample_835)
    assert result["payer"]["name"] == "ANY PLAN USA"
    assert result["payee"]["name"] == "GENERAL HOSPITAL"


def test_835_claim_and_service_payments(sample_835):
    result = converter.convert_edi(sample_835)
    assert result["claim_count"] == 1
    claim = result["claims"][0]
    assert claim["patient_control_number"] == "PATACCT001"
    assert claim["total_charge"] == "800"
    assert claim["total_paid"] == "500"
    assert claim["patient"]["last_name_or_org"] == "SMITH"

    # Claim-level adjustments (CAS CO/PR)
    groups = {a["group_code"] for a in claim["adjustments"]}
    assert {"CO", "PR"} <= groups

    # Service payments
    assert len(claim["service_payments"]) == 2
    svc0 = claim["service_payments"][0]
    assert svc0["procedure_code"] == "99213"
    assert svc0["paid_amount"] == "300"
    assert svc0["adjustments"][0]["reason_code"] == "45"

    # Provider-level adjustment
    assert result["provider_adjustments"][0]["amount"] == "-25"


# --------------------------------------------------------------------------- #
#  834 Enrollment
# --------------------------------------------------------------------------- #
def test_834_detect_and_parties(sample_834):
    result = converter.convert_edi(sample_834, "auto")
    assert result["source_transaction"] == "ANSI X12 834"
    assert result["sponsor"]["name"] == "ACME EMPLOYER"
    assert result["payer"]["name"] == "ACME INSURANCE COMPANY"


def test_834_members_and_coverage(sample_834):
    result = converter.convert_edi(sample_834)
    assert result["member_count"] == 2

    sub = result["members"][0]
    assert sub["subscriber_indicator"] == "Y"
    assert sub["maintenance_type"] == "Addition"
    assert sub["member"]["last_name_or_org"] == "SMITH"
    assert sub["member"]["first_name"] == "JOHN"
    # Two coverages (health + dental), each with a begin date
    lines = {c["insurance_line"] for c in sub["coverages"]}
    assert {"Health", "Dental"} <= lines
    assert sub["coverages"][0]["dates"][0]["value"] == "2024-01-01"

    dep = result["members"][1]
    assert dep["subscriber_indicator"] == "N"
    assert dep["member"]["first_name"] == "JANE"
