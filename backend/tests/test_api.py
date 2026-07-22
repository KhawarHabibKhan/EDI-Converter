"""API-level tests using FastAPI's TestClient."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "edi-converter"


def test_root_points_to_docs():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "docs" in resp.json()["message"].lower()


def test_edi_json_conversion():
    from tests.conftest import read_fixture

    content = read_fixture("sample_837p.edi").encode("utf-8")
    resp = client.post(
        "/edi/json?type=837P",
        files={"file": ("sample_837p.edi", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["file_name"] == "sample_837p.edi"
    assert body["data"]["claim_count"] == 1
    assert body["data"]["claims"][0]["total_charge"] == "350.00"


def test_edi_xml_conversion():
    from tests.conftest import read_fixture

    content = read_fixture("sample_837p.edi").encode("utf-8")
    resp = client.post(
        "/edi/xml?type=837P",
        files={"file": ("sample_837p.edi", content, "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    body = resp.text
    assert body.startswith('<?xml')
    assert "<total_charge>350.00</total_charge>" in body


def test_edi_json_auto_detect():
    from tests.conftest import read_fixture

    content = read_fixture("sample_837p.edi").encode("utf-8")
    resp = client.post(  # no type → defaults to auto
        "/edi/json",
        files={"file": ("sample_837p.edi", content, "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["source_transaction"] == "ANSI X12 837P"


def test_edi_json_unsupported_type_returns_400():
    # 999 (functional acknowledgment) is not a mapped type → friendly 400.
    edi = (
        "ISA*00*          *00*          *ZZ*SUB            *ZZ*REC            "
        "*240115*1200*^*00501*000000001*0*P*:~ST*999*0001~"
    ).encode("utf-8")
    resp = client.post(
        "/edi/json?type=auto",
        files={"file": ("ack.edi", edi, "text/plain")},
    )
    assert resp.status_code == 400
    assert "999" in resp.json()["detail"]


def test_edi_csv_conversion():
    from tests.conftest import read_fixture

    content = read_fixture("sample_837p.edi").encode("utf-8")
    resp = client.post("/edi/csv", files={"file": ("s.edi", content, "text/plain")})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "patient_account_no" in resp.text


def test_edi_validate_clean_file():
    from tests.conftest import read_fixture

    content = read_fixture("sample_837p.edi").encode("utf-8")
    resp = client.post("/edi/validate", files={"file": ("s.edi", content, "text/plain")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["error_count"] == 0


def test_edi_json_rejects_empty_file():
    resp = client.post(
        "/edi/json",
        files={"file": ("empty.edi", b"", "text/plain")},
    )
    assert resp.status_code == 400


def test_edi_json_rejects_bad_extension():
    resp = client.post(
        "/edi/json",
        files={"file": ("claim.pdf", b"ISA*00*", "application/pdf")},
    )
    assert resp.status_code == 400
