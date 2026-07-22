# 4 — Development Phases

> **Project name:** EDI-Converter
> **Last updated:** 2026-07-21
>
> Build in order. Do not start a phase until the previous one's "Done when"
> checklist is met. Track live progress in `6-memory.md`.

---

## Phase 0 — Project Setup & Scaffolding

Get the skeleton running end-to-end with a "hello world" before any EDI logic.

- **0.1** Create folder structure (`backend/`, `frontend/`, `samples/`) per
  `2-architecture.md`.
- **0.2** Backend: minimal FastAPI app with `GET /health` returning `{status:ok}`.
- **0.3** Backend `Dockerfile` + `requirements.txt`; container builds and runs.
- **0.4** Frontend: Vite + React + TS + Tailwind, blank page that calls `/health`.
- **0.5** `docker-compose.yml` runs both; frontend can reach backend.

**Done when:** `docker compose up` serves a page that shows the backend health.

---

## Phase 1 — 837P Conversion (the vertical slice)

Prove the whole pipeline with the transaction type we already understand.

- **1.1** Add `pyx12` and build `engine/x12_reader.py` (raw text → segment tree).
- **1.2** Port `edi_1500_to_json.py` logic into `engine/mappers/map_837.py`.
- **1.3** Build `engine/converter.py` entry point (`convert_edi`).
- **1.4** Wire `POST /edi/json` in `main.py` to the converter.
- **1.5** Tests: `test_map_837.py` against `Input files/837P-all-fields.dat`.
- **1.6** Frontend: `FileUpload`, `ResultViewer`, download button — upload a real
  837P file and see JSON.
- **1.7** **XML output** (added early): `engine/xml_writer.py` (shared dict→XML
  serializer) + `POST /edi/xml`. Frontend gains an **output-format selector
  (JSON / XML)** and a single **Convert** button.

**Done when:** a user uploads `837P-all-fields.dat` in the browser, picks a
format, and gets correct JSON or XML, all backed by our own Docker container.

---

## Phase 2 — Auto-Detection & Type Selector

- **2.1** `engine/detector.py` — read `ST` segment → transaction type.
- **2.2** `convert_edi(raw, "auto")` uses the detector.
- **2.3** Frontend `TypeSelector.tsx`: `Auto · 837P · 837I · 835 · 834 · 271 · 277`.
- **2.4** Tests for detection across all sample types.

**Done when:** auto-detect correctly identifies every sample file's type.

---

## Phase 3 — Remaining Claim Type: 837I

- **3.1** Extend `map_837.py` (or add `map_837i.py`) for institutional specifics
  (revenue codes, DRG, occurrence codes, UB-04 fields).
- **3.2** Tests against an 837I sample.

**Done when:** 837I files convert with institutional fields present.

---

## Phase 4 — Financial & Enrollment: 835 & 834

- **4.1** `map_835.py` — payer, payee, claim payments, adjustments (CAS), PLB.
- **4.2** `map_834.py` — sponsor, payer, member coverage, dates.
- **4.3** Tests for both.

**Done when:** 835 and 834 files produce correct JSON.

---

## Phase 5 — Eligibility & Status: 271 & 277

- **5.1** `map_271.py` — information source → receiver → subscriber →
  eligibility/benefit loops (mirror the hierarchy in the existing
  `convert_271.py`).
- **5.2** `map_277.py` — payer/provider/patient claim-status loops.
- **5.3** Tests against `Input files/271/*.edi`.

**Done when:** all 6 transaction types convert end-to-end.

---

## Phase 6 — Validation

- **6.1** `engine/validator.py` — structural + basic rule checks → issue list.
- **6.2** `POST /edi/validate` endpoint.
- **6.3** Frontend `FormatToggle.tsx` gains a "Validation" mode + issue display.

**Done when:** an invalid file returns a clear, structured issue list in the UI.

---

## Phase 7 — CSV Output & Batch

- **7.1** CSV serialization for tabular data (claims, service lines, payments).
- **7.2** `POST /edi/csv` endpoint + frontend format toggle.
- **7.3** Batch upload (multiple files) mirroring `Input files/` → `Output files/`.

**Done when:** user can export CSV and process multiple files at once.

---

## Phase 8 — Polish & Hardening

- **8.1** Apply full design system from `5-design.md` (theme, typography, states).
- **8.2** Error handling review against `3-rules.md` (limits, messages, statuses).
- **8.3** Loading states, empty states, responsive layout.
- **8.4** README with run instructions; `.env.example`.
- **8.5** End-to-end pass with all sample files.

**Done when:** the app is presentable, robust, and documented.

---

## Later / Optional (post-v1)

- EDI **generation** (JSON → EDI).
- **Persistence** + search (`/claims`, `/payments`, analytics) — needs a PHI/
  security review first.
- **Auth** (accounts, API keys).
- **Dark mode**.

---

### Phase dependency map

```
0 ─► 1 ─► 2 ─► 3 ─► 4 ─► 5 ─► 6 ─► 7 ─► 8
          │
          └─ (2 unlocks all later mappers via auto-detect)
```

Each mapper phase (3,4,5) is independent once Phase 2 is done, so they can be
reordered by priority if needed.
