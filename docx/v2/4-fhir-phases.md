# v2 · 4 — FHIR Phases

> **Project:** EDI-Converter — Version 2 (FHIR R4)
> **Last updated:** 2026-07-23
> Build in order. Each phase ships on its own. Track status in `6-fhir-memory.md`.

---

## V2-A — 837 → `Claim`, end to end  *(proof-of-pattern)*

Stand up the **entire pipeline** on our richest transaction (837), so all the
plumbing exists and later resources are "just another mapper".

**Backend**
- **A.1** `engine/input_adapter.py` — detect `.edi/.dat` vs `.json` vs `.xml`,
  return `(normalized dict, transaction_type)`.
- **A.2** `engine/xml_reader.py` — our-schema XML → dict (reverse of `xml_writer`).
- **A.3** `engine/fhir/common.py` — `Reference`/`Identifier`/`CodeableConcept`/
  money/name builders + the code-system URI table.
- **A.4** `engine/fhir/map_claim.py` — 837P/837I dict → `Claim` (+ `Patient`,
  `Coverage`, `Organization`) as a resource list.
- **A.5** `engine/fhir/writer.py` — dispatch by type; assemble the **Bundle**.
- **A.6** `POST /edi/fhir` in `main.py` (widen upload allow-list to `.json/.xml`).
- **A.7** Tests: 837 EDI **and** its v1 JSON/XML round-trip → Bundle with
  `Claim` + referenced resources; structural FHIR checks; input-adapter tests.

**Frontend**
- **A.8** Add `react-router-dom`; wrap in `<BrowserRouter>`; routes `/` and `/fhir`.
- **A.9** Refactor existing UI into `pages/ConverterPage.tsx` (no behavior change).
- **A.10** `pages/FhirPage.tsx` — reuse layout; accept `.edi/.dat/.json/.xml`;
  `convertFhir` API call; render FHIR JSON; badge `FHIR · Claim`.
- **A.11** Top-nav (Converter · FHIR Converter).

**Done when:** on `/fhir`, uploading an 837 file **or its v1 JSON/XML** returns a
valid FHIR **Bundle** centered on a `Claim`; v1 page unchanged; tests green.

---

## V2-B — 835 → `ExplanationOfBenefit`

- **B.1** `engine/fhir/map_eob.py` — 835 dict → `ExplanationOfBenefit`
  (+ Patient, Coverage, Organization). Map CLP totals, SVC lines → `item`,
  CAS adjustments → `item.adjudication`, PLB → process-level adjustment.
- **B.2** Register in `fhir/writer.py`; FhirPage handles it automatically.
- **B.3** Tests against the 835 sample.

**Done when:** 835 (or its JSON/XML) → Bundle with an `ExplanationOfBenefit`.

---

## V2-C — the remaining resources

- **C.1** `map_coverage.py` — 834 → `Coverage` (member, payer, plan, dates).
- **C.2** `map_eligibility.py` — 270 → `CoverageEligibilityRequest`,
  271 → `CoverageEligibilityResponse` (EB/EQ → `insurance.item`).
- **C.3** `map_task.py` — 276/277 → `Task` (claim-status trace + STC status).
- **C.4** Tests for each against the existing samples.

**Done when:** all 8 transaction types have a FHIR mapping.

---

## V2-D — FHIR profile validation upgrade

- **D.1** Replace "reuse existing validator" with real **FHIR profile validation**
  (CARIN Blue Button / US Core / Da Vinci) — a FHIR validator run in CI/tests.
  ✅ **done 2026-08-11** — `.github/workflows/ci.yml` job `fhir-conformance` runs
  the **official HL7 validator** (`validator_cli.jar`) over a Bundle exported from
  every fixture by `backend/scripts/export_fhir_bundles.py`.
- **D.2** Report FHIR conformance issues (structure, required fields, bindings).
  ✅ done — at runtime by `engine/fhir/validator.py` (base R4, zero-dep) and in CI
  by the reference implementation.
- **D.3** Optionally expose a "FHIR validate" mode in the UI. ✅ done — the `/fhir`
  page auto-validates and shows a **SNIP + FHIR R4** chip.

**Done when:** generated Bundles pass the targeted IG profiles in CI.

> **Status — split gate (2026-08-11).** The CI job enforces **base FHIR R4 as a
> hard gate** (it fails the build) and runs **US Core + CARIN Blue Button as an
> advisory step**. Our mappers emit conformant base-R4 resources but do not yet
> declare `meta.profile` or carry the IGs' must-support slices, so the profile
> run is a backlog report, not a pass. Full IG certification = flip
> `continue-on-error: false` once that enrichment lands (§6.5 of the memory doc).
> The base-R4 gate is not a formality: standing it up immediately exposed two
> real defects our own validator had missed — see the memory doc.

---

### Dependency map
```
V2-A ─► V2-B ─► V2-C ─► V2-D
  │
  └─ (A builds the pipeline: adapter, xml_reader, fhir/writer, /edi/fhir, /fhir page)
     B and C are "just another resource mapper" once A exists.
```
