# v3 · 3 — SNIP Validation Rules & Conventions

> **Project:** EDI-Converter — Version 3 (SNIP Level 2–5 validation)
> **Last updated:** 2026-07-23
> Extends the v1 rules (`../3-rules.md`); v1/v2 rules still apply.

---

## 3.1 What to use
- **Hand-built, data-driven rules** in plain Python — keep the project's
  **zero-runtime-dependency** principle. No schema/rule-engine libraries.
- **One rule module per SNIP level** (`validation/level2.py` … `level5.py`), each
  dispatching to **per-transaction-type rule data** under `validation/rules/`.
- Rules are expressed as **data + small predicates**, not sprawling `if` trees:
  a Level-2 requirement is a table of `(loop, segment, element, condition)`; a
  Level-4 situational rule is a `(when_predicate, then_required)` pair.
- `decimal.Decimal` for all money/quantity balancing (never binary `float`).
- Bundled **code-set tables** loaded once at import; membership via `set`.

## 3.2 What to avoid
- ❌ **No new runtime dependency.**
- ❌ **No re-parsing** — consume the `EdiDocument` the runner already parsed.
- ❌ **No parser/mapper/FHIR changes** — v3 only reads segments.
- ❌ **Don't break Level 1 back-compat** — callers with no `snip_level` keep
  today's behavior; Level-1 issues keep their current message text where feasible.
- ❌ **No PHI persistence / logging** — treat all EDI as PHI-sensitive (as v1/v2).
- ❌ **Don't hard-code paths/ports** — reuse `config.py` / env.
- ❌ **No CPT validation** until the AMA-licensing decision (see §3.6).

## 3.3 Issue conventions
- Every issue carries **`level` (1–5)** plus the existing
  `severity` / `message` / `segment` / `position`.
- **Severity:** `ERROR` = payer would reject; `WARNING` = likely-reject / risky;
  `INFO` = advisory. Keep the vocabulary identical to v1 so the UI is unchanged.
- **Messages** name the offending segment/element and the expected condition,
  e.g. `"2400 SV1 missing required element SV101 (procedure code)."`
- **Cumulative:** running level N runs 1..N. The runner de-dups and sorts by
  `(position, level, severity)`.
- **No PHI in messages** — reference segment IDs/positions and element names,
  never echo full patient data.

## 3.4 Rule-authoring conventions (house rules)
- **Level 2 (Requirement):** encode required loops/segments/elements, element
  **data types** (ID/AN/DT/R/N), min/max length, and **loop repeat limits** from
  the transaction's TR3 implementation guide. Represent as per-type tables.
- **Level 3 (Balancing):** pure arithmetic, exact `Decimal`. Each balancing rule
  states the equation and tolerance (default exact; document any allowed epsilon).
- **Level 4 (Situational):** `(condition → requirement)` predicates over the
  parsed segments; each rule cites its TR3 situational note in a comment.
- **Level 5 (Code set):** look the coded value up in the bundled set for its
  code system; unknown code → issue. Never invent codes.
- **Every rule is traceable** — a short comment naming the TR3 loop/element or the
  SNIP concept it enforces, so rules can be audited against the guide.

## 3.5 Transaction-type scope
- **837P is encoded first** on every level branch (proof-of-pattern).
- In-scope types (match the converter's mappers): **837P, 837I, 835, 834,
  270/271, 276/277**. Priority order for depth: **837P → 837I → 835 → 834 →
  271 → 277** (claims/remittance first, where balancing/requirement value is
  highest). Confirm per-level scope in `6-snip-memory.md`.

## 3.6 Code-set sourcing & licensing (decision needed)
Level 5 validates codes against external sets; sourcing differs:

| Code set | Used by | Sourcing | Status |
|----------|---------|----------|--------|
| ICD-10-CM / ICD-10-PCS | diagnoses / inpatient procedures | CMS, **free** | bundle + refresh |
| HCPCS Level II | procedures/supplies | CMS, **free** | bundle + refresh |
| Place of Service | 837 facility code | CMS, **free** | bundle |
| X12 internal lists | qualifiers, status, adjustment codes | in the X12 guides, **free** | bundle |
| **CPT** | professional procedures | **AMA-licensed, NOT free** | **⛔ gated on a licensing decision** |

- **Plan:** ship Level 5 against the **free sets first**. CPT validation stays
  **off** until leadership confirms AMA licensing. Until then, CPT-position codes
  are format-checked (length/numeric-ish) but **not** membership-validated, and
  the report notes CPT membership was not checked.
- **Refresh:** `validation/codesets/README.md` documents each set's source URL,
  version/date, and the manual refresh steps. Code sets are **data**, versioned
  with the repo; refreshing is a data update, not a code change.

## 3.7 Delivery / Git workflow (per level)
- The work is delivered **one SNIP level per feature branch**, merged to `main`
  before the next level starts (`4-snip-phases.md` §4.1).
- **The user owns all Git/GitHub** — branch creation, commits, PRs, merges, and
  pushes. The assistant only writes code/docs and runs tests locally; it **does
  not** create branches, commit, or push, and never adds AI co-author trailers.

## 3.8 AI / contributor boundaries
- Read `6-snip-memory.md` first; update it after each level merges.
- Work **one level at a time** (L2 → L5); each ships on its own branch.
- Every level gets **unit tests** (valid + deliberately-invalid samples) before
  it is considered done.
- Do not introduce a runtime dependency without explicit approval.
- Keep Level-1 behavior backward compatible.
