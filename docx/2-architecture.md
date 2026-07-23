# 2 — Architecture

> **Project name:** EDI-Converter
> **Last updated:** 2026-07-21

---

## 2.1 App Flow & Architecture

The engine is decoupled over HTTP, so our own Docker backend is a **drop-in
replacement** for the commercial datainsight.health engine.

### High-level flow

```
┌──────────────────────────────────────────────────────────────────┐
│                          BROWSER (Frontend)                        │
│   React + TypeScript (pure-CSS design system)                      │
│   • Upload / drop / paste EDI  → AUTO-VALIDATES on add             │
│   • Pick transaction type (Auto / 837P / 837I / 835 / 834 / 271 / 277)
│   • Pick output format (JSON / XML / CSV) then Convert             │
│   • View + download result; MAXIMIZE into a large overlay          │
│   • Realistic loading animation (~2 s convert, ~2-3 s validate)    │
└───────────────────────────────┬────────────────────────────────── ┘
                                 │  HTTP (multipart upload / JSON)
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                    BACKEND — main.py (FastAPI)   [Docker]          │
│   • POST /edi/json      convert EDI → JSON                         │
│   • POST /edi/xml       convert EDI → XML                          │
│   • POST /edi/csv       convert EDI → CSV      (Phase 7)           │
│   • POST /edi/validate  validate EDI → issue list (Phase 6)        │
│   • GET  /health        liveness check                            │
│   (Web concerns only: upload, decode, HTTP status, errors)        │
└───────────────────────────────┬────────────────────────────────── ┘
                                 │  plain Python function calls
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                    engine/  (conversion logic)                     │
│   detector.py  → which transaction type?                          │
│   parser       → pyx12 breaks raw X12 into segments/loops         │
│   mappers/     → one per type: shape segments into clean JSON      │
│   validator.py → rule checks, returns issues                      │
│   (No HTTP knowledge — pure, testable Python)                     │
└────────────────────────────────────────────────────────────────── ┘
```

### Request lifecycle (convert to JSON)
1. User drops `claim.dat` and selects "Auto-detect" + "JSON" in the browser.
2. Frontend sends `POST /edi/json` (multipart) to the backend.
3. `main.py` reads the file, decodes it (`utf-8-sig`), calls
   `engine.converter.convert_edi(raw, "auto")`.
4. `detector.py` reads the `ST` segment → `"837"`.
5. `pyx12` parses raw text into a segment/loop tree.
6. `mappers/map_837.py` walks the tree → builds a Python dict.
7. `main.py` returns the dict; FastAPI serializes it to a JSON HTTP response.
8. Frontend renders it in the viewer and enables **Download**.

### Why this split (separation of concerns)
- **`main.py` = waiter** — talks HTTP, no EDI logic.
- **`engine/` = kitchen** — all EDI logic, no HTTP. Fully unit-testable without a
  web server.
- Swapping engines later (or exposing a CLI) touches only one side.

---

## 2.2 Folder & File Structure

```
EDI-Converter/
├── docx/                          # planning docs (this folder)
│   ├── 1-project-requirements.md
│   ├── 2-architecture.md
│   ├── 3-rules.md
│   ├── 4-phases.md
│   ├── 5-design.md
│   └── 6-memory.md
│
├── backend/                       # our Dockerized API — replaces :5080 engine
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                    # FastAPI app: /edi/json, /edi/xml, /edi/csv, /edi/validate
│   ├── config.py                  # settings (limits, CORS, allowed extensions)
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── converter.py           # convert_edi(raw, type) -> dict  (entry point)
│   │   ├── detector.py            # detect_transaction_type(raw) -> "837"|"835"|...
│   │   ├── validator.py           # validate_edi(raw) -> list[Issue]  (Phase 6)
│   │   ├── x12_reader.py          # tokenizer + delimiter auto-detect
│   │   ├── xml_writer.py          # dict -> XML (shared serializer, all types)
│   │   ├── models.py              # Pydantic output models (Claim, Payment, ...)
│   │   └── mappers/
│   │       ├── __init__.py
│   │       ├── map_837.py         # professional + institutional claims
│   │       ├── map_835.py         # remittance / payment
│   │       ├── map_834.py         # enrollment
│   │       ├── map_271.py         # eligibility response
│   │       └── map_277.py         # claim status response
│   └── tests/
│       ├── test_detector.py
│       ├── test_map_837.py
│       ├── test_map_835.py
│       └── fixtures/              # copies of sample EDI files
│
├── frontend/                      # React + TypeScript + Vite
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/client.ts          # calls backend endpoints
│       ├── components/
│       │   ├── FileUpload.tsx     # drag & drop
│       │   ├── TypeSelector.tsx   # transaction-type dropdown
│       │   ├── FormatToggle.tsx   # output-format selector: JSON / XML / CSV
│       │   ├── (result maximize overlay — large centered glass panel)
│       │   ├── (validity chip — auto-validation status in Source header)
│       │   ├── ResultViewer.tsx   # formatted JSON viewer + download
│       │   └── ErrorBanner.tsx
│       ├── styles/                # Tailwind + theme tokens
│       └── types.ts
│
├── samples/                       # example inputs/outputs for demos & tests
│   ├── input/
│   └── output/
│
├── docker-compose.yml             # runs backend + frontend together
├── .env.example
├── .gitignore
└── README.md
```

---

## 2.3 Tech & Stack

### Backend
| Concern | Choice | Why |
|---------|--------|-----|
| Language | **Python 3.11+** | Reuse existing `edi_1500_to_json.py` logic |
| Web framework | **FastAPI** | Async, automatic OpenAPI docs, great DX |
| Server | **Uvicorn** | Standard ASGI server for FastAPI |
| EDI parsing | **our own reader** (`x12_reader.py`) | Ported from the proven `edi_1500_to_json.py`; zero deps, runs on Python 3.14 + Docker |
| JSON output | stdlib `json` | Mapper returns a dict → JSON directly |
| XML output | stdlib (`xml.sax.saxutils`) | Shared `xml_writer.to_xml(dict)` over any mapper — no new dependency |
| Data models | **Pydantic v2** | Typed, validated output |
| Testing | **pytest** | Standard, simple |

> We use our own parser rather than `pyx12` (see decision log in `6-memory.md`).
> XML is produced by one shared serializer that turns any mapper's dict into
> XML, so new transaction types get XML for free.

### Frontend
| Concern | Choice | Why |
|---------|--------|-----|
| Framework | **React 18 + TypeScript** | Component model, type safety, large ecosystem |
| Build tool | **Vite** | Fast dev server & builds |
| Styling | **Tailwind CSS** | Fast, consistent styling (tokens in `5-design.md`) |
| JSON viewer | lightweight tree component (or custom) | Collapsible result display |
| Testing | **Vitest** | Vite-native unit testing |

### Infrastructure
| Concern | Choice |
|---------|--------|
| Containers | **Docker** + **docker-compose** |
| Backend port | `:5080` (keeps parity with old engine, optional) |
| Frontend port | `:5173` (Vite) / `:80` in production build |
| Config | environment variables via `.env` |

### Data flow contract (our own API — not datainsight's)
- `POST /edi/json?type=auto` → `{ "transaction_type": "...", "data": {...} }`
- `POST /edi/xml?type=auto` → `application/xml` (shared serializer over the
  mapper's dict output — works for every transaction type)
- `POST /edi/csv?type=auto` → `text/csv` (Phase 7)
- `POST /edi/validate` → `{ "issues": [ { "severity", "message", "segment", "line" } ] }`
- `GET /health` → `{ "status": "ok" }`

We define this contract ourselves (Option 2 from the analysis), so we are free of
the commercial schema.
