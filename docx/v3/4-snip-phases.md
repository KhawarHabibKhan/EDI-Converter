# v3 · 4 — SNIP Phases & Git Workflow

> **Project:** EDI-Converter — Version 3 (SNIP Level 2–5 validation)
> **Last updated:** 2026-07-23
> Build in order, **one level per feature branch**. Track status in `6-snip-memory.md`.

---

## 4.1 Delivery workflow — one feature branch per SNIP level

**The user manages all Git/GitHub.** The assistant writes code + docs and runs
tests locally only; it does **not** create branches, commit, push, open PRs, or
merge, and never adds AI co-author trailers. The workflow below is what **the
user** performs; the assistant's deliverable per level is "green code + tests +
updated docs" ready to commit.

```
main
 ├─ feature/snip-level-2   →  build Level 2  →  PR → review → merge → delete
 ├─ feature/snip-level-3   →  build Level 3  →  PR → review → merge → delete
 ├─ feature/snip-level-4   →  build Level 4  →  PR → review → merge → delete
 └─ feature/snip-level-5   →  build Level 5  →  PR → review → merge → delete
```

Per level (user-run):
1. `git checkout main && git pull`
2. `git checkout -b feature/snip-level-N`
3. assistant implements level N + tests + doc updates; user commits in logical chunks
4. open PR → review → **all tests green** → merge to `main` → delete branch
5. only then start `feature/snip-level-(N+1)` from the freshly-merged `main`

**Merge gate (per level):** new level tests pass **and** all existing v1/v2/v3
tests pass; `?snip_level=` default bumped to the newly-merged level; `6-snip-memory.md`
updated to mark the level ✅ merged.

> Branches are strictly **per level** (4 branches total). Within a level branch,
> 837P is committed first (pattern), then remaining transaction types — all under
> the same branch, merged together as that level's deliverable.

---

## V3-L2 — Level 2: Requirement  *(branch: `feature/snip-level-2`)*  — proof-of-pattern

Stand up the **rule-module framework** and encode IG requirement rules.

- **L2.1** `engine/validation/` package: `runner.py`, `issue.py` (adds `level`),
  `level1.py` (wraps existing envelope logic; keep `validator.py` as a facade).
- **L2.2** `?snip_level=` on `POST /edi/validate`; report gains `level` +
  `transaction_type` + `snip_level` (additive, back-compatible).
- **L2.3** `level2.py` + `rules/t837p.py` — required loops/segments/elements,
  data types, loop repeat limits for **837P** (the proof-of-pattern).
- **L2.4** Extend Level 2 to the remaining in-scope types
  (837I → 835 → 834 → 271 → 277), each as its own `rules/<txn>.py`.
- **L2.5** Frontend: SNIP level badge on issue rows; show applied level/type;
  optional level selector (1–5) on the Converter options.
- **L2.6** Tests: clean sample per type → 0 Level-2 errors; a deliberately broken
  copy (missing a required element/loop) → the exact Level-2 issue, labeled `2`.

**Done when:** `?snip_level=2` reports missing-required issues for every in-scope
type; Level-1 behavior unchanged when `snip_level` is omitted; tests green;
branch merged to `main`.

---

## V3-L3 — Level 3: Balancing  *(branch: `feature/snip-level-3`)*

Pure arithmetic (exact `Decimal`), no external data.

- **L3.1** `level3.py` + balancing rules:
  - **837:** `CLM02` claim total == Σ service-line charges (`SV1`/`SV2`).
  - **835:** `CLP` charge == paid + patient-responsibility + Σ `CAS` adjustments;
    `SVC` line balancing; `BPR02` total == Σ `CLP04` + Σ `PLB`.
- **L3.2** Tests: balanced samples → clean; unbalanced copies → the specific
  Level-3 mismatch, labeled `3`, naming both sides of the equation.

**Done when:** `?snip_level=3` catches claim/remittance imbalances; branch merged.

---

## V3-L4 — Level 4: Situational  *(branch: `feature/snip-level-4`)*

Inter-segment "if A present, then B required" rules.

- **L4.1** `level4.py` + per-type situational rule sets (each rule cites its TR3
  situational note), e.g.:
  - 837: if COB indicated → other-payer loop (2320/2330) required;
  - 837: if accident-related → accident date (DTP) required;
  - 837I: if certain bill types → admission date/hour required.
- **L4.2** Tests: rule-triggering samples with the dependent segment present
  (clean) and absent (Level-4 issue, labeled `4`).

**Done when:** `?snip_level=4` enforces the encoded situational rules; branch merged.

---

## V3-L5 — Level 5: Code set  *(branch: `feature/snip-level-5`)*

External code-set validity from **bundled free sets**; **CPT gated**.

- **L5.1** `codesets/` loader + membership tests; bundle ICD-10-CM/PCS, HCPCS,
  POS, and relevant X12 internal lists (+ `README.md` sources/refresh).
- **L5.2** `level5.py` — validate diagnosis codes (ICD-10-CM), institutional
  procedures (ICD-10-PCS), HCPCS, place-of-service, etc. against the sets.
- **L5.3** CPT-position codes: format-check only + a report note that CPT
  membership was **not** validated (pending AMA licensing). Wire CPT membership
  behind a flag to switch on once licensing is approved.
- **L5.4** Tests: valid codes → clean; invalid codes → Level-5 issue, labeled `5`;
  a CPT code → format-checked, note present, no false "invalid".

**Done when:** `?snip_level=5` flags out-of-set codes for the free sets; CPT
handled per the licensing decision; branch merged. **v3 complete.**

---

### Dependency map
```
main ─► L2 (framework + requirement) ─► L3 (balancing) ─► L4 (situational) ─► L5 (code sets)
         each on its own feature branch, merged to main before the next begins
```
L2 builds the runner + `?snip_level=` + issue `level`; L3/L4/L5 are "just another
level module + per-type rules" once L2 exists.
