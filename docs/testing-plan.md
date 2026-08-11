# EDI-Converter — Testing Plan

What is tested today, what is not, and exactly what must go green before a release
reaches users. Written to be executed, not filed.

| | | | |
|---|---|---|---|
| **180** | **17** | **0** | **0** |
| Automated tests passing | Deployment smoke checks | HIGH/CRITICAL image CVEs | Frontend / E2E tests — the gap |

---

## Scope

Seven layers, ordered from the fastest and cheapest to the slowest. Each names the
command that runs it, what "pass" means, and whether it exists yet. Two layers are
marked as gaps — they are the honest state of the project, not oversights.

| Layer | What it proves | Runtime | Status |
|-------|----------------|--------:|--------|
| 1 · Unit | Mappers, validators, code sets are correct | ~3 s | ✅ 180 tests |
| 2 · Integration | HTTP endpoints behave through the real app | included | ✅ covered |
| 3 · Conformance | FHIR output passes the official HL7 validator | ~2 min | ✅ in CI |
| 4 · Container | Images are minimal, non-root, CVE-free | ~3 min | ✅ verified |
| 5 · Deployment | A live URL actually works, with TLS and headers | ~30 s | ✅ 17 checks |
| 6 · Performance | Throughput and latency under concurrency | ~1 min | ✅ harness |
| 7 · Frontend / E2E | The UI works for a real user | — | ❌ not built |

---

## Layers 1–2 — Unit and integration

**Backend suite — 180 passing**

```bash
cd backend && python -m pytest -q
```

Covers every mapper against real fixture files for all eight transaction types, all
five SNIP levels including deliberately broken copies, the FHIR resource mappers,
the input adapter and XML round-trip, and every HTTP endpoint through FastAPI's
test client. Meaningful coverage, not a percentage target: each SNIP rule has both
a clean case and a failing case that asserts the exact issue and its level.

**Pass:** 180/180. Any failure blocks the release.

### Where to add tests first

When a defect is found, the fix is not done until a test would have caught it.
Priority order for new coverage:

- A new SNIP rule needs a clean-and-broken pair.
- A new transaction type needs a fixture plus mapper assertions.
- A parser change needs a round-trip assertion through JSON **and** XML.

---

## Layer 3 — FHIR conformance

**Official HL7 validator — in CI**

```bash
python scripts/export_fhir_bundles.py build/fhir
java -jar validator_cli.jar build/fhir -version 4.0.1 -output outcome.json
python scripts/check_fhir_conformance.py outcome.json
```

Exports a Bundle from every fixture and validates it with HL7's reference
implementation. **Base R4 is a hard gate.** The verdict comes from the checker
script rather than the validator's exit code, so that CPT "unknown code" findings
are waived — CPT is AMA-licensed and HL7 ships only a fragment of it, so gating on
that would tie the build to whichever codes HL7 happens to bundle. Every other
error fails.

US Core and CARIN Blue Button profiles run as an *advisory* step. They are not a
pass yet and are not claimed to be.

**Pass:** zero blocking conformance errors; waived findings printed, not hidden.

> **Why this layer exists.** It found four real defects our own validator had
> approved: missing `fullUrl` on Bundle entries (making every internal reference
> unresolvable), undotted ICD-10-CM codes, an element written to a resource that
> does not define it, and a violated FHIR invariant. Independent implementations
> catch what your own assumptions cannot.

---

## Layer 4 — Container

**Image audit — verified**

```bash
docker compose build
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image --severity HIGH,CRITICAL edi-converter-backend
```

Assertions, each independently checkable:

- Both containers run as a **non-root** user (backend uid 1001, frontend uid 101).
- **Read-only** root filesystem with a `noexec,nosuid` tmpfs for `/tmp`.
- `cap_drop: ALL` and `no-new-privileges` confirmed via `docker inspect`.
- No test framework, no `__pycache__`, no markdown in the image.
- Zero HIGH or CRITICAL CVEs.
- A >1 MB upload succeeds against the read-only filesystem — proving the tmpfs
  spool works.

**Pass:** all six hold. Sizes: backend 127 MB, frontend 81.7 MB.

---

## Layer 5 — Deployment verification

**Smoke test — 17 checks**

```bash
python deploy/smoke_test.py https://edi.example.com
```

Run this against *every* deployment, immediately after it goes up. It tests the
things that only break behind a real edge, and exits non-zero if any fail:

- **Transport** — HTTP redirects to HTTPS, HSTS present.
- **Headers** — CSP, `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  Referrer-Policy.
- **Routing** — SPA root and the `/fhir` deep link both resolve; the API answers
  under `/api`.
- **Function** — JSON, XML, CSV and FHIR conversions all return correct content.
- **Validation** — a known-good claim passes all five SNIP levels; a corrupted
  copy is rejected.
- **Limits** — wrong file type → 400, empty upload → 400, oversized upload → 413.
- **PHI safety** — an error response never echoes uploaded content back.

**Pass:** 17/17, printed as `DEPLOYMENT VERIFIED`.

### Rehearse the production topology locally

Same compose file, same edge, no certificate needed:

```bash
cd deploy
SITE_ADDRESS=":80" ACME_EMAIL="test@example.com" HTTP_PORT=8088 HTTPS_PORT=9443 \
  docker compose -f docker-compose.prod.yml up -d --build
python smoke_test.py http://localhost:8088 --no-tls
```

---

## Layer 6 — Performance

**Load test — harness**

```bash
python deploy/load_test.py https://edi.example.com --concurrency 8 --requests 400
```

Exits non-zero above a configurable error budget (default 1%), so it can gate a
release. Baseline, measured through the production edge on a 1-vCPU container:

| Endpoint | Conc. | req/s | p50 | p95 | p99 | Errors |
|----------|------:|------:|----:|----:|----:|-------:|
| `/edi/validate` | 8 | 152 | 47 ms | 94 ms | 125 ms | 0 |
| `/edi/validate` | 32 | 213 | 132 ms | 231 ms | 276 ms | 0 |
| `/edi/fhir` | 8 | 233 | 32 ms | 51 ms | 58 ms | 0 |

**Regression budget:** throughput must stay within 20% of this baseline and p95
under 150 ms at concurrency 8. Re-measure after any parser or validator change —
that is where a quadratic loop would show up first.

---

## Layer 7 — The gap: frontend and E2E

**Not built — highest-value gap**

There are zero frontend tests. Every UI behaviour is verified by hand today:
drag-and-drop, the debounced auto-validation, the loading race-guard, the maximize
overlay, batch upload, and the Forward-to-FHIR hand-off. The race-guard is the
risky one — it exists specifically to stop auto-validation overwriting a user's
conversion result, and a regression there would be invisible to the backend suite.

**Recommended, in priority order:**

1. **Component tests** (Vitest + Testing Library — Vitest is already a dependency):
   result panel rendering per output format, issue-card rendering per SNIP level,
   the validity chip.
2. **E2E** (Playwright, ~4 specs): upload → convert → download; auto-validation
   showing a report; batch upload; Forward to FHIR.
3. **Cross-browser**: run the E2E specs on Chromium, Firefox and WebKit — the
   drag-and-drop and clipboard paths are where they diverge.

---

## The release gate

Nothing ships until every line here is green. Security items are blockers, not
preferences.

- [ ] **180/180 backend tests pass** — `pytest -q`
- [ ] **Frontend builds clean** — `tsc -b && vite build`, no type errors
- [ ] **FHIR conformance gate green** — zero blocking errors from the HL7 validator
- [ ] **Images rebuilt and scanned** — zero HIGH/CRITICAL, non-root confirmed
- [ ] **Production topology rehearsed locally** — smoke test 17/17 against the prod
      compose file
- [ ] **Deployed, then smoke-tested against the live URL** — TLS, headers, all
      endpoints
- [ ] **Load test within budget** — ≤20% throughput regression, p95 < 150 ms
- [ ] **Rollback rehearsed** — previous image tag redeployable; `caddy_data` volume
      intact

---

## Testing that does not yet apply

These layers are deliberately absent because the features they would test do not
exist. Listing them here keeps the gap visible rather than implied.

| Test area | Blocked by | Status |
|-----------|------------|--------|
| Authentication / authorization tests | No auth exists | 🔴 blocker for PHI |
| Rate-limit / brute-force tests | No throttling exists | 🔴 blocker for PHI |
| Audit-log assertions | No audit logging exists | 🔴 blocker for PHI |
| Penetration test (ZAP / Burp) | Should follow the three above | ✅ ZAP baseline run: 0 fail, 5 warn, 62 pass |
| Python dependency CVE scan | `requirements.txt` has no pinned versions | ⚠️ blind until pinned |
| Third-party data-flow review | Fonts load from a Google CDN | ⚠️ self-host first |

Until the first three land, this system is testable and shippable as an **internal
tool on a trusted network**, and is not ready for a public deployment carrying live
patient data.

---

*Every number in this plan was measured on the delivered system. Layer commands are
copy-pasteable; the scripts live in [`deploy/`](../deploy/) and
[`backend/scripts/`](../backend/scripts/).*
