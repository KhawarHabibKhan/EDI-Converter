"""Post-deployment smoke test — run this against any deployed EDI-Converter.

Verifies the things that only break once the app is behind a real edge: TLS,
security headers, same-origin routing, upload limits, and every conversion and
validation endpoint. Standard library only, so it runs on a bare host, in CI, or
from a laptop with no install step.

    python smoke_test.py https://edi.example.com
    python smoke_test.py http://localhost:8091 --no-tls   # local/dev target

Exit code 0 = every check passed; 1 = at least one failed.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

# A minimal but genuinely valid 837P claim — enough to exercise the parser,
# the SNIP validator and the FHIR mapper end to end. No real patient data.
SAMPLE_837P = (
    "ISA*00*          *00*          *ZZ*SUBMITTER      *ZZ*RECEIVER       "
    "*240115*1200*^*00501*000000001*0*P*:~\n"
    "GS*HC*SUBMITTER*RECEIVER*20240115*1200*1*X*005010X222A1~\n"
    "ST*837*0001*005010X222A1~\n"
    "BHT*0019*00*244579*20240115*1023*CH~\n"
    "NM1*41*2*SUBMITTER CLINIC*****46*TGJ23~\n"
    "PER*IC*CONTACT*TE*5551112222~\n"
    "NM1*40*2*RECEIVER PAYER*****46*66783JJT~\n"
    "HL*1**20*1~\n"
    "NM1*85*2*SMITH CLINIC*****XX*1234567893~\n"
    "N3*100 MAIN ST~\n"
    "N4*ANYTOWN*OH*45209~\n"
    "REF*EI*123456789~\n"
    "HL*2*1*22*0~\n"
    "SBR*P*18*******CI~\n"
    "NM1*IL*1*DOE*JOHN****MI*MEMBER123~\n"
    "N3*200 OAK AVE~\n"
    "N4*ANYTOWN*OH*45209~\n"
    "DMG*D8*19800101*M~\n"
    "NM1*PR*2*ACME INSURANCE COMPANY*****PI*PAYER001~\n"
    "CLM*PATACCT001*150.00***11:B:1*Y*A*Y*Y~\n"
    "HI*ABK:J209~\n"
    "LX*1~\n"
    "SV1*HC:99213*150.00*UN*1***1~\n"
    "DTP*472*D8*20240110~\n"
    "SE*23*0001~\n"
    "GE*1*1~\n"
    "IEA*1*000000001~\n"
)

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


class Results:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.warned = 0

    def ok(self, name: str, detail: str = "") -> None:
        self.passed += 1
        print(f"  {GREEN}PASS{RESET}  {name}" + (f"  ({detail})" if detail else ""))

    def fail(self, name: str, detail: str) -> None:
        self.failed += 1
        print(f"  {RED}FAIL{RESET}  {name}\n          {detail}")

    def warn(self, name: str, detail: str) -> None:
        self.warned += 1
        print(f"  {YELLOW}WARN{RESET}  {name}\n          {detail}")


def request(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    insecure: bool = False,
) -> tuple[int, dict[str, str], bytes]:
    """Return (status, headers, body) — HTTP errors come back, not raised."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    ctx = ssl._create_unverified_context() if insecure else None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as res:  # noqa: S310
            return res.status, {k.lower(): v for k, v in res.headers.items()}, res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()


def multipart(field: str, filename: str, content: bytes) -> tuple[bytes, str]:
    """Build a multipart/form-data body (the upload endpoints all take one)."""
    boundary = f"----edismoke{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def post_edi(api: str, path: str, content: bytes, name: str = "claim.edi", **kw: Any):
    body, ctype = multipart("file", name, content)
    return request(f"{api}{path}", method="POST", data=body,
                   headers={"Content-Type": ctype}, **kw)


# --------------------------------------------------------------------------- #
#  Checks
# --------------------------------------------------------------------------- #
def check_tls(base: str, r: Results, insecure: bool) -> None:
    if not base.startswith("https://"):
        r.warn("TLS", "target is not https — skipping TLS and HSTS checks")
        return
    host = base.split("://", 1)[1].rstrip("/")
    status, headers, _ = request(f"http://{host}/", insecure=insecure)
    # Caddy answers plain HTTP with a redirect to HTTPS.
    if status in (301, 302, 307, 308):
        r.ok("HTTP redirects to HTTPS", f"{status} -> {headers.get('location', '?')}")
    else:
        r.fail("HTTP redirects to HTTPS", f"expected a 3xx redirect, got {status}")

    _, headers, _ = request(f"{base}/", insecure=insecure)
    if "strict-transport-security" in headers:
        r.ok("HSTS header", headers["strict-transport-security"])
    else:
        r.fail("HSTS header", "Strict-Transport-Security is missing")


def check_security_headers(base: str, r: Results, insecure: bool) -> None:
    _, headers, _ = request(f"{base}/", insecure=insecure)
    expected = {
        "content-security-policy": None,
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": None,
    }
    for header, want in expected.items():
        got = headers.get(header)
        if not got:
            r.fail(f"header {header}", "missing")
        elif want and got.lower() != want.lower():
            r.fail(f"header {header}", f"expected {want!r}, got {got!r}")
        else:
            r.ok(f"header {header}", got[:60] + ("…" if len(got) > 60 else ""))

    if "server" in headers and "caddy" in headers["server"].lower():
        r.warn("server header", f"leaks the server software: {headers['server']}")


def check_spa(base: str, r: Results, insecure: bool) -> None:
    status, _, body = request(f"{base}/", insecure=insecure)
    if status == 200 and b"<div id=\"root\">" in body:
        r.ok("SPA root serves", f"{len(body)} bytes")
    else:
        r.fail("SPA root serves", f"status {status}, {len(body)} bytes")

    # Deep link must fall back to index.html, not 404 — the /fhir route matters.
    status, _, _ = request(f"{base}/fhir", insecure=insecure)
    (r.ok if status == 200 else r.fail)(
        "SPA deep link /fhir", f"status {status}" if status != 200 else "200"
    )


def check_health(api: str, r: Results, insecure: bool) -> None:
    status, _, body = request(f"{api}/health", insecure=insecure)
    if status != 200:
        r.fail("API /health", f"status {status}")
        return
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        r.fail("API /health", "response was not JSON")
        return
    if payload.get("status") == "ok":
        r.ok("API /health", f"version {payload.get('version', '?')}")
    else:
        r.fail("API /health", f"unexpected payload {payload}")


def check_conversions(api: str, r: Results, insecure: bool) -> None:
    edi = SAMPLE_837P.encode()

    status, _, body = post_edi(api, "/edi/json", edi, insecure=insecure)
    if status == 200 and b"837P" in body:
        r.ok("POST /edi/json", "837P detected")
    else:
        r.fail("POST /edi/json", f"status {status}: {body[:160]!r}")

    for path, marker, label in (
        ("/edi/xml", b"<?xml", "POST /edi/xml"),
        ("/edi/csv", b"transaction", "POST /edi/csv"),
        ("/edi/fhir", b"\"resourceType\"", "POST /edi/fhir"),
    ):
        status, _, body = post_edi(api, path, edi, insecure=insecure)
        if status == 200 and marker in body:
            r.ok(label)
        else:
            r.fail(label, f"status {status}: {body[:160]!r}")


def check_validation(api: str, r: Results, insecure: bool) -> None:
    status, _, body = post_edi(api, "/edi/validate", SAMPLE_837P.encode(), insecure=insecure)
    if status != 200:
        r.fail("POST /edi/validate", f"status {status}: {body[:160]!r}")
        return
    report = json.loads(body)
    if report.get("snip_level") != 5:
        r.fail("SNIP validation level", f"expected snip_level 5, got {report.get('snip_level')}")
    elif not report.get("valid"):
        errors = [i["message"] for i in report["issues"] if i["severity"] == "ERROR"]
        r.fail("SNIP validation", f"a known-good claim was rejected: {errors[:3]}")
    else:
        r.ok("SNIP validation", f"level 5, clean claim passes all levels 1-5")

    # A deliberately broken envelope must be reported, not crash the service.
    broken = SAMPLE_837P.replace("SE*23*0001~", "SE*99*0001~").encode()
    status, _, body = post_edi(api, "/edi/validate", broken, insecure=insecure)
    if status == 200 and not json.loads(body)["valid"]:
        r.ok("Broken file is rejected", "segment-count error reported")
    else:
        r.fail("Broken file is rejected", f"status {status}, expected valid=false")


def check_limits(api: str, r: Results, insecure: bool) -> None:
    # Unsupported extension -> 400 with a useful message, not a 500.
    status, _, body = post_edi(api, "/edi/json", b"nonsense", name="payload.exe", insecure=insecure)
    if status == 400:
        r.ok("Rejects unsupported file type", "400")
    else:
        r.fail("Rejects unsupported file type", f"expected 400, got {status}: {body[:120]!r}")

    # Empty upload -> 400.
    status, _, _ = post_edi(api, "/edi/json", b"", insecure=insecure)
    (r.ok if status == 400 else r.fail)(
        "Rejects empty upload", "400" if status == 400 else f"expected 400, got {status}"
    )

    # Oversized upload -> 413 from the app, or 413 from the edge before it.
    oversized = b"ISA*00*" + (b"X" * (13 * 1024 * 1024))
    try:
        status, _, _ = post_edi(api, "/edi/json", oversized, insecure=insecure, timeout=120)
        if status == 413:
            r.ok("Rejects oversized upload", "413")
        else:
            r.fail("Rejects oversized upload", f"expected 413, got {status}")
    except (urllib.error.URLError, ConnectionError) as exc:
        # Some edges cut the connection instead of replying — acceptable.
        r.warn("Rejects oversized upload", f"connection closed by the edge ({exc})")


def check_no_phi_in_errors(api: str, r: Results, insecure: bool) -> None:
    """An error must never echo the uploaded content back to the caller."""
    marker = b"ZZPHIMARKERZZ"
    status, _, body = post_edi(api, "/edi/json", b"GARBAGE*" + marker + b"~", insecure=insecure)
    if marker in body:
        r.fail("Errors do not echo file content", f"upload content appeared in the {status} response")
    else:
        r.ok("Errors do not echo file content", f"status {status}, payload not reflected")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="e.g. https://edi.example.com")
    parser.add_argument("--api-path", default="/api",
                        help="path the API is mounted on (default: /api; use '' when hitting the backend directly)")
    parser.add_argument("--no-tls", action="store_true", help="skip TLS/HSTS checks")
    parser.add_argument("--insecure", action="store_true", help="accept self-signed certificates")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    api = f"{base}{args.api_path.rstrip('/')}"
    r = Results()

    print(f"\nSmoke-testing {base}  (API at {api})\n")

    groups: list[tuple[str, Callable[[], None]]] = [
        ("Transport", lambda: None if args.no_tls else check_tls(base, r, args.insecure)),
        ("Security headers", lambda: check_security_headers(base, r, args.insecure)),
        ("Static app", lambda: check_spa(base, r, args.insecure)),
        ("API health", lambda: check_health(api, r, args.insecure)),
        ("Conversions", lambda: check_conversions(api, r, args.insecure)),
        ("Validation", lambda: check_validation(api, r, args.insecure)),
        ("Input limits", lambda: check_limits(api, r, args.insecure)),
        ("PHI safety", lambda: check_no_phi_in_errors(api, r, args.insecure)),
    ]
    for title, run in groups:
        print(f"{title}:")
        try:
            run()
        except Exception as exc:  # noqa: BLE001 — a crashed check is a failed check
            r.fail(title, f"check raised {type(exc).__name__}: {exc}")
        print()

    print(f"{r.passed} passed, {r.failed} failed, {r.warned} warnings")
    if r.failed:
        print(f"{RED}DEPLOYMENT NOT VERIFIED{RESET}")
        return 1
    print(f"{GREEN}DEPLOYMENT VERIFIED{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
