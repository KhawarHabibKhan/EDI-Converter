# v3 · 1 — SNIP Validation Requirements

> **Project:** EDI-Converter — Version 3 (SNIP Level 2–5 validation)
> **Last updated:** 2026-07-23
>
> Extends the v1 requirements (`../1-project-requirements.md`). v1/v2 stay as-is.

---

## 1.1 What to build

Extend the EDI-Converter's validation from today's **envelope-only (SNIP Level 1)**
checks up through the industry-standard **WEDI SNIP Levels 2–5** — a real
**claim scrubber** that answers *"will a payer accept this claim?"*, not just
*"is this a well-formed file?"*.

The whole span **Level 2 → Level 5 is one initiative (v3)**, delivered one SNIP
level at a time. Each level is developed on **its own feature branch and merged
to `main` before the next level begins** (see `4-snip-phases.md` §4.1).

This is a **content extension of the existing X12 validator** (`engine/validator.py`
+ `POST /edi/validate`), not new plumbing — no parser, mapper, or FHIR changes.

## 1.2 Why (real-world driver)

SNIP (Strategic National Implementation Process, WEDI) is the framework payers
and clearinghouses actually use to accept or reject a claim file. Scrubbing to
Levels 2–5 is what drives claim error/denial rates below ~5%. Commercial tools
(clearinghouse claim-scrubbers, EdiFabric, PilotFish) sell exactly this. It also
strengthens the rest of the tool: a file that passes SNIP 2–5 produces cleaner,
more complete **FHIR** output (v2), since the same required fields drive both.

Source research: `../../../RECOMMENDATIONS.md` (Recommendation 2) and
`../../../NEXT-STEPS-SNIP-VALIDATION.md`.

## 1.3 Target users
- **Providers / billers** — catch rejections before submission.
- **Clearinghouse / payer intake** — gate bad data before it costs a denial.
- **Integration engineers** — a self-hosted scrubber with no per-claim fee.
- (Same audience as v1; this deepens the "validate" answer they already get.)

## 1.4 The SNIP levels (cumulative)

Levels are **cumulative** — enforcing Level 4 also enforces 1–3. v3 covers 2–5.

| Level | Name | What it checks | v3 status |
|-------|------|----------------|-----------|
| **1** | Integrity | X12 envelope: ISA/IEA, GS/GE, ST/SE, control numbers, segment counts | ✅ exists (`engine/validator.py`) |
| **2** | Requirement | HIPAA IG syntax: required segments/elements/loops, data types, loop repeat limits | v3 |
| **3** | Balancing | Amounts/quantities balance (claim total vs service lines; 835 payment math) | v3 |
| **4** | Situational | Inter-segment rules ("if element A present, B is required") | v3 |
| **5** | Code set | External code-set validity (ICD-10, HCPCS, POS, X12 internal lists; CPT gated) | v3 |
| 6 | Product/type | Payer product-specific rules | ❌ out of scope |
| 7 | Trading-partner | Payer companion-guide-specific rules | ❌ out of scope |

Levels 6–7 need payer-specific companion guides we do not target.

## 1.5 Key distinction — why v3 is per-level *and* per-transaction-type
- **Level 1 is generic:** one envelope ruleset for every transaction.
- **Levels 2–5 are transaction-type-specific:** 837P, 837I, 835, 834, 270/271,
  276/277 each have their **own** implementation-guide (TR3) rule set.

So each level's branch carries a rule set per in-scope transaction type. To keep
branches shippable, **837P is always encoded first** as the proof-of-pattern,
then the remaining types follow within the same level branch (see phase scope).

## 1.6 Features

### Must-have (per level)
- [ ] Per-level rule modules behind the existing validator (`engine/validation/`)
- [ ] `?snip_level=` query param on `POST /edi/validate` — **cumulative**, default
      to the highest implemented level
- [ ] Every returned issue **labeled with its SNIP level** (`level: 1..5`)
- [ ] Reuse the existing issue shape (`severity`/`message`/`segment`/`position`)
      and the existing UI validation view (add the level label/filter)
- [ ] Unit tests per level against sample files (valid **and** deliberately invalid)

### By level
- [ ] **Level 2** — required segments/elements/loops, data types, repeat limits
- [ ] **Level 3** — balancing (837 claim vs service lines; 835 payment math)
- [ ] **Level 4** — situational inter-segment rules
- [ ] **Level 5** — code-set validity from bundled free sets (CPT gated on licensing)

## 1.7 Non-goals (v3)
- ❌ SNIP Levels 6–7 (payer product / trading-partner companion guides).
- ❌ CPT code-set validation until the AMA-licensing decision is made (§ see rules).
- ❌ Parser / mapper / FHIR changes — v3 reads the same parsed segments Level 1 uses.
- ❌ Persisting any EDI/PHI — validation stays in-memory (same as v1/v2).
- ❌ JSON → EDI generation (a separate future initiative; noted, not built here).

## 1.8 Success criteria (per level, and overall)
1. Uploading a clean in-scope file at `?snip_level=N` returns **zero errors**;
   a deliberately broken one returns the **specific** level-N issue, labeled `N`.
2. Cumulative behavior verified: `snip_level=4` also reports any Level 2/3 issues.
3. All existing v1/v2 tests still pass; new per-level tests are green.
4. Each level ships on its own feature branch, merged to `main`, before the next.
5. **Overall v3 done:** Levels 2–5 merged; `POST /edi/validate?snip_level=5`
   scrubs the in-scope transaction types with level-labeled issues in the UI.
