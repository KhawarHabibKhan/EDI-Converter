# Level 5 code sets

Bundled reference data for SNIP **Level 5 — Code sets** (`../level5.py`). Each
`.txt` file is a plain list of valid codes (one per line; `#` comments and blank
lines ignored; only the first token on a line is read, so `CODE  description`
works). The loader in `__init__.py` reads them lazily and caches the result for
the process.

## Files

| File | Code system | Used for | Status |
|------|-------------|----------|--------|
| `pos.txt` | Place of Service | 837P `CLM05-01` facility | **complete** standard set |
| `icd10cm.txt` | ICD-10-CM | `HI` diagnoses (ABK/ABF/ABJ/APR/ABN) | **seed subset** — replace with full CMS set |
| `icd10pcs.txt` | ICD-10-PCS | 837I `HI` inpatient procedures (BBR/BBQ) | **seed subset** — replace with full CMS set |
| `hcpcs.txt` | HCPCS Level II | `SV1`/`SV2` `HC:` procedures (letter+4 digits) | **seed subset** — replace with full CMS set |

> **Why seed subsets?** The full ICD-10-CM / ICD-10-PCS / HCPCS lists are large
> (tens of thousands of codes each). The bundled files contain the codes used by
> the sample fixtures plus a handful of common codes so the feature and its tests
> work out of the box. Swap in the full official lists any time — see below.

## CPT is gated (not bundled)

5-digit numeric **CPT** procedure codes are **AMA-licensed** and are intentionally
**not** shipped here. Level 5 **format-checks** CPT-range codes only and adds one
`INFO` note that CPT membership was not validated. When AMA licensing is approved,
add `cpt.txt`, register it in `__init__.py` `_FILES`, and set `CPT_MEMBERSHIP =
True` in `level5.py` — no other changes needed.

## Refreshing a set (data update, not a code change)

1. Download the current official list (free sources below).
2. Reduce it to one code per line (codes only, or `CODE  description`).
   Store ICD codes **without** the decimal point, as they appear in X12.
3. Replace the corresponding `.txt` file in this folder and commit it.

Sources (all free):
- ICD-10-CM / ICD-10-PCS — CMS: <https://www.cms.gov/medicare/coding-billing/icd-10-codes>
- HCPCS Level II — CMS: <https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system>
- Place of Service — CMS: <https://www.cms.gov/medicare/coding-billing/place-of-service-codes/code-sets>
