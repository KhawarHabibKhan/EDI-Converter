# v3 · 6 — SNIP Project Memory (Living Progress Log)

> **Project:** EDI-Converter — Version 3 (SNIP Level 2–5 validation)
> **Last updated:** 2026-07-23
>
> Read this FIRST before working on v3. Update it whenever something is started,
> completed, or decided. Single source of truth for "where is v3?".

---

## 6.1 Status
- **v1:** complete (Phases 0–9). 8 X12 types → JSON/XML/CSV, auto-validation
  (SNIP **Level 1** only), batch, maximize.
- **v2 (FHIR):** complete (V2-A→D). 8 types → FHIR R4 Bundles + FHIR structural
  validation. See `../v2/6-fhir-memory.md`.
- **v3 (SNIP L2–5): COMPLETE.** All levels 2–5 built.
  - Level 2 (Requirement) — merged to `main`.
  - Level 3 (Balancing) — merged to `main`.
  - Level 4 (Situational) — merged to `main`.
  - Level 5 (Code sets) — built on `feature/snip-validation-level-5`
    (`HIGHEST_LEVEL=5`, default validation now runs L1..L5). Backend **166
    tests** passing, frontend build clean. Awaiting merge → completes v3.

## 6.2 Locked decisions
| # | Decision | Choice |
|---|----------|--------|
| 1 | Scope | SNIP **Levels 2–5** in one v3 initiative (Level 1 already done; 6–7 out) |
| 2 | Delivery | **One feature branch per level**, merged to `main` before the next |
| 3 | Git ownership | **User** owns all branches/commits/PRs/merges/pushes; assistant never commits/pushes and adds no AI co-author trailer |
| 4 | Implementation | **Hand-built, data-driven rules, zero new runtime deps** |
| 5 | Component | Extend `engine/validator.py` → `engine/validation/` + `?snip_level=` on `POST /edi/validate` (back-compatible) |
| 6 | No touching | **No parser/mapper/FHIR changes**; reads already-parsed segments |
| 7 | Issue shape | Existing `severity/message/segment/position` **+ `level`** |
| 8 | Proof-of-pattern | **837P first** on every level branch |
| 9 | CPT | **Gated** on AMA licensing; ship free code sets first (§6.5) |

## 6.3 Progress by level (branch)
| Level | Branch | Description | Status |
|-------|--------|-------------|--------|
| 1 | (merged, pre-v3) | Integrity / envelope | ✅ done (`engine/validator.py`) |
| 2 | `feature/snip-validation-level-2` | Requirement (framework + `?snip_level=` + IG required segs/elements) | ✅ merged |
| 3 | `feature/snip-validation-level-3` | Balancing (837 totals; 835 payment math) | ✅ merged |
| 4 | `feature/snip-validation-level-4` | Situational (inter-segment rules) | ✅ merged |
| 5 | `feature/snip-validation-level-5` | Code sets (free sets; CPT gated) | ✅ built (pending merge) |

### What Level 2 shipped (files, branch `feature/snip-validation-level-2`)
- Backend: `engine/validation/` package — `__init__.py` (`HIGHEST_LEVEL=2`),
  `issue.py` (adds `level`), `level1.py` (facade over the existing envelope
  logic), `level2.py` (dispatch), `runner.py` (parse once, run 1..N, dedup/sort),
  and `rules/` (`common.py` + `t837p`, `t837i`, `t835`, `t834`, `t270_271`,
  `t276_277`). `engine/validator.py` refactored to expose `validate_doc(doc)`
  (Level-1 core) while `validate_edi(raw)` stays back-compatible.
- Endpoint: `POST /edi/validate?snip_level=` (default highest = 2); report gains
  `transaction_type` + `snip_level`; every issue carries `level`.
- Frontend: SNIP-level selector on Converter options (auto-validation uses it),
  per-issue `L1/L2` badge + "Validated to SNIP level N · TYPE" scope line.
- Tests: `tests/test_snip_level2.py` (20 tests) — clean per type, requirement
  failures, cumulative L1+L2, level gating, endpoint, out-of-range 422. Suite
  now **126** (was 106). Frontend build green.
- **Merge gate met.** After merge, bump nothing here except starting Level 3 on
  a fresh branch from `main`.

Legend: ⬜ Not started · 🟨 In progress · ✅ Done/merged

## 6.4 Which component / feature next
- **Now:** user merges `feature/snip-validation-level-5` → `main`. **This
  completes v3** (SNIP Levels 1–5 all in `main`).
- **After v3:** no further SNIP levels planned (6–7 are out of scope). Candidate
  next work: swap the seed ICD/HCPCS sets for the full CMS lists (data-only
  refresh), revisit the deferred 835 BPR-level balancing, or move on to another
  RECOMMENDATIONS.md item.
- **No parser/mapper/FHIR changes** — validation reads the existing segments.

### What Level 5 shipped (files, branch `feature/snip-validation-level-5`)
- Backend: `engine/validation/level5.py` — membership validation of coded
  elements against bundled free sets. Checks ICD-10-CM diagnoses (`HI`
  ABK/ABF/ABJ/APR/ABN), ICD-10-PCS inpatient procedures (`HI` BBR/BBQ, 837I),
  HCPCS Level II procedures (`SV1`/`SV2` `HC:`), and Place of Service
  (`CLM05-01`, 837P). Unknown code → `ERROR` labeled `5`.
- Code sets: `engine/validation/codesets/` package — `__init__.py` loader
  (`contains`/`available`/`counts`, lazy + cached, normalizes case/dots) plus
  `pos.txt` (complete standard set), `icd10cm.txt`, `icd10pcs.txt`, `hcpcs.txt`
  (**seed subsets** — README documents refreshing to the full CMS lists as a
  data-only change), and `README.md`.
- **CPT gated:** 5-digit numeric CPT-range codes are format-checked only and
  never membership-validated; one `INFO` note per file records this. Flip
  `CPT_MEMBERSHIP=True` in `level5.py` (and add `cpt.txt`) once AMA licensing is
  approved — no restructuring.
- Wiring: `__init__.py` `HIGHEST_LEVEL=5`; `runner.py` runs `level5` at level ≥5.
- Frontend: "Level 5 — Code sets (ICD / HCPCS / POS)" option added; default now 5.
- Tests: `tests/test_snip_level5.py` — loader membership, clean 837P/837I pass,
  unknown ICD-10-CM/PCS/HCPCS/POS flagged, CPT format-only + INFO note, level
  gating, endpoint default. Suite now **166** (was 153).

### What Level 3 shipped (merged)
- `engine/validation/level3.py` (exact `Decimal`): 837 `CLM02` == Σ line charges;
  835 line `SVC02 == SVC03 + Σ line CAS` and claim `CLP03 == Σ SVC02`,
  `CLP04 == Σ SVC03`. Fixture `837I-sample.edi` `CLM02 → 750` (was unbalanced).
  BPR-level balancing deferred (see §6.5).

### What Level 4 shipped (branch `feature/snip-validation-level-4`)
- Backend: `engine/validation/level4.py` (situational): 837 accident
  (`CLM11` → `DTP*439`), COB (non-primary `SBR01` → other-payer 2320 loop),
  837I admission (`CL1` → `DTP*435`); 834 coverage (`HD` → `DTP*348`).
  Registered in `runner.py`; `HIGHEST_LEVEL = 4`.
- Frontend: SNIP selector gains **Level 4 — Situational**; default → 4.
- Tests: `tests/test_snip_level4.py` (15); Level-3 endpoint default assertion made
  dynamic (`HIGHEST_LEVEL`). Suite **153** (was 138). Frontend build green.

## 6.5 Open items / to confirm
- [x] Level 2 merged to `main`.
- [x] Level 3 merged to `main`.
- [x] Level 4 — merged to `main`.
- [x] Level 5 built on `feature/snip-validation-level-5` — pending user merge (completes v3).
- [ ] Refresh seed ICD-10-CM / ICD-10-PCS / HCPCS sets with the full CMS lists
      (data-only; drop-in replace the `.txt` files in `codesets/`).
- [ ] **BPR-level 835 balancing** (`BPR02 = Σ CLP04 − Σ PLB`) deferred from L3 —
      revisit with realistic balanced samples (sign-aware PLB).
- [ ] **CPT licensing** (AMA) for full Level 5 — ship free sets first; confirm
      whether/when to enable CPT membership validation.
- [ ] Confirm the per-level **transaction-type scope & order** (default:
      837P → 837I → 835 → 834 → 271 → 277).
- [ ] Confirm default `?snip_level=` = highest merged level (gets stricter as
      each branch lands) vs. an explicit fixed default.

## 6.6 Doc set (this folder, `docx/v3/`)
1. `1-snip-requirements.md` — scope, SNIP levels, users, features, success criteria
2. `2-snip-architecture.md` — flow, `engine/validation/` package, `?snip_level=` contract, UI
3. `3-snip-rules.md` — conventions, zero-dep, code-set sourcing/CPT licensing, boundaries
4. `4-snip-phases.md` — per-level phases (V3-L2…L5) + feature-branch-per-level Git workflow
5. `5-snip-rule-reference.md` — per-level rule catalogs + worked examples
6. `6-snip-memory.md` — this log

## 6.7 Related docs
- Research basis: `../../../RECOMMENDATIONS.md` (Rec 2) and
  `../../../NEXT-STEPS-SNIP-VALIDATION.md`.
- v1 docs: `../1-project-requirements.md` … `../8-frontend-plan.md`.
- v2 (FHIR) docs: `../v2/`.
- Current Level-1 validator: `../../backend/engine/validator.py`;
  endpoint `POST /edi/validate` in `../../backend/main.py`.

## 6.8 Cross-version notes
- **Validation parity (both converters auto-validate, same source checks).**
  The Converter page auto-validates the X12 file through the SNIP levels (v3).
  The **FHIR page now auto-validates too**, and — importantly — its
  `/edi/fhir/validate` endpoint **reuses this v3 SNIP runner** on raw-EDI input
  (`stage:"snip"`, levelled) *in addition to* the v2 FHIR R4 Bundle check
  (`stage:"fhir"`). This fixed an inconsistency where the FHIR page passed a
  SNIP-broken 837 that the Converter flagged (a lenient mapper still yields a
  structurally-valid Bundle). So the SNIP validator built here is now consumed
  by **both** pages. JSON/XML exports skip SNIP (no X12 envelope).
- The FHIR-side wiring lives in v2 — see `../v2/6-fhir-memory.md`. The SNIP
  engine itself (`engine/validation/`) is unchanged by this; the FHIR endpoint
  just calls `runner.validate(...)`.
