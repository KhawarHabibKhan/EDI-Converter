# v2 · 1 — FHIR Requirements

> **Project:** EDI-Converter — Version 2 (FHIR R4)
> **Status:** Planned
> **Last updated:** 2026-07-23
> Part of the v2 doc set: [1-requirements](1-fhir-requirements.md) ·
> [2-architecture](2-fhir-architecture.md) · [3-rules](3-fhir-rules.md) ·
> [4-phases](4-fhir-phases.md) · [5-mapping](5-fhir-mapping-reference.md) ·
> [6-memory](6-fhir-memory.md)

---

## 1.1 What to build

A new, **separate "FHIR Converter" page** in the existing app that converts
healthcare data into **FHIR R4** JSON (packaged as a FHIR **Bundle**).

Where v1 page 1 reads only raw X12 EDI, the FHIR page accepts **four input types**
and always outputs FHIR:

| Input | Meaning | How it's handled |
|-------|---------|------------------|
| `.edi` | Raw X12 EDI | parsed by the v1 engine |
| `.dat` | Raw X12 EDI (alt extension) | parsed by the v1 engine |
| `.json` | **Our own** v1 JSON output | loaded directly (already the normalized dict) |
| `.xml` | **Our own** v1 XML output | parsed back into the dict |

> `.json` / `.xml` are the files **this tool produced** (round-trip). They are not
> arbitrary third-party documents — FHIR mapping needs our known field meanings.

The conversion re-uses the v1 pipeline: any input becomes the **normalized dict**,
then a FHIR serializer turns that dict into FHIR resources. **No X12 parser or
mapper changes.**

## 1.2 Why (real-world driver)

**CMS-0057-F** (federal final rule) requires impacted payers — Medicare Advantage,
Medicaid, CHIP, and FFE QHPs — to run **four production FHIR APIs by Jan 1, 2027**
(Patient Access, Provider Access, Payer-to-Payer, Prior Authorization). This is
driving a large, deadline-bound wave of X12↔FHIR work across the industry
(Availity, Microsoft, Redix, Flexpa). FHIR is the modern interoperability standard;
adding it positions the tool against the biggest current US interoperability push.

## 1.3 Target users

| User | Need |
|------|------|
| **Healthcare developers** | FHIR R4 output to feed modern APIs / apps |
| **Payer/provider integration teams** | X12 → FHIR to meet CMS-0057-F |
| **Analysts / QA** | Human-readable, standard resources instead of raw X12 |

## 1.4 Supported transaction → resource mappings

| EDI transaction | FHIR R4 resource | Conformance profile (target) | Phase |
|-----------------|------------------|------------------------------|-------|
| 837P / 837I | `Claim` | US Core / Da Vinci PAS | **V2-A** |
| 835 | `ExplanationOfBenefit` | CARIN Blue Button | V2-B |
| 834 | `Coverage` | US Core | V2-C |
| 270 / 271 | `CoverageEligibilityRequest` / `Response` | Da Vinci | V2-C |
| 276 / 277 | `Task` | Da Vinci | V2-C |

> Each resource is packaged in a **Bundle** together with the resources it
> references (Patient, Coverage, Organization, …). See `5-fhir-mapping-reference.md`.

## 1.5 Features

### Must-have (V2-A)
- [ ] Separate **`/fhir` page** (React Router) with a top-nav link
- [ ] Accept **`.edi` / `.dat` / `.json` / `.xml`** (upload / drop / paste)
- [ ] **Auto-detect** input format and transaction type
- [ ] Convert **837 → `Claim`** end-to-end, output a FHIR **Bundle**
- [ ] Render FHIR JSON (reuse the v1 highlighter); **copy** + **download** (`.json`)
- [ ] Reuse **maximize**, **loading animation**, **theme** from v1
- [ ] Friendly message for a transaction type not yet FHIR-mapped

### Later (V2-B / V2-C / V2-D) — all delivered
- [x] 835 → `ExplanationOfBenefit` (V2-B)
- [x] 834, 270/271, 276/277 mappings (V2-C)
- [x] **FHIR validation** — hand-built base-R4 structural validator +
  `/edi/fhir/validate` + automated validity chip (V2-D). *IG profile
  certification (CARIN/US Core/Da Vinci via the HL7 validator) is a CI follow-up.*

### Cross-page convenience
- [x] **Forward to FHIR** button on the Converter result panel — enabled only for
  **JSON/XML** output; redirects to `/fhir` and **prefills** the input (the user
  clicks Convert themselves — no auto-conversion).

## 1.6 Non-goals (v2)
- ❌ Full Implementation-Guide *certification* in V2-A (target is valid base R4;
  profile conformance is the V2-D upgrade).
- ❌ JSON → EDI generation (a separate future initiative).
- ❌ Persistence / storing FHIR output (in-memory, like v1).
- ❌ Accepting arbitrary non-schema JSON/XML.

## 1.7 Success criteria (V2-A)
1. On `/fhir`, uploading an **837** file — *or its v1 JSON/XML output* — returns a
   valid FHIR **Bundle** centered on a `Claim` (+ Patient, Coverage, Organization).
2. Output is structurally valid FHIR R4 JSON.
3. The v1 page and all v1 behavior are unchanged.
