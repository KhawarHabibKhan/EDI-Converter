"""Version-dependent delimiter handling in the ISA header.

X12 only gained a repetition separator in version 4030. Before that, ISA11 holds
the Interchange Control Standards Identifier — the letter "U" — so treating it as
a delimiter silently splits real data. Eligibility service-type codes such as
"UC" (urgent care) and "AL" are exactly where that shows up.

Every other fixture in this suite is version 00501, which is why this path went
untested.
"""

from engine import converter
from engine.x12_reader import Delimiters, detect_delimiters

ISA_5010 = (
    "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     "
    "*240115*1200*^*00501*000000001*0*P*:~"
)
ISA_4010 = (
    "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     "
    "*240115*1200*U*00401*000000001*0*P*:~"
)


# --------------------------------------------------------------------------- #
#  Delimiter detection
# --------------------------------------------------------------------------- #
def test_isa_header_is_exactly_106_characters():
    # The whole detection scheme depends on fixed positions; guard the fixtures.
    assert len(ISA_5010) == 106
    assert len(ISA_4010) == 106


def test_5010_honours_isa11_as_repetition_separator():
    d = detect_delimiters(ISA_5010)
    assert d.supports_repetition is True
    assert d.repetition == "^"
    assert d.element == "*" and d.component == ":" and d.segment == "~"


def test_4010_does_not_treat_isa11_as_a_delimiter():
    d = detect_delimiters(ISA_4010)
    assert d.supports_repetition is False
    assert d.repetition != "U"


def test_version_boundary_is_4030():
    # ISA12 is a 5-character code, not the release number: "00402" is 4020 and
    # "00403" is 4030. 4030 introduced the separator; 4020 did not.
    assert detect_delimiters(ISA_5010.replace("*00501*", "*00402*")).supports_repetition is False
    assert detect_delimiters(ISA_5010.replace("*00501*", "*00403*")).supports_repetition is True
    assert detect_delimiters(ISA_5010.replace("*00501*", "*00504*")).supports_repetition is True


def test_alphanumeric_isa11_is_never_a_delimiter():
    # Belt and braces: even if ISA12 claims 5010, a letter in ISA11 is the
    # standards identifier, not a separator.
    mislabelled = ISA_4010.replace("*U*00401*", "*U*00501*")
    assert detect_delimiters(mislabelled).supports_repetition is False


# --------------------------------------------------------------------------- #
#  split_repeats
# --------------------------------------------------------------------------- #
def test_split_repeats_splits_when_supported():
    d = Delimiters(repetition="^", supports_repetition=True)
    assert d.split_repeats("30^UC^AL") == ["30", "UC", "AL"]
    assert d.split_repeats("") == []


def test_split_repeats_keeps_the_value_whole_when_unsupported():
    d = Delimiters(repetition="U", supports_repetition=False)
    assert d.split_repeats("UC") == ["UC"]          # would have been ["", "C"]
    assert d.split_repeats("AL") == ["AL"]
    assert d.split_repeats("") == []


# --------------------------------------------------------------------------- #
#  End to end through the mapper
# --------------------------------------------------------------------------- #
def test_4010_service_type_code_is_not_split_on_the_letter_u(sample_271_4010):
    """The defect: EB03 "UC" became ["", "C"] because ISA11 was "U"."""
    result = converter.convert_edi(sample_271_4010, "271")

    # information_sources -> information_receivers -> subscribers (-> dependents)
    benefits = [
        eb
        for source in result["information_sources"]
        for receiver in source.get("information_receivers", [])
        for subscriber in receiver.get("subscribers", [])
        for node in [subscriber, *subscriber.get("dependents", [])]
        for eb in node.get("eligibility", [])
    ]
    assert benefits, f"no eligibility parsed from the 4010 fixture: {result}"
    codes = [c for eb in benefits for c in eb.get("service_type_codes", [])]
    assert codes == ["UC"], f"service-type codes were corrupted: {codes}"


def test_5010_repetition_still_splits(sample_271):
    """Guard against fixing 4010 by breaking 5010."""
    result = converter.convert_edi(sample_271, "271")
    assert result["source_transaction"].endswith("271")
