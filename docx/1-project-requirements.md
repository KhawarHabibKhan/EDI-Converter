# 1 — Project Requirements Document

> **Project name:** EDI-Converter
> **Status:** Planning
> **Last updated:** 2026-07-21

---

## 1.1 What to Build

A self-hosted web application that converts **healthcare X12 EDI files** into
clean, structured **JSON** and **XML** (and optionally CSV), with built-in
**validation**.

The product has three parts:

1. **Frontend (web UI)** — a browser page where a user uploads an EDI file,
   chooses the transaction type and output format, and views/downloads the
   result.
2. **Backend (our own Dockerized API)** — a FastAPI service that parses the EDI
   and returns JSON. **This replaces the commercial datainsight.health engine**
   that the existing `python/` folder depends on. No commercial license, no
   external Docker image — the engine is ours.
3. **Conversion engine** — a Python package (built on an open-source X12 parser)
   with one mapper per transaction type.

### The core problem we solve
Raw X12 EDI looks like this and is unreadable to humans and most apps:

```
ISA*00*   *00*   *ZZ*SENDER*ZZ*RECEIVER*240115*1200*^*00501*000000001*0*P*:~
CLM*PATACCT001*350.00***11:B:1*Y*A*Y*Y~
```

We turn it into this:

```json
{ "claim": { "patient_account_no": "PATACCT001", "total_charge": "350.00" } }
```

### Explicit non-goals (what we are NOT building)
- We are **not** re-licensing or bundling the datainsight.health engine.
- We are **not** building a full clearinghouse (no submitting claims to payers).
- We are **not** storing PHI long-term in v1 (files processed in-memory, then
  discarded). A persistence/database layer is a later, optional phase.
- We are **not** building user accounts / multi-tenant auth in v1.

---

## 1.2 Target Users

| User | Who they are | What they need |
|------|--------------|----------------|
| **Healthcare developers** | Engineers integrating EDI into apps | A JSON API they can call; predictable output schema |
| **Billing / claims staff** | Non-technical office users | A simple upload page that shows readable results |
| **Analysts** | People auditing claims/payments | CSV export to open in Excel; readable field names |
| **QA / integration testers** | People checking EDI files are correct | Validation report showing what's wrong and where |

**Primary user for v1:** the developer + the billing/claims staff (the upload
page). Everything else builds on those two.

---

## 1.3 Features

### Must-have (v1 / MVP)
- [ ] Upload an EDI file (`.edi`, `.dat`, `.txt`) via drag-and-drop or file picker
- [ ] **Auto-detect** the transaction type from the file
- [ ] Manual **transaction-type selector**: `837P · 837I · 835 · 834 · 271 · 277`
- [ ] **Output-format selector** — user picks the format, then converts
- [ ] Convert to **JSON** and show it in a formatted, highlighted viewer
- [ ] Convert to **XML** (shared serializer over any transaction type)
- [ ] **Download** the result (JSON/XML), named after the input file
- [ ] Clear **error messages** when a file is not valid EDI
- [ ] Backend runs fully inside **Docker** (no external engine)

### Should-have (v2)
- [ ] **CSV** output format for tabular data (claims, service lines, payments)
- [ ] **Validation report** — list of issues with segment/line references
- [ ] **Batch upload** — convert many files at once (mirrors the existing
      `Input files/` → `Output files/` workflow)
- [ ] Copy-to-clipboard for the JSON result

### Nice-to-have (later)
- [ ] EDI **generation** (JSON → EDI) — reverse direction
- [ ] Saved conversion history / search (like the `viewer/` scripts:
      `/claims`, `/payments`)
- [ ] User accounts and API keys
- [ ] Dark mode (see design doc)

---

## 1.4 Supported Transaction Types

| Code | X12 name | Plain meaning | Paper equivalent |
|------|----------|---------------|------------------|
| **837P** | Health Care Claim: Professional | Doctor/clinic claim | CMS-1500 |
| **837I** | Health Care Claim: Institutional | Hospital/facility claim | UB-04 |
| **835** | Health Care Claim Payment/Advice | Remittance / payment (ERA) | — |
| **834** | Benefit Enrollment & Maintenance | Member enrollment | — |
| **271** | Eligibility Benefit Response | "Is this patient covered?" answer | — |
| **277** | Health Care Claim Status Response | "What's the status of my claim?" | — |

> v1 delivers **837P** end-to-end first (we already have a working mapper in
> `Health care EDI/edi_1500_to_json.py`). The other five are added in phases —
> see `4-phases.md`.

---

## 1.5 Success Criteria

The project is "done" for v1 when:
1. A user can upload a real 837P `.dat` file in the browser and get correct JSON.
2. The backend runs with a single `docker compose up` — no datainsight license.
3. Auto-detection correctly identifies all 6 transaction types.
4. Invalid files produce a helpful error, not a crash.
5. All backend mappers have passing unit tests against the sample files in
   `Health care EDI/Input files/`.

---

## 1.6 Inputs & Outputs (reference)

- **Input examples available today:**
  `Health care EDI/Input files/837P-all-fields.dat`,
  `Health care EDI/Input files/271/*.edi`
- **Output today:** `Health care EDI/Output files/*.json`
- The new app keeps this same flow but drives it through a UI + API.
