# v2 · 3 — FHIR Rules & Conventions

> **Project:** EDI-Converter — Version 2 (FHIR R4)
> **Last updated:** 2026-07-23
> Extends the v1 rules (`../3-rules.md`); v1 rules still apply.

---

## 3.1 What to use
- **Hand-built FHIR** as plain Python dicts serialized with stdlib `json` — keep the
  project's **zero-runtime-dependency** principle.
- One **mapper module per FHIR resource** (`fhir/map_claim.py`, `map_eob.py`, …),
  each exposing `to_fhir(dict) -> list[resource dicts]` (primary + referenced).
- Shared builders in `fhir/common.py` for `Reference`, `Identifier`,
  `CodeableConcept`, `HumanName`, money, and the **code-system URI table**.
- `xml.etree.ElementTree` (stdlib) for XML input parsing.
- **`react-router-dom`** for the two-page frontend (the only new runtime dep).

## 3.2 What to avoid
- ❌ **No new backend runtime dependency** (no `fhir.resources` at runtime for v2).
- ❌ **No X12 parser or mapper changes** — FHIR consumes the existing dict only.
- ❌ **Do not build FHIR JSON as strings** — always build dicts, then `json.dumps`.
- ❌ **Do not accept arbitrary JSON/XML** — input `.json`/`.xml` must be our schema;
  anything else → clean HTTP 400.
- ❌ **No PHI persistence** — FHIR output is generated in memory and returned, never
  stored (same as v1).
- ❌ Don't hard-code the API base or ports — reuse v1 `config.py` / env.

## 3.3 Dependency & validation policy (decision)
- **Runtime:** hand-built, zero new deps.
- **Validation for v2:** **reuse the existing structural validator** as-is. Full
  **FHIR profile validation** (CARIN Blue Button / US Core / Da Vinci) is a
  deliberate **later upgrade (V2-D)** — likely a FHIR validator in CI, not at
  runtime. Until then, V2 targets **valid base FHIR R4 structure**, not IG
  certification.

## 3.4 FHIR conventions (house rules)
- **Bundle:** every response is a FHIR `Bundle` with `type: "collection"`; entries
  are the primary resource + all resources it references.
- **References:** link resources by `{"reference": "Patient/<id>"}` with stable,
  deterministic local ids (e.g., `patient-1`, `coverage-1`, `org-payer`). Prefer
  referenced resources in the Bundle over `contained` resources.
- **Identifiers:** carry business ids as `Identifier` (e.g., subscriber member id,
  patient control number) with an appropriate `system` where known.
- **Coded values:** always a `CodeableConcept` with `coding[].system` + `code`
  (never a bare code). Use the URI table in §3.5 / `5-fhir-mapping-reference.md`.
- **Missing required fields:** if our dict lacks a FHIR-required value, use a safe
  default where semantically valid, else a `data-absent-reason` extension — never
  invent clinical/financial data.
- **Field names / ids** must be XML/JSON safe and stable (they are a contract).

## 3.5 Code-system URIs (canonical list — keep in `fhir/common.py`)

| Concept | X12 source | FHIR `system` URI |
|---------|-----------|-------------------|
| ICD-10-CM diagnosis | HI `ABK/ABF/ABJ/APR` | `http://hl7.org/fhir/sid/icd-10-cm` |
| ICD-10-PCS procedure | HI `BBR/BBQ` | `http://www.cms.gov/Medicare/Coding/ICD10` |
| CPT / HCPCS | SV1/SV2 `HC:` | `http://www.ama-assn.org/go/cpt` · `https://www.cms.gov/…/HCPCSReleaseCodeSets` |
| Provider taxonomy (NPI) | NM1 `XX` | NPI: `http://hl7.org/fhir/sid/us-npi` |
| Claim type | 837P vs 837I | `http://terminology.hl7.org/CodeSystem/claim-type` (`professional`/`institutional`) |
| Adjustment group (CAS) | 835 `CO/PR/OA/PI` | `http://terminology.hl7.org/CodeSystem/adjudication` (+ CARIN) |
| Gender | DMG | `http://hl7.org/fhir/administrative-gender` |

> Exact URIs and profile-specific slices are **verified against the published FHIR
> R4 spec and IGs at implementation time**; this table is the working baseline.

## 3.6 AI / contributor boundaries
- Read `6-fhir-memory.md` first; update it after each phase.
- Work **one phase at a time** (V2-A → D); each phase ships on its own.
- Every resource mapper gets **unit tests** (structural FHIR checks) before "done".
- Do not introduce a runtime dependency without explicit approval.
- Treat all EDI/JSON/XML input as **PHI-sensitive** — never log full contents.
