# Case Study — Replacing a licensed EDI engine with one we own

A healthcare claims tool was built on a commercial, closed-source EDI engine
shipped as a licensed Docker image. We rebuilt the engine in-house, then took it
further than the original went — five levels of claim validation and FHIR R4
output — and put it on a $4.50/month box.

| | | | |
|---|---|---|---|
| **8** | **180** | **152/s** | **$0** |
| X12 transaction types supported | Automated tests, all passing | Claims validated per second, 1 vCPU | Licence cost, down from commercial |

---

## Page 1

### The problem

Healthcare runs on X12 EDI — claims, remittances, eligibility checks. The format
is machine-readable and human-hostile: a single claim is a wall of
asterisk-delimited segments where a misplaced count invalidates the file. The
existing setup handled this with a third-party engine distributed as a licensed
container. That created three problems at once.

- **No control.** The engine was a black box. Its output schema was theirs, its
  bugs were theirs to fix, and its roadmap was theirs to set.
- **Licence exposure.** Commercial terms and per-deployment cost for what is, at
  bottom, a text parser.
- **A validation ceiling.** It confirmed files were structurally readable. It did
  not tell you whether a payer would *accept* them — which is the question that
  actually costs money when the answer is no.

### The approach

We built our own engine in three deliberate stages, each shipped before the next
began.

#### Own the parser

A hand-built X12 reader and one mapper per transaction type, in Python with
**zero third-party EDI dependencies**. All eight types — 837P, 837I, 835, 834,
270, 271, 276, 277 — convert to JSON, XML or CSV through a shared serializer.
Auto-detection reads the file and decides the type itself.

#### Answer the question that matters

Structural validity is table stakes. The industry's actual standard is the **WEDI
SNIP levels**, and we implemented all five: envelope integrity,
implementation-guide requirements, financial balancing, situational "if A then B"
rules, and code-set membership against real ICD-10-CM, ICD-10-PCS, HCPCS and
place-of-service lists. Levels are cumulative and selectable, and every issue is
labelled with the level that raised it.

Level 3 is where this earns its keep. It does exact decimal arithmetic on the
money: claim total against the sum of service lines, remittance payments against
line items and provider-level adjustments. These are the failures that get a claim
rejected weeks later, and they are invisible to a structural check.

#### Speak the modern format

Every transaction type also converts to a **FHIR R4 Bundle** — `Claim`,
`ExplanationOfBenefit`, `Coverage`, `CoverageEligibilityResponse`, `Task` — so the
same files feed modern clinical systems without a second integration. The FHIR
path accepts the app's own JSON and XML exports as input, not just raw X12.

> **Design constraint held throughout.** Zero runtime dependencies beyond the web
> framework, and no PHI persistence. Files are parsed in memory and discarded — no
> database, no storage bucket, no retention policy to defend. That single decision
> removed most of the compliance surface before it existed.

---

## Page 2

### What verification found

Two independent checks were added late, and both immediately paid for themselves —
which is the useful part of the story, because it says something about the
difference between "our tests pass" and "this is correct".

**The official HL7 validator caught four real defects.** Our own FHIR validator
said the Bundles were clean. Running HL7's reference implementation in CI
disagreed: entries were missing `fullUrl`, so *every* internal reference was
unresolvable; ICD-10 codes were emitted without their decimal point, making them
invalid codes; an element was being written that does not exist on that resource;
and one resource violated a FHIR invariant. All four are now fixed, with
regression tests, and the Bundles validate clean.

**A container audit found bytecode from the wrong Python.** A `.dockerignore`
pattern that looked correct silently matched only the top directory, so local
`__pycache__` folders were shipping into the image — Python 3.14 bytecode inside a
Python 3.11 container. Fixing the patterns cut the application layer by 53%.

### Results

| Measure | Before | After | Change |
|---------|-------:|------:|-------:|
| Backend image size | 260 MB | 127 MB | **−51%** |
| Frontend image size | 93 MB | 81.7 MB | **−12%** |
| HIGH/CRITICAL CVEs in images | 2 | 0 | **cleared** |
| Automated tests | 51 | 180 | **+253%** |
| Validation depth | SNIP L1 | SNIP L1–5 | **+4 levels** |
| Output formats | JSON | JSON/XML/CSV/FHIR | **+3** |
| Engine licence | commercial | none | **removed** |

### Measured performance

Load-tested through the production edge against a CPU-limited container, using a
real 837P claim:

| Endpoint | Concurrency | Throughput | p95 | Errors |
|----------|------------:|-----------:|----:|-------:|
| Validate (SNIP L1–5) | 8 | 152 req/s | 94 ms | 0 |
| Validate (SNIP L1–5) | 32 | 213 req/s | 231 ms | 0 |
| Convert to FHIR | 8 | 233 req/s | 51 ms | 0 |

One small container absorbs roughly **150 claims per second** with sub-100 ms p95
latency — comfortably hundreds of thousands of conversions a day. Throughput is
CPU-bound, so the sizing guidance is to add CPU before adding replicas.

### What it costs to run

Both containers are multi-stage, run as non-root with read-only filesystems, and
carry no HIGH or CRITICAL vulnerabilities. That makes the hosting question
genuinely cheap:

- **~$4.50/month** — one small VPS running the whole stack with automatic TLS.
  One machine, one compose file.
- **~$0–5/month** — static frontend on a free tier plus a scale-to-zero API,
  which bills only while it is actually serving.

### Security verification

| Check | Tool | Result |
|-------|------|--------|
| Secrets in code and git history | gitleaks | 52 commits scanned, **no leaks** |
| Automated penetration test | OWASP ZAP baseline | **0 failures**, 5 warnings, 62 passes |
| Container vulnerabilities | Trivy | **0 HIGH/CRITICAL**, both images |
| Deployment verification | bundled smoke test | **17/17 checks pass** |

### Honest limitations

The system has **no authentication, no rate limiting and no audit logging**. For
an internal tool behind a VPN that is a reasonable trade; for a public deployment
handling real patient data it is not, and the deployment runbook says so plainly
rather than burying it. The bundled code sets are seed subsets pending a swap for
the full CMS lists, and CPT membership is deliberately unchecked pending AMA
licensing — the report states this rather than passing silently. FHIR output
conforms to base R4; certification against the US Core and CARIN Blue Button
profiles runs in CI as an advisory step and is not yet a pass. The backend also
has no dependency lock file, so Python CVE scanning is currently blind and builds
are not byte-reproducible.

> **The transferable lesson.** Two of the most valuable defects in this project
> were found not by writing more tests, but by pointing an *independent*
> implementation at the output — HL7's validator at the FHIR Bundles, a container
> scanner at the images. Your own tests encode your own assumptions. Someone
> else's tool does not.

---

*Every figure here was measured on the delivered system: image sizes from
`docker images`, CVE counts from Trivy, throughput from the bundled load-test
harness, test counts from the suite.*
