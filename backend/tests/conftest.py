"""Shared test fixtures and path helpers."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8-sig")


@pytest.fixture
def sample_837p() -> str:
    return read_fixture("sample_837p.edi")


@pytest.fixture
def all_fields_837p() -> str:
    return read_fixture("837P-all-fields.dat")


@pytest.fixture
def sample_837i() -> str:
    return read_fixture("837I-sample.edi")


@pytest.fixture
def sample_835() -> str:
    return read_fixture("835-sample.edi")


@pytest.fixture
def sample_834() -> str:
    return read_fixture("834-sample.edi")


@pytest.fixture
def sample_271() -> str:
    return read_fixture("271-sample.edi")


@pytest.fixture
def sample_270() -> str:
    return read_fixture("270-sample.edi")


@pytest.fixture
def sample_271_4010() -> str:
    """A pre-4030 interchange: ISA11 is the standards identifier "U", not a
    repetition separator. Every other fixture is 00501, so this is the only one
    that exercises the version-dependent delimiter path."""
    return read_fixture("271-4010-sample.edi")


@pytest.fixture
def sample_277() -> str:
    return read_fixture("277-sample.edi")
