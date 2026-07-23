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
- **v3 (SNIP L2–5):** **Level 2 complete** (branch `feature/snip-validation-level-2`).
  Framework + `?snip_level=` + requirement rules for all in-scope types built and
  green (backend **126 tests**, frontend build clean). Awaiting merge to `main`,
  then Level 3.

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
| 2 | `feature/snip-validation-level-2` | Requirement (framework + `?snip_level=` + IG required segs/elements) | ✅ built (pending merge) |
| 3 | `feature/snip-level-3` | Balancing (837 totals; 835 payment math) | ⬜ Not started |
| 4 | `feature/snip-level-4` | Situational (inter-segment rules) | ⬜ Not started |
| 5 | `feature/snip-level-5` | Code sets (free sets; CPT gated) | ⬜ Not started |

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
- **Now:** user merges `feature/snip-validation-level-2` → `main` (all tests
  green, docs updated).
- **Next action:** after merge, from a fresh `main` create the Level 3 branch and
  build **V3-L3** — `engine/validation/level3.py` (balancing): 837 `CLM02` == Σ
  service-line charges; 835 `CLP`/`SVC`/`BPR` payment math (exact `Decimal`).
  Bump `HIGHEST_LEVEL` to 3, extend the UI level selector to include Level 3,
  add `tests/test_snip_level3.py`.
- **No parser/mapper/FHIR changes** — validation reads the existing segments.

## 6.5 Open items / to confirm
- [x] Level 2 built on `feature/snip-validation-level-2` — pending user merge.
- [ ] After merge, start **Level 3** (balancing) on a fresh branch from `main`.
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
