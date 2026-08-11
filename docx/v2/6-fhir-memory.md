# v2 · 6 — FHIR Project Memory (Living Progress Log)

> **Project:** EDI-Converter — Version 2 (FHIR R4)
> **Last updated:** 2026-07-23
>
> Read this FIRST before working on v2. Update it whenever something is started,
> completed, or decided. Single source of truth for "where is v2?".

---

## 6.1 Status
- **v1:** complete (Phases 0–9). All 8 X12 types → JSON/XML/CSV, auto-validation,
  batch, maximize. 51 tests. See `../6-memory.md`.
- **v2 (FHIR): ALL PHASES COMPLETE (V2-A → V2-D).** All 8 X12 types convert to
  FHIR R4 Bundles, with automated FHIR structural validation.
  - V2-A: 837P/837I → `Claim` Bundle, end to end (adapter + fhir package +
    `/edi/fhir`; `/fhir` page with React Router). Accepts `.edi/.dat` **and** our
    JSON/XML exports.
  - V2-B: 835 → `ExplanationOfBenefit` (CAS → `adjudication`, BPR/TRN →
    `payment`, PLB → `processNote`).
  - V2-C: 834 → `Coverage`; 270 → `CoverageEligibilityRequest`; 271 →
    `CoverageEligibilityResponse` (+ derived Request/Coverage stubs so required
    refs resolve); 276/277 → `Task`.
  - V2-D: hand-built FHIR R4 structural validator (`engine/fhir/validator.py`) +
    `POST /edi/fhir/validate` + automated validity chip on the `/fhir` page.
    Base-R4 structure (required elements, value sets, reference integrity,
    coding hygiene). It already caught a real bug — missing `Claim.created`
    (now populated from the BHT/GS date). **Official IG certification (CARIN /
    US Core / Da Vinci via the HL7 validator) remains a CI follow-up** — see
    §6.5.
  - Backend suite now **106 tests** (was 51). Frontend build green.

## 6.2 Locked decisions
| # | Decision | Choice |
|---|----------|--------|
| 1 | JSON/XML input = our own v1 output (round-trip) | ✅ Yes |
| 2 | First resource, built end-to-end | **837 → `Claim`** |
| 3 | Frontend routing | **React Router** (`/`, `/fhir`) |
| 4 | Runtime dependencies | **Hand-built FHIR, zero new deps** |
| 5 | Validation (v2) | **Reuse existing validator**; FHIR profile validator = V2-D upgrade |
| 6 | Output shape | **FHIR Bundle** (`type: collection`) |

## 6.3 Progress by phase
| Phase | Description | Status |
|-------|-------------|--------|
| V2-A | 837 → `Claim` end-to-end (adapter, xml_reader, fhir pkg, /edi/fhir, /fhir page) | ✅ Done |
| V2-B | 835 → `ExplanationOfBenefit` (`map_eob.py`) | ✅ Done |
| V2-C | 834 → `Coverage`; 270/271 → CoverageEligibility; 276/277 → `Task` | ✅ Done |
| V2-D | FHIR structural validator + `/edi/fhir/validate` + UI chip + **official HL7 validator in CI** | ✅ Done (base R4 hard gate; IG profiles advisory) |

Legend: ⬜ Not started · 🟨 In progress · ✅ Done

## 6.4 Which component / feature next
- **v2 core is complete.** No open build work. Candidate follow-ups:
  1. **V2-D+ (CI):** wire the official HL7 FHIR validator against the CARIN
     Blue Button / US Core / Da Vinci packages in CI for true IG certification
     (our runtime validator is base-R4 structural only, by design/zero-dep).
  2. Enrich mappings toward those profiles (must-support slices) once (1) exists.
  3. Optional: a dedicated FHIR-bundle *upload-and-validate* mode (validate an
     externally-produced Bundle, not just ones we generate).
- **No X12 parser/mapper changes** — FHIR consumes the existing v1 dict.

### What V2-C/D shipped (files)
- Backend: `engine/fhir/{map_coverage,map_eligibility,map_task,validator}.py`;
  8 code-system URIs added to `common.py`; all 8 types registered in `writer.py`
  (`_PLANNED` now empty); `Claim.created` now populated from the header;
  `POST /edi/fhir/validate` in `main.py`.
- Tests: `tests/test_fhir_c.py`, `tests/test_fhir_validate.py` (106 total green).
- Frontend: `validateFhir` client + automated **Valid FHIR R4** validity chip on
  the `/fhir` page.

### FHIR page auto-validation (parity with the Converter page)
- The `/fhir` page now **auto-validates on input change** (debounced ~600ms +
  ~2.2s aesthetic window), exactly like the Converter page — no Convert click
  needed. Shows the report in the result panel (when not showing a Bundle) **and**
  a validity chip in the Source header. Uses the same `validateCanOwn` race-guard
  + `source:"validate"` loading tag and a "clear stale Bundle on input change"
  effect. `run()` no longer triggers validation itself; forwarded hand-offs get
  auto-validated too. Files: `pages/FhirPage.tsx` (`VALIDATE_MIN_MS`, two effects).

### `/edi/fhir/validate` now validates **source + output** (SNIP + FHIR)
- **Problem fixed:** the FHIR page used to validate only the generated Bundle's
  R4 structure, so a SNIP-broken 837 (missing service line, bad amount) still
  produced a structurally-valid Bundle and **passed** — inconsistent with the
  Converter page, which flagged it. The mappers are lenient (`.get()` + `prune`),
  so Bundle-only validation misses source defects.
- **Fix:** `/edi/fhir/validate` now runs **both**: (1) when the input is raw X12
  EDI, the **same SNIP validation** as `/edi/validate` (levelled issues, tagged
  `stage:"snip"`); (2) the FHIR R4 Bundle structure check (`stage:"fhir"`).
  JSON/XML exports skip SNIP (only raw X12 has an envelope). If EDI can't build a
  Bundle, SNIP findings are still returned + a `stage:"fhir"` build-failure note.
  Report gains `transaction_type` + `snip_level`; each issue carries `stage`.
- Frontend: the validation view badges `stage:"fhir"` issues as **FHIR** and
  SNIP issues as **L1/L2**; the chip reads "Valid — SNIP + FHIR R4". Files:
  `main.py` (`/edi/fhir/validate`), `input_adapter.detect_format`,
  `components/ResultPanel.tsx`, `api/client.ts`, `pages/FhirPage.tsx`.
  Tests: `tests/test_fhir_validate.py` (broken-EDI surfaces SNIP errors). 128 total.

### "Forward to FHIR" hand-off (added after V2-D)
- Converter result panel has a **Forward to FHIR** button, **enabled only for
  JSON/XML** output. It navigates to `/fhir` (React Router `state`) and
  **prefills** the FHIR input with that output — it does **not** auto-convert;
  the user clicks Convert themselves.
- Files: shared `components/ResultPanel.tsx` gains an `onForward` prop + the
  button; `pages/ConverterPage.tsx` passes `forwardToFhir` (uses `useNavigate`);
  `pages/FhirPage.tsx` reads the router state once on mount, sets the input +
  file name, resets the result, and clears the state. CSS: `.forward-bar` /
  `.forward-btn`. No backend change — reuses `/edi/fhir` when the user converts.

### What V2-A shipped (files)
- Backend: `engine/fhir/{__init__,common,map_claim,writer}.py`,
  `engine/xml_reader.py`, `engine/input_adapter.py`, `POST /edi/fhir` in
  `main.py` (upload allow-list widened to `.json/.xml` for that route only).
- Tests: `tests/test_fhir_claim.py`, `tests/test_input_adapter.py`,
  `tests/test_xml_reader.py` (77 total, all green).
- Frontend: `react-router-dom` added; `main.tsx` wraps `<BrowserRouter>`;
  `App.tsx` = shell (aurora + `<Routes>`); `pages/ConverterPage.tsx` (v1 UI
  moved, unchanged behavior) + `pages/FhirPage.tsx` (new); shared
  `components/{Header,ResultPanel}.tsx` + `lib/theme.ts`; nav + `.fhir-note` CSS.
  nginx SPA fallback already present (deep-link `/fhir` works).

### V2-D completion — official HL7 validator in CI (2026-08-11)
The D.1 acceptance criterion ("a FHIR validator run in CI/tests") had never been
built — there was no CI at all. It exists now:

- **`.github/workflows/ci.yml`** — three jobs: `backend-tests` (pytest),
  `frontend-build` (tsc + vite), and **`fhir-conformance`**, which exports a
  Bundle per fixture (`backend/scripts/export_fhir_bundles.py`) and runs the
  **official `validator_cli.jar`** over them.
- **Split gate.** Base R4 is a **hard gate**; US Core + CARIN Blue Button run
  **advisory**.
- **The verdict is computed, not taken from the exit code.**
  `backend/scripts/check_fhir_conformance.py` reads the validator's
  `OperationOutcome` (or its text report — both are handled) and fails on every
  error **except** CPT "unknown code" findings. Reason: CPT is AMA-licensed, so
  HL7 bundles only a *fragment* — "unknown" there means "not in the fragment",
  not "invalid", and gating on it would tie the build to whichever CPT codes HL7
  ships. This mirrors v3 decision 9 (`level5.CPT_MEMBERSHIP`). Note `-tx n/a`
  does **not** avoid this: the CPT fragment is bundled locally.
- **`tests/test_fhir_export.py`** guards the export so CI can't silently
  validate fewer files; **`tests/test_fhir_conformance_gate.py`** covers the
  verdict logic, including that a waiver never masks a real finding.

**The gate paid for itself immediately — three real defects our own validator
never caught**, each now fixed with a regression test:

| # | Defect | Fix |
|---|--------|-----|
| 1 | **No `fullUrl` on Bundle entries** → *every* relative reference was unresolvable ("Relative Reference appears inside Bundle whose entry is missing a fullUrl") | `common.entry()` emits `{BUNDLE_BASE_URL}/{Type}/{id}`; `fhir/validator.py` now flags a missing `fullUrl` too |
| 2 | **ICD-10-CM emitted undotted** (`J0300`), which is *not* a code in `http://hl7.org/fhir/sid/icd-10-cm` — X12 carries no decimal point | `common.icd10cm_code()` inserts it after the 3-char category (`J03.00`); applied in `map_claim._diagnoses` |
| 3 | **`ExplanationOfBenefit.total[].reason`** — `reason` is valid on `item.adjudication` but does not exist on `total` | `map_eob._as_total()` reshapes to `category` + `amount`, carrying the X12 reason as a second coding on the category |
| 4 | **`CoverageEligibilityResponse` invariant ces-1** — an EB with no service type produced an item with neither `category` nor `productOrService` | `map_eligibility._eb_item()` falls back to a text-only "Plan-level benefit" category |

**Verified locally**, not just wired up: `validator_cli.jar` 6.10.1 against all 8
exported Bundles → **0 blocking errors**; the only remaining findings are the 4
waived CPT codes from the synthetic `837P-all-fields.dat`. Before the fixes the
same run reported 25+ errors. Backend suite **180** (was 166 — +3 SNIP L3,
+11 FHIR/export/gate).

## 6.5 Open items / to confirm
- [x] **A FHIR validator running in CI** (D.1) — done 2026-08-11, see above.
- [ ] **IG profile certification** (CARIN Blue Button for EOB, US Core, Da Vinci)
      — the validator now *runs* against these IGs in CI, but **advisory only**.
      To make it a hard gate the mappers must declare `meta.profile` and carry
      each IG's must-support slices; then flip `continue-on-error: false` in
      `.github/workflows/ci.yml`. The runtime validator remains **base R4**
      by design (zero runtime dependencies).
- [ ] Fixture `837P-all-fields.dat` carries **synthetic CPT codes** (`99299`,
      `87099`, modifiers `28`/`29`) that no CPT edition recognizes. Harmless for
      structure, but the advisory job will always report them — decide whether to
      correct the fixture or keep it as an "unknown code" case.
- [ ] Confirm the `271` design choice of emitting derived `CoverageEligibilityRequest`
      + `Coverage` stubs (needed because R4 makes those references required).
- [ ] Move `NEXT-STEPS-PROPOSAL.md` / `RECOMMENDATIONS.md` into the repo if they
      should be versioned (currently in the parent folder).

## 6.6 Doc set (this folder, `docx/v2/`)
1. `1-fhir-requirements.md` — scope, users, features, mappings
2. `2-fhir-architecture.md` — flow, input adapter, fhir package, routing
3. `3-fhir-rules.md` — conventions, deps, code-system URIs, boundaries
4. `4-fhir-phases.md` — V2-A…D with acceptance criteria
5. `5-fhir-mapping-reference.md` — per-resource field mappings + worked example
6. `6-fhir-memory.md` — this log
