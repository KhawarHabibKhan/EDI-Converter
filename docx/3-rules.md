# 3 — Rules & Conventions

> **Project name:** EDI-Converter
> **Last updated:** 2026-07-21
>
> These are the guardrails for anyone (human or AI) working on this project.
> Follow them unless a doc explicitly overrides them.

---

## 3.1 What to Use

### Backend
- **Python 3.11+** with type hints on all public functions.
- **FastAPI** for the API layer, **Uvicorn** to serve it.
- **pyx12** for low-level X12 parsing (do not hand-roll a full X12 tokenizer —
  reuse a proven library).
- **Pydantic v2** models for every API request/response shape.
- **pytest** for tests; every mapper must have tests against real sample files.
- Standard library first; add a dependency only when it clearly earns its place.

### Frontend
- **React 18 + TypeScript** (no plain JS files).
- **Vite** for build/dev.
- **Tailwind CSS** using the design tokens defined in `5-design.md`.
- **fetch** (or a tiny wrapper) for API calls — keep them all in `src/api/`.

### Conventions
- File names: `snake_case` in Python, `PascalCase.tsx` for React components.
- One transaction type per mapper file (`map_837.py`, `map_835.py`, ...).
- Output is format-agnostic: mappers return a **dict**; `json`/`xml_writer`
  serialize it. Never build XML/CSV strings inside a mapper.
- Field names double as **XML tag names**, so keep them XML-safe (snake_case).
- Output field names: `snake_case`, human-readable, stable (they are a contract).
- Keep the old working parser (`Health care EDI/edi_1500_to_json.py`) as the
  reference implementation for `map_837.py`.

---

## 3.2 What to Avoid

- ❌ **Do NOT** re-add the datainsight.health commercial engine or its Docker
  image. The whole point is to own the backend.
- ❌ **Do NOT** copy datainsight's proprietary JSON schema field-for-field
  (licensing risk). We define our own contract (`2-architecture.md`).
- ❌ **Do NOT** store PHI to disk or a database in v1. Process in memory, return,
  discard. (Persistence is a deliberate later phase with its own review.)
- ❌ **Do NOT** hard-code file paths, ports, or secrets — use `config.py` / env.
- ❌ **Do NOT** put EDI-parsing logic in `main.py`, or HTTP logic in `engine/`.
- ❌ **Do NOT** log full EDI file contents (may contain PHI). Log metadata only
  (file name, size, transaction type, issue counts).
- ❌ **Do NOT** commit real patient files. Only use the synthetic samples in
  `Input files/`.
- ❌ **Do NOT** silently swallow parse errors — surface them as structured issues.

---

## 3.3 Libraries

| Purpose | Library | License | Notes |
|---------|---------|---------|-------|
| X12 parsing | **our own `x12_reader`** | ours | Chosen over pyx12 (see `6-memory.md`); zero deps |
| X12 parsing (fallback) | pyx12 / bots / badX12 | BSD/GPL/MIT | Only if a type proves too complex |
| API framework | FastAPI | MIT | |
| Models | Pydantic v2 | MIT | |
| JSON output | stdlib `json` | — | Mapper dict → JSON |
| XML output | stdlib `xml.sax.saxutils` | — | Shared `xml_writer` over any mapper dict; no new dep |
| CSV (tabular) | stdlib `csv` / pandas | — | pandas only if needed for CSV (Phase 7) |
| Testing (BE) | pytest | MIT | |
| Frontend | React, Vite | MIT | Pure-CSS design system (no Tailwind) |

**License rule:** confirm the license of any parsing library before shipping.
Prefer permissive (MIT/BSD). If a GPL library is used server-side only, document
it here and confirm it's acceptable for the deployment model.

---

## 3.4 Error Handling

Principles:
1. **Never crash the server on a bad file.** Catch parsing failures and return a
   clean error response.
2. **Distinguish three outcomes:**
   - `ERROR` — file could not be parsed at all (return HTTP 400 + message).
   - `WARNING` — parsed, but something is off (include in `issues`, still return data).
   - `OK` — parsed cleanly.
3. **Structured issues**, not free text:
   ```json
   { "severity": "ERROR", "message": "Unknown segment XYZ",
     "segment": "XYZ", "line": 14 }
   ```
4. **HTTP status codes:**
   - `200` — success (may include warnings)
   - `400` — invalid/undetectable EDI, bad request
   - `413` — file too large (enforce a size limit in `config.py`)
   - `422` — request shape invalid (FastAPI/Pydantic default)
   - `500` — unexpected server bug (log it; return generic message, no PHI)
5. **Frontend** shows errors in `ErrorBanner.tsx` with the backend message; never
   a blank screen.

---

## 3.5 AI Assistant Boundaries

When an AI agent works on this project:

- ✅ **Always read `6-memory.md` first** to know current state before acting.
- ✅ **Update `6-memory.md`** after completing a component or phase.
- ✅ Work **one phase / one file at a time** (see `4-phases.md`). No jumping ahead.
- ✅ Write tests alongside each mapper. A mapper is not "done" without tests.
- ✅ Ask before adding a new dependency or changing the API contract.
- ❌ **Do not** edit the planning docs' intent without explicit approval — small
  status updates to `6-memory.md` are fine; rewriting requirements is not.
- ❌ **Do not** invent EDI field mappings from memory — verify against pyx12
  output and the sample files.
- ❌ **Do not** re-introduce anything from `3.2 What to Avoid`.
- ❌ **Do not** touch files/folders outside `EDI-Converter/` unless asked.
- 🔒 **PHI safety:** never paste real file contents into logs, commit messages,
  external services, or AI prompts beyond what's needed. Treat all EDI as
  sensitive by default.
