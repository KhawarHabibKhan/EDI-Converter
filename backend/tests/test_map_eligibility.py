"""Tests for 271 (eligibility) and 277 (claim status) mappers."""

from engine import converter


# --------------------------------------------------------------------------- #
#  271 Eligibility (real sample file)
# --------------------------------------------------------------------------- #
def test_271_detect_and_hierarchy(sample_271):
    result = converter.convert_edi(sample_271, "auto")
    assert result["source_transaction"] == "ANSI X12 271"

    sources = result["information_sources"]
    assert len(sources) == 1
    assert sources[0]["payer"]["last_name_or_org"] == "ABC COMPANY"

    receivers = sources[0]["information_receivers"]
    assert receivers[0]["provider"]["last_name_or_org"] == "BONE AND JOINT CLINIC"

    subs = receivers[0]["subscribers"]
    assert len(subs) == 1
    sub = subs[0]
    assert sub["info"]["last_name_or_org"] == "SMITH"
    assert sub["info"]["first_name"] == "JOHN"
    assert sub["info"]["date_of_birth"] == "1963-05-19"
    assert sub["trace_numbers"][0]["trace_number"] == "93175-012547"


def test_271_eligibility_benefits(sample_271):
    sub = converter.convert_edi(sample_271)["information_sources"][0][
        "information_receivers"
    ][0]["subscribers"][0]

    elig = sub["eligibility"]
    assert len(elig) >= 4
    # First EB is active coverage for the GOLD 123 PLAN
    assert elig[0]["eligibility"] == "Active Coverage"
    assert elig[0]["plan_description"] == "GOLD 123 PLAN"
    # A benefit line with repetition-separated service type codes
    with_types = [e for e in elig if e["service_type_codes"]]
    assert any(len(e["service_type_codes"]) > 1 for e in with_types)
    # A co-payment benefit with an in-plan network indicator
    copays = [e for e in elig if e["eligibility_code"] == "B"]
    assert copays and copays[0]["in_plan_network_indicator"] in ("Y", "N")


# --------------------------------------------------------------------------- #
#  277 Claim Status
# --------------------------------------------------------------------------- #
def test_277_detect_and_status(sample_277):
    result = converter.convert_edi(sample_277, "auto")
    assert result["source_transaction"] == "ANSI X12 277"
    assert result["claim_count"] == 1

    claim = result["claims"][0]
    assert claim["trace_number"] == "CLAIM10012345"
    st = claim["statuses"][0]
    assert st["category_code"] == "A2"
    assert st["status_code"] == "20"
    assert st["total_charge"] == "800"
    assert claim["references"][0]["value"] == "94060555410000"

    # Service line with its own status
    assert len(claim["service_lines"]) == 1
    line = claim["service_lines"][0]
    assert line["procedure_code"] == "99213"
    assert line["statuses"][0]["paid_amount"] == "200"


def test_270_request_with_inquiry(sample_270):
    result = converter.convert_edi(sample_270, "auto")
    assert result["source_transaction"] == "ANSI X12 270"
    sub = result["information_sources"][0]["information_receivers"][0]["subscribers"][0]
    assert sub["info"]["last_name_or_org"] == "SMITH"
    assert sub["inquiries"][0]["service_type_codes"] == ["30"]


def test_all_types_supported():
    assert set(converter.supported_types()) >= {
        "270", "271", "276", "277", "834", "835", "837", "837I", "837P"
    }
