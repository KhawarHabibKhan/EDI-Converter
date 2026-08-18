# EDI-Converter — User Manual

Turn healthcare X12 EDI files into readable JSON, XML, CSV or FHIR — and find out
what is wrong with them before a payer does.

| | |
|---|---|
| **Audience** | Billing and claims staff, integration developers, QA |
| **Applies to** | EDI-Converter v0.1 (SNIP Levels 1–5, FHIR R4) |
| **You need** | A browser and an EDI file. No account, no install. |

---

## Contents

1. [What it does](#1-what-it-does)
2. [Loading a file](#2-loading-a-file)
3. [Converting](#3-converting)
4. [Reading the validation report](#4-reading-the-validation-report)
5. [The FHIR converter](#5-the-fhir-converter)
6. [For developers — the API](#6-for-developers--the-api)
7. [Troubleshooting](#7-troubleshooting)
8. [Privacy](#8-privacy)

---

## 1. What it does

An X12 EDI claim file is a wall of asterisks and tildes that no human is meant to
read. EDI-Converter turns it into something you can work with, and checks it
against the industry's standard validation levels at the same time.

```
CLM*PATACCT001*150.00***11:B:1*Y*A*Y*Y~
```

becomes

```json
{ "patient_account_no": "PATACCT001", "total_charge": "150.00" }
```

### Supported transaction types

| Code | What it is | Paper equivalent |
|------|------------|------------------|
| **837P** | Professional claim — doctor or clinic | CMS-1500 |
| **837I** | Institutional claim — hospital or facility | UB-04 |
| **835** | Payment / remittance advice (ERA) | — |
| **834** | Benefit enrolment and maintenance | — |
| **270 / 271** | Eligibility request and response | — |
| **276 / 277** | Claim status request and response | — |

You do not have to tell it which one you have — it reads the file and works it
out. The type dropdown exists for when you want to force a specific reading.

---

## 2. Loading a file

Open the converter and get your EDI in front of it, whichever way suits you:

- **Drag and drop** the file onto the source panel.
- **Upload** — click the button and pick a file.
- **Paste** the raw EDI text straight into the panel.
- **Load a sample** if you just want to see how it behaves.

Accepted extensions are `.edi`, `.dat`, `.txt` and `.x12`, up to 10 MB.

> **Validation starts on its own.** The moment a file lands, it is validated —
> you do not click anything to begin. A validity chip appears in the source
> header and the full report shows in the output panel.

---

## 3. Converting

1. **Choose the output format** — JSON, XML or CSV.
   - *JSON* keeps the full structure.
   - *XML* mirrors it.
   - *CSV* flattens to one row per service line, payment or benefit — this is
     what you want for Excel.
2. **Leave the type on Auto** unless you have a reason not to.
3. **Click Convert.** The result appears on the right, syntax-highlighted.
4. **Copy or download it.** The download is named after your input file.

Two features make long output easier to live with:

- **Maximize** expands the result into a large centred overlay. Close it with the
  ✕, the `Esc` key, or by clicking outside it.
- **Batch upload** accepts several files at once and gives you one combined
  download plus a per-file status list.

---

## 4. Reading the validation report

Validation follows the **WEDI SNIP levels** — the industry's shared vocabulary
for "how deeply was this checked". Levels are **cumulative**: choosing Level 5
also runs 1 through 4. Level 5 is the default.

| Level | Name | Catches |
|-------|------|---------|
| **L1** | Integrity | Broken envelope — ISA/IEA and GS/GE mismatches, wrong control numbers, segment counts that do not add up |
| **L2** | Requirement | Missing segments or elements the implementation guide requires for that transaction type |
| **L3** | Balancing | Money that does not reconcile — claim total ≠ sum of service lines; remittance payments that do not add up |
| **L4** | Situational | "If A, then B" rules — an accident-related claim with no accident date, COB without the other-payer loop |
| **L5** | Code sets | Codes that are not real — invalid ICD-10-CM diagnoses, ICD-10-PCS procedures, HCPCS, place of service |

Each issue card carries the level that raised it, the segment involved, and a
message naming the actual numbers. A balancing failure reads like:

> **L3 ERROR · CLM** — CLM02 claim total 150.00 does not equal the sum of
> service-line charges 100.00.

Both sides of the equation, so you can go straight to the fix.

> **On CPT codes.** Five-digit CPT procedure codes are checked for *format* only,
> never membership. CPT is licensed by the AMA, so the code list is not bundled.
> The report states this explicitly rather than quietly passing them.

---

## 5. The FHIR converter

The **FHIR** page turns the same files into FHIR R4 Bundles — the format modern
clinical systems and APIs expect.

| Input | Becomes |
|-------|---------|
| 837P / 837I | `Claim` |
| 835 | `ExplanationOfBenefit` |
| 834 | `Coverage` |
| 270 / 271 | `CoverageEligibilityRequest` / `Response` |
| 276 / 277 | `Task` |

Each Bundle also contains the `Patient`, `Organization` and `Coverage` resources
it references.

It accepts this app's own JSON and XML exports as well as raw X12, so you can
convert once and take the output onward. The **Forward to FHIR** button on a JSON
or XML result carries it across for you.

**Validation here checks both ends** — the source file against the SNIP levels
*and* the generated Bundle against FHIR R4 structure. That matters because the
mappers are forgiving: a broken 837 can still produce a structurally valid
Bundle, and checking only the output would call that a pass.

---

## 6. For developers — the API

Every screen action is a plain HTTP endpoint. No key, no session.

| Method | Endpoint | Returns |
|--------|----------|---------|
| `GET` | `/health` | Liveness JSON |
| `POST` | `/edi/json?type=auto` | `{transaction_type, file_name, data, issues}` |
| `POST` | `/edi/xml?type=auto` | `application/xml` |
| `POST` | `/edi/csv?type=auto` | `text/csv` |
| `POST` | `/edi/validate?snip_level=1..5` | Validation report with levelled issues |
| `POST` | `/edi/fhir` | `application/fhir+json` — an R4 Bundle |
| `POST` | `/edi/fhir/validate` | Combined SNIP + FHIR R4 report |

```bash
curl -X POST -F "file=@claim.edi" \
     "http://localhost:5080/edi/validate?snip_level=5"
```

```json
{"file_name":"claim.edi","transaction_type":"837P","snip_level":5,
 "valid":true,"error_count":0,"warning_count":0,"issues":[]}
```

- Interactive API docs are served at `/docs`.
- `type` accepts `auto` (default) or any specific transaction code.
- `snip_level` defaults to the highest implemented level (5).
- `/edi/fhir*` also accept `.json` / `.xml` exports from this app.

---

## 7. Troubleshooting

| You see | Meaning | Do this |
|---------|---------|---------|
| Unsupported file type | Extension is not `.edi`, `.dat`, `.txt` or `.x12` | Rename it, or paste the contents instead |
| File exceeds the 10 MB limit | Upload ceiling reached | Split the batch, or raise `EDI_MAX_FILE_MB` on the server |
| No EDI segments found | Not an X12 interchange — often a PDF or spreadsheet renamed | Check the file really starts with `ISA` |
| Conversion works, validation fails | Normal. The parser is lenient, the validator is strict | Read the issue list — that is the point of the tool |
| Everything times out | The API base URL in Options is wrong, or the backend is down | Open `/health` in a browser tab |

---

## 8. Privacy

Uploads are processed **in memory and discarded**. Nothing is written to disk,
nothing is stored in a database, and error messages never quote the contents of
your file back at you. There is no account system because there is nothing to
keep.

---

*For deployment and operations, see [`deploy/README.md`](../deploy/README.md).*
