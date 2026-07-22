# 6 — Project Memory (Living Progress Log)

> **Project name:** EDI-Converter
> **Last updated:** 2026-07-21 (Phases 0–8 COMPLETE — project done)
>
> This is the **living state** of the project. Read this FIRST before working.
> Update it whenever something is completed, started, or changed.
> Keep it honest — it is the single source of truth for "where are we?"

---

## 6.1 What Has Been Completed

- [X] **Analysis** — reviewed the existing `python/` folder (datainsight.health
  commercial SDK) and confirmed the engine is a licensed Docker API, not
  source we can edit.
- [X] **Decision** — build our OWN Dockerized backend to replace the commercial
  engine (Path B / Option 2: our own API contract + frontend).
- [X] **Reference parser exists** — `Health care EDI/edi_1500_to_json.py` already
  converts 837P → CMS-1500 JSON. This becomes the basis for `map_837.py`.
- [X] **Planning docs written** — eight docs in `EDI-Converter/docx/`:
  requirements, architecture, rules, phases, design, memory, plus
  `7-backend-plan.md` and `8-frontend-plan.md`.
- [X] **Phase 0 — Scaffolding COMPLETE & VERIFIED:**
  - `backend/` FastAPI app with `GET /health` + `GET /` — verified via real
  uvicorn run and `pytest` (2/2 passing).
  - `backend/Dockerfile`, `requirements.txt`, `config.py`, `engine/` package
  skeleton.
  - `frontend/` React + TS + Vite + Tailwind — `npm run build` succeeds;
  `App.tsx` calls `/health` and shows connection status.
  - `docker-compose.yml` (validated), root `README.md`, `.env.example`,
  `.gitignore`, `samples/` folders.
- [X] **Phase 1 — 837P conversion COMPLETE & VERIFIED (vertical slice):**
  - `engine/x12_reader.py` — tokenizer + ISA delimiter auto-detect.
  - `engine/mappers/map_837.py` — full 837P mapper (ported from
  `edi_1500_to_json.py`); also flags 837I via X223 implementation guide.
  - `engine/converter.py` — `convert_edi(raw, type)` with dispatch table.
  - `POST /edi/json` in `main.py` — upload validation (size/ext/empty),
  structured errors, returns `{transaction_type, file_name, data, issues}`.
  - Tests: **10/10 passing** (`test_map_837.py`, `test_api.py`) incl. the
  real `837P-all-fields.dat` and `sample_837p.edi` fixtures.
  - Frontend: `FileUpload` (drag/drop + a11y), `ResultViewer` (JSON + copy +
  download), `ErrorBanner`; `App.tsx` orchestrates upload→convert→view.
  `npm run build` passes.
  - **End-to-end verified:** real 837P POSTed over HTTP → correct JSON.
- [X] **Phase 2 — Auto-detection & type selector COMPLETE & VERIFIED:**
  - `engine/detector.py` — `detect_transaction_type(raw)` / `detect_from_doc`
  read the ST segment (+ ST03/GS08 version to split 837P vs 837I).
  - `converter.convert_edi(raw, "auto")` parses once, detects, dispatches;
  recognized-but-unmapped types (835/834/271/277) raise a friendly
  `UnsupportedTransactionError` naming the type + its future phase.
  - `/edi/json` and `/edi/xml` now default `type=auto`.
  - Frontend: **Transaction-type dropdown** (Auto · 837P · 837I · 835 · 834 ·
  271 · 277) in Options, passed through to the API; removed the old
  client-side 837-only gate (backend decides now).
  - Tests: **27/27 passing** (added `test_detector.py`, API auto + 400 tests).
- [X] **Phase 3 — 837I (Institutional / UB-04) COMPLETE & VERIFIED:**
  - `map_837.py` extended: detects institutional (X223) up front and emits
  UB-04 fields — SV2 service lines (revenue code / HCPCS / units / charge),
  CL1 admission (type/source/patient status), type-of-bill, DRG, procedures
  (ICD-10-PCS), occurrence / value / condition codes, statement + admission
  dates, attending/operating providers.
  - **Field rename** (shared by both forms): `box_26_patient_account_no → patient_account_no`, `box_28_total_charge → total_charge`,
  `box_24_service_lines → service_lines`, SBR boxes → plain names. Inner
  line fields keep CMS-1500 (`box_24*`) vs UB-04 (`box_42/44/46/47`) names.
  - New `tests/fixtures/837I-sample.edi` + `test_map_837i.py`.
  - Tests: **32/32 passing**. Works for both JSON and XML (shared serializer).
- [X] **Phases 4 & 5 — 835 / 834 / 271 / 277 COMPLETE & VERIFIED:**
  - Shared `mappers/_common.py` (name/date parsing, entity map).
  - `map_835.py` — payment (BPR/TRN), payer/payee (N1), claim payments (CLP),
  service payments (SVC), adjustments (CAS group/reason/amount), PLB.
  - `map_834.py` — sponsor/payer (N1), members (INS) with demographics,
  references, and health coverage (HD) + dates.
  - `map_271.py` — HL hierarchy (source→receiver→subscriber→dependent) with
  EB eligibility/benefit segments (service-type repetition split).
  - `map_277.py` — claim-status loops with STC composite (category/status/
  entity), per-claim + per-service statuses.
  - Registered all four in `converter._MAPPERS`; `_PLANNED` now only 270/276.
  - Fixtures: real `271-sample.edi` + authored `835/834/277-sample.edi`.
  Tests `test_map_financial.py` + `test_map_eligibility.py`.
  - **All 6 transaction types now convert end-to-end.** Tests: **41/41**.
  - **270 & 276 added** (request-side twins): `map_271` also handles 270 (EQ
  inquiry segments), `map_277` also handles 276. Registered in dispatch;
  `_PLANNED` now empty. Frontend dropdown lists 270/276 too. Tests: **42/42**.
  (Note: files in the `271/` folder named "…request…" are actually 270s.)
- [X] **Phase 6 — Validation COMPLETE:** `engine/validator.py` (ISA/IEA, GS/GE,
  ST/SE pairing, control-number matching, segment counts) → issue list;
  `POST /edi/validate` → `{valid, error_count, warning_count, issues[]}`;
  frontend **Validate** button + issue cards + summary stats.
- [X] **Phase 7 — CSV & Batch COMPLETE:** `engine/csv_writer.py` (per-type row
  builders: 837 lines, 835 payments, 834 coverages, 271/270 benefits,
  277/276 statuses); `POST /edi/csv`; frontend **CSV** format + table view;
  **batch** multi-file upload → combined JSON/XML/CSV download + status list.
- [X] **Phase 8 — Polish COMPLETE:** full glassmorphism design system, light/dark,
  loading/empty/error states, responsive; error handling reviewed; README
  rewritten with API table + features; fixed SE counts in all sample files so
  they validate clean.

## 6.2 Which Component / Feature We Are Working On

- **Current phase:** _All phases (0–8) complete._ Project is feature-complete.
- **Current component:** none — maintenance / optional post-v1 items only.
- **Next action (optional / post-v1):** EDI generation (JSON→EDI), persistence +
  search, auth, per-file batch validation. See `4-phases.md` "Later / Optional".

## 6.3 Currently On Which File / Folder

- **Active folder:** whole project stable; nothing in progress.
- **Ports:** backend `:5080`, frontend Docker `:8091`, frontend dev `:5173`.
- **Run tests:** `cd backend && python -m pytest -q` (currently **51 passing**).

---

## 6.4 Progress by Phase

| Phase | Description                      | Status  |
| ----- | -------------------------------- | ------- |
| 0     | Setup & scaffolding              | ✅ Done |
| 1     | 837P conversion (vertical slice) | ✅ Done |
| 2     | Auto-detection & type selector   | ✅ Done |
| 3     | 837I                             | ✅ Done |
| 4     | 835 & 834                        | ✅ Done |
| 5     | 271 & 277                        | ✅ Done |
| 6     | Validation                       | ✅ Done |
| 7     | CSV output & batch               | ✅ Done |
| 8     | Polish & hardening               | ✅ Done |

Legend: ⬜ Not started · 🟨 In progress · ✅ Done

---

## 6.5 Key Decisions Log

| Date       | Decision                                                                        | Reason                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ---------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-07-21 | Replace datainsight engine with our own Docker backend                          | Avoid commercial license; own the stack                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2026-07-21 | Stack: FastAPI + pyx12 + Pydantic (backend), React + Vite + Tailwind (frontend) | Reuse Python EDI work; modern, well-supported                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| 2026-07-21 | Define our own API contract (not datainsight's schema)                          | Freedom + avoid IP/licensing risk                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-07-21 | Deliver 837P end-to-end first                                                   | We already have a working mapper for it                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 2026-07-21 | No PHI persistence in v1                                                        | Reduce compliance surface; in-memory only                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 2026-07-21 | Use our own proven parser (not pyx12) for the engine                            | `edi_1500_to_json.py` already works on real files; zero deps; runs on Python 3.14 + Docker. Revisit a library only if a transaction type proves too complex.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-07-21 | Frontend host port 8080 →**8091**                                        | Port 8080 was occupied by another app on the user's machine, so the frontend container failed to bind (looked like "frontend not running"; the 500 was the other app on 8080). Backend verified healthy. Docker stack now runs: frontend :8091, backend :5080.                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 2026-07-21 | Added**XML output** + format selector; replaced "To CSV" with "To XML"    | User request. Backend:`engine/xml_writer.py` (shared dict→XML serializer, stdlib only) + `POST /edi/xml`; `_convert_or_raise` helper shared by /edi/json and /edi/xml. Tests 14/14 (added `test_xml.py` + API test). Frontend: step ③ is now an **output-format selector (JSON / XML)** + a single **Convert** button (removed CSV/Validate buttons). XML rendered with tag highlighting; download `.xml`. All 8 docx updated. CSV stays Phase 7, validation Phase 6.                                                                                                                                                                                                           |
| 2026-07-21 | Frontend re-skinned to match the datainsight reference design                   | User supplied the reference`index.html`. Adopted: aurora animated background, Sora/Manrope/JetBrains Mono fonts, full CSS design system (teal `#0d9488`/cyan `#22d3ee` tokens), header + source + options + 3-action layout, JSON syntax highlight, placeholder/loading/error/info result states. Dropped Tailwind (pure CSS now); postcss = autoprefixer only. App.tsx is self-contained (old components removed). **To JSON** works against our backend (text sent as Blob to /edi/json?type=837P); **To CSV** → honest "Phase 7" info state, **Validate** → "Phase 6" info state; non-837 input → honest "not supported yet" info. Client-side `detectType()` gates it. |
| 2026-07-21 | Frontend redesigned with**glassmorphism** (colors kept)                   | User request. Frosted glass panels, teal→cyan→lavender gradient bg, dark mode, Space Grotesk display font. New components: Header, SourcePanel (paste+drop+**Upload button**+sample), OptionsPanel (API base, file name, Validate/NDJSON toggles — toggles are visual until Phases 6/7), ResultPanel (empty/loading/error/JSON + copy/download). Old FileUpload/ResultViewer/ErrorBanner removed. Text is sent as a Blob to the existing /edi/json (no backend change). NOTE: requested `frontend-design` skill is not available in this environment.                                                                                                                                        |

---

## 6.6 Open Questions / To Confirm

- [ ] Confirm final X12 library: **pyx12** vs `bots` vs `badX12` (Phase 1.1).
- [ ] Confirm we have sample files for **every** type (have 837P + 271; need
  837I, 835, 834, 277 samples for tests).
- [ ] Backend port: keep `:5080` for parity, or move to a fresh port?
- [ ] Deployment target for later (local only, or a server)?

---

## 6.7 How To Update This File

When you finish something:

1. Move the item to **6.1 Completed** (check the box).
2. Update **6.2 / 6.3** to point at the new current phase/component/file.
3. Flip the phase status in **6.4**.
4. Log any real decision in **6.5**.
5. Update the `Last updated` date at the top.
