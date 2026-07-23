# v3 · 2 — SNIP Validation Architecture

> **Project:** EDI-Converter — Version 3 (SNIP Level 2–5 validation)
> **Last updated:** 2026-07-23

---

## 2.1 Guiding idea

The X12 validator already parses the segment tree once and returns a structured
issue list. v3 keeps that shape and **adds rule layers on top**: a small engine
runs Level 1 (existing) then, cumulatively, Levels 2→N of per-transaction-type
rules. Everything reads the **already-parsed segments** — nothing re-parses, and
the mappers / FHIR path are untouched.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Validation view (Converter page + FHIR page reuse the same renderer)  │
│  issues now carry a SNIP `level` (1–5) → shown + filterable            │
└───────────────────────────────┬────────────────────────────────────── ┘
                                 │  POST /edi/validate?snip_level=N
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  main.py  (FastAPI)  — reads snip_level, calls validation.run(...)     │
└───────────────────────────────┬────────────────────────────────────── ┘
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  engine/validation/  (NEW package)                                     │
│    runner.py    → parse once, detect type, run Levels 1..N cumulatively │
│    level1.py    → envelope (moved/kept from engine/validator.py)        │
│    level2.py    → requirement (required segs/elements/loops, datatypes)  │
│    level3.py    → balancing (claim vs lines; 835 payment math)          │
│    level4.py    → situational (inter-segment "if A then B")             │
│    level5.py    → code-set validity (bundled tables; CPT gated)         │
│    rules/<txn>/  → per-transaction-type rule data (837P, 837I, 835, …)  │
│    codesets/     → bundled free code sets (ICD-10, HCPCS, POS, …)       │
│    issue.py     → issue builder (adds `level`)                          │
└───────────────────────────────┬────────────────────────────────────── ┘
                                 ▼
        issue list  [{severity, level, message, segment, position, ...}]
```

## 2.2 Backend structure (additions only)

```
backend/
├── main.py                         # /edi/validate gains ?snip_level=
└── engine/
    ├── validator.py                # KEPT as the Level-1 entry (or re-exported
    │                               #   by validation/level1.py) for back-compat
    └── validation/                 # NEW package
        ├── __init__.py
        ├── runner.py               # orchestrates Levels 1..N; dedups; sorts
        ├── issue.py                # _issue(...) now includes `level`
        ├── level1.py               # envelope (wraps existing validator logic)
        ├── level2.py               # requirement checks (data-driven per type)
        ├── level3.py               # balancing (pure arithmetic)
        ├── level4.py               # situational (rule predicates)
        ├── level5.py               # code-set lookups
        ├── rules/                  # per-transaction-type rule definitions
        │   ├── common.py           # shared loop/segment helpers
        │   ├── t837p.py            # 837P required segs/elements/situational
        │   ├── t837i.py            # 837I
        │   ├── t835.py             # 835
        │   ├── t834.py             # 834
        │   ├── t27x.py             # 270/271
        │   └── t27_status.py       # 276/277
        └── codesets/
            ├── __init__.py         # loader + membership tests
            ├── icd10cm.txt         # bundled (free)
            ├── icd10pcs.txt        # bundled (free)
            ├── hcpcs.txt           # bundled (free)
            ├── pos.txt             # place-of-service (free)
            └── README.md           # sources + documented refresh process
```

> **Back-compat:** the existing `engine/validator.py` / `validate_edi(raw)` and
> the current default `POST /edi/validate` behavior (Level 1) must not change for
> callers that don't pass `snip_level`. Simplest path: `level1.py` reuses the
> existing logic; `validator.py` stays as a thin Level-1 facade.

### Module contracts
- `runner.run(raw, snip_level) -> list[issue]`
  - parse once (`x12_reader.parse`), detect type (`detector`),
  - run Level 1 always; then Levels 2..`snip_level` for that transaction type,
  - each level returns `list[issue]`; runner concatenates, de-dups, sorts by
    (position, level, severity).
- `levelN.check(doc, txn_type, ctx) -> list[issue]` — one module per level; each
  dispatches to the per-type rule set in `rules/`.
- `issue.make(severity, level, message, segment="", position=0) -> dict`.
- `codesets.contains(set_name, code) -> bool` — membership test used by Level 5.

## 2.3 API contract

| Method | Path | Query | Returns |
|--------|------|-------|---------|
| `POST` | `/edi/validate` | `snip_level` = `1..5` (optional; default = highest implemented) | JSON report |

Report shape (extends the v1 report — **additive**, existing fields unchanged):
```jsonc
{
  "file_name": "claim.edi",
  "transaction_type": "837P",     // NEW: which rule set ran
  "snip_level": 5,                 // NEW: level requested/applied
  "valid": false,
  "error_count": 2,
  "warning_count": 1,
  "issue_count": 3,
  "issues": [
    { "severity": "ERROR", "level": 3, "message": "CLM02 350.00 ≠ Σ service lines 300.00",
      "segment": "CLM", "position": 12 }
  ]
}
```
- `level` is added to each issue; Level 1 issues report `level: 1`.
- Errors follow the v1 convention: 400 (bad/undetectable input), 413, 500.
- Default `snip_level` = the highest level implemented **so far** (so the endpoint
  gets stricter automatically as each level branch merges).

## 2.4 Frontend (validation view)

The validation result renderer already lists issues with severity/segment. v3
adds, in the **same** component (shared `ResultPanel` / validation view):
- a **SNIP level badge** on each issue row (e.g. `L3`),
- the summary line shows the applied `snip_level` and `transaction_type`,
- (optional) a **level selector** on the Converter page's options (1–5) that sets
  `?snip_level=`; default = highest. Auto-validation continues to run on input
  change, now at the selected level.

No new page. The FHIR page is unaffected (it uses the separate FHIR validator).

## 2.5 Tech & dependencies

| Concern | Choice |
|---------|--------|
| Rule engine | **Hand-built, data-driven** Python — **zero new runtime deps** |
| Code sets | **Bundled text/CSV tables** loaded at process start; membership via `set` |
| Balancing math | stdlib `decimal.Decimal` (exact money math) |
| CPT | **excluded** until AMA licensing is decided (see `3-snip-rules.md`) |

## 2.6 Reused vs new

| Reused from v1/v2 (unchanged) | New in v3 |
|-------------------------------|-----------|
| `x12_reader`, `detector`, all mappers, `xml/csv/fhir` writers, FHIR validator | `engine/validation/` package (runner + level modules + rules + codesets) |
| `POST /edi/validate` contract (backward compatible) | `?snip_level=` param + `level`/`transaction_type` report fields |
| Validation result UI component | SNIP level badge + optional level selector |

## 2.7 Two validators — do not confuse
- **`engine/validator.py` → `engine/validation/`** — validates **X12 EDI** (this v3).
- **`engine/fhir/validator.py`** — validates the generated **FHIR Bundle** (v2).

Different inputs, different endpoints (`/edi/validate` vs `/edi/fhir/validate`).
