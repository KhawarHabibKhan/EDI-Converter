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
- **v3 (SNIP L2–5):** **planned, not started.** Documentation set written;
  awaiting go-ahead to start **Level 2** (`feature/snip-level-2`).

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
| 2 | `feature/snip-level-2` | Requirement (framework + `?snip_level=` + IG required segs/elements) | ⬜ Not started |
| 3 | `feature/snip-level-3` | Balancing (837 totals; 835 payment math) | ⬜ Not started |
| 4 | `feature/snip-level-4` | Situational (inter-segment rules) | ⬜ Not started |
| 5 | `feature/snip-level-5` | Code sets (free sets; CPT gated) | ⬜ Not started |

Legend: ⬜ Not started · 🟨 In progress · ✅ Done/merged

## 6.4 Which component / feature next
- **Next action:** on go-ahead, create `feature/snip-level-2` (user) and build
  **V3-L2** — the `engine/validation/` framework (`runner`, `issue` with `level`,
  `level1` facade), `?snip_level=` on the endpoint, then `level2` + `rules/t837p`
  (837P first), then the remaining in-scope types, then the UI level badge.
- **Merge gate:** new + all existing tests green; default `snip_level` bumped;
  this doc updated; then user merges to `main` before Level 3.
- **No parser/mapper/FHIR changes** — validation reads the existing segments.

## 6.5 Open items / to confirm
- [ ] Go-ahead to start **Level 2** (`feature/snip-level-2`).
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
