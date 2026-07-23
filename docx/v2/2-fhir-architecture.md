# v2 · 2 — FHIR Architecture

> **Project:** EDI-Converter — Version 2 (FHIR R4)
> **Last updated:** 2026-07-23

---

## 2.1 End-to-end flow

Everything funnels into the v1 **normalized dict**, then a FHIR serializer emits a
Bundle. FHIR mapping is written **once**, against the dict.

```
┌──────────────────────────────────────────────────────────────────────┐
│  FHIR CONVERTER PAGE  (/fhir)   — React + React Router                 │
│  upload / drop / paste  (.edi · .dat · .json · .xml)                   │
└───────────────────────────────┬────────────────────────────────────── ┘
                                 │  POST /edi/fhir (multipart)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  main.py  (FastAPI)                                                    │
│    _read_upload → input_adapter.detect_and_load → fhir.writer.to_fhir  │
└───────────────────────────────┬────────────────────────────────────── ┘
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  engine/input_adapter.py                                               │
│    .edi/.dat → x12_reader + mappers (v1)  ─┐                           │
│    .json     → json.loads                  ─┼─► normalized dict         │
│    .xml      → xml_reader (NEW)            ─┘   (+ transaction type)    │
└───────────────────────────────┬────────────────────────────────────── ┘
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  engine/fhir/  (NEW, hand-built, zero deps)                            │
│    writer.py  → dispatch by transaction type → per-resource mapper     │
│    map_claim.py / map_eob.py / …  → resource dicts                     │
│    common.py  → References, Identifiers, CodeableConcept, system URIs   │
│    → assemble FHIR Bundle (type: collection)                           │
└───────────────────────────────┬────────────────────────────────────── ┘
                                 ▼
                    application/fhir+json  (a FHIR Bundle)
```

## 2.2 Backend structure (additions only)

```
backend/
├── main.py                     # + POST /edi/fhir
└── engine/
    ├── input_adapter.py        # NEW: detect edi/json/xml → (dict, type)
    ├── xml_reader.py           # NEW: our-schema XML → dict (reverse of xml_writer)
    └── fhir/                   # NEW: FHIR mapping package
        ├── __init__.py
        ├── writer.py           # to_fhir(dict, type) -> Bundle dict (dispatch)
        ├── common.py           # builders + code-system URI table
        ├── map_claim.py        # 837P/837I -> Claim (+ Patient/Coverage/Organization)  [V2-A]
        ├── map_eob.py          # 835      -> ExplanationOfBenefit                       [V2-B]
        ├── map_coverage.py     # 834      -> Coverage                                   [V2-C]
        ├── map_eligibility.py  # 270/271  -> CoverageEligibilityRequest/Response        [V2-C]
        └── map_task.py         # 276/277  -> Task                                       [V2-C]
```

### Module contracts
- `input_adapter.detect_and_load(text, filename) -> (dict, transaction_type)`
  - `ISA…` / has X12 segments → `converter.convert_edi(text, "auto")`
  - `{…` → `json.loads(text)` (already our dict; read `source_transaction`)
  - `<?xml…` / `<…` → `xml_reader.to_dict(text)`
  - otherwise → raise → HTTP 400 "unrecognized input format"
- `xml_reader.to_dict(xml) -> dict` — reverse of `xml_writer`: element tree →
  dict/list/scalars; `<item>` children rebuild lists. Our XML is regular, so this
  is deterministic.
- `fhir.writer.to_fhir(dict, transaction_type) -> dict` — picks the resource mapper
  by type, builds the primary resource + referenced resources, wraps in a Bundle.
  Unmapped-yet types raise `UnsupportedFhirError` → HTTP 400 with a "arrives in
  V2-x" message (mirrors the v1 unsupported-type pattern).

## 2.3 API contract

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `POST` | `/edi/fhir` | multipart file (`.edi/.dat/.json/.xml`) | `application/fhir+json` — a FHIR Bundle |

- Reuses `_read_upload` (size/extension/empty checks; extension allow-list widened
  to include `.json`, `.xml`).
- Errors follow the v1 convention: 400 (bad/unsupported input), 413 (too large),
  500 (unexpected, no PHI leaked).

## 2.4 Frontend structure

The single-page app is refactored into two routed pages.

```
frontend/src/
├── main.tsx                # wrap <App/> in <BrowserRouter>
├── App.tsx                 # shell (header + nav) + <Routes>
├── pages/
│   ├── ConverterPage.tsx   # existing v1 UI, moved out of App
│   └── FhirPage.tsx        # NEW — the FHIR converter
├── components/             # shared: header/nav, upload, result viewer, overlay …
├── api/client.ts           # + convertFhir(text, fileName, base)
└── lib/edi.ts              # highlightJSON reused for FHIR output
```

- **Routes:** `/` → `ConverterPage`, `/fhir` → `FhirPage`.
- **Top nav** in the header: **Converter** · **FHIR Converter**.
- **"Forward to FHIR" hand-off:** the Converter result panel shows a
  **Forward to FHIR** button, enabled **only for JSON or XML** output (the two
  formats the FHIR input adapter accepts as our-schema exports — CSV, validation
  reports, and batch output are not convertible, so the button is disabled for
  them). Clicking it navigates to `/fhir` (via React Router navigation `state`)
  and **prefills** the FHIR page's input with that output — it does **not**
  auto-convert; the user reviews the prefilled input and clicks **Convert to
  FHIR** themselves. Implemented in the shared `ResultPanel` (`onForward` prop);
  `ConverterPage` supplies the navigate, `FhirPage` consumes the router state
  once on mount and clears it (so back/refresh won't refire).
- `FhirPage` reuses the glass layout, upload/drop/paste, maximize, copy/download,
  loading animation, theme. Differences: wider file accept (`.edi,.dat,.json,.xml`),
  no format/type selectors (output is always FHIR, type auto-detected), badge shows
  **`FHIR · <ResourceType>`** + profile chip.

## 2.5 Tech & dependencies

| Concern | Choice |
|---------|--------|
| FHIR serialization | **Hand-built dicts** (stdlib `json`) — **zero new runtime deps** |
| XML input parsing | stdlib `xml.etree.ElementTree` |
| FHIR validation (v2) | **reuse the existing structural validator**; real FHIR profile validation is the **V2-D** upgrade |
| Frontend routing | **`react-router-dom`** (first frontend runtime dep) |

## 2.6 What is reused vs new

| Reused from v1 (unchanged) | New in v2 |
|----------------------------|-----------|
| `x12_reader`, `detector`, `converter`, all X12 mappers | `input_adapter`, `xml_reader`, `fhir/` package |
| `xml_writer`, `csv_writer`, `validator` | `POST /edi/fhir` route |
| Glass UI, upload, result viewer, maximize, loading, theme | `/fhir` page, top-nav, React Router |
