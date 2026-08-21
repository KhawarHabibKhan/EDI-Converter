# EDI-Converter

Self-hosted web app that converts healthcare **X12 EDI** into clean **JSON**,
**XML**, and **CSV**, with structural **validation** and **batch** processing.
It replaces the commercial datainsight.health engine with our own Dockerized
backend — no license required.

Internal planning and design documents are kept out of the repository per project
policy. The user-facing documentation is in [`docs/`](docs/): the
[user manual](docs/user-guide.md), [testing plan](docs/testing-plan.md),
[deployment guide](docs/deployment-guide.md) and [case study](docs/case-study.md).

## Quick start

```bash
git clone https://github.com/KhawarHabibKhan/EDI-Converter.git
cd EDI-Converter
docker compose up --build
```

## Features

- **Transaction types:** 837P, 837I, 835, 834, 270, 271, 276, 277
- **Auto-detection** of the transaction type (or force it)
- **Output formats:** JSON, XML, CSV — plus **FHIR R4 Bundles** on the `/fhir` page
- **WEDI SNIP validation, Levels 1–5** (cumulative, selectable): envelope
  integrity, IG requirement, balancing, situational rules, and code-set
  membership (ICD-10-CM/PCS, HCPCS, POS)
- **Automatic validation** on file add — report shown automatically plus a
  validity chip; no button needed
- **Batch** conversion of multiple files into one combined download
- **Maximize** the result into a large centered overlay for easy reading
- Realistic loading animation (~2 s convert / ~2–3 s validate)
- Glassmorphism UI, light/dark theme, paste / drag-drop / upload, copy & download
- 100% self-hosted; files processed in memory, never stored

## Structure

```
EDI-Converter/
├── docs/         user manual, testing plan, deployment guide, case study
├── backend/      FastAPI + conversion engine (Python, no EDI-library deps)
├── frontend/     React + Vite (TypeScript, pure-CSS design system)
├── samples/      example inputs/outputs
└── docker-compose.yml
```

## Run with Docker (both services)

```bash
docker compose up --build
```

- Frontend: http://localhost:8091
- Backend API + docs: http://localhost:5080/docs

Both images are multi-stage and ship only what runs: the backend is a
`python:3.11-alpine` runtime holding a pruned virtualenv (the compiler toolchain,
pip, and the test framework stay in the build stage), and the frontend ships the
compiled bundle on unprivileged nginx — no Node, no `node_modules`.

| Image | Before | After |
|-------|--------|-------|
| backend | 260 MB | **127 MB** (−51%) |
| frontend | 93 MB | **81.7 MB** (−12%) |

Both containers run as a **non-root user** with a **read-only root filesystem**,
`cap_drop: ALL`, `no-new-privileges`, a tmpfs `/tmp` (Starlette spools uploads
over ~1 MB), and explicit CPU/memory limits — see `docker-compose.yml`.

> If a port is already in use, change the left-hand number in
> `docker-compose.yml` (e.g. `"9000:80"` for the frontend) and update
> `EDI_CORS_ORIGINS` to match.

## API

| Method | Path | Returns |
|--------|------|---------|
| `GET`  | `/health` | liveness JSON |
| `POST` | `/edi/json?type=auto` | `{transaction_type, file_name, data, issues}` |
| `POST` | `/edi/xml?type=auto` | `application/xml` |
| `POST` | `/edi/csv?type=auto` | `text/csv` |
| `POST` | `/edi/validate?snip_level=1..5` | `{valid, transaction_type, snip_level, error_count, warning_count, issues[]}` |
| `POST` | `/edi/fhir` | `application/fhir+json` — an R4 Bundle |
| `POST` | `/edi/fhir/validate` | combined SNIP (source) + FHIR R4 (output) report |

`type` accepts `auto` (default) or `837P · 837I · 835 · 834 · 270 · 271 · 276 · 277`.
`snip_level` defaults to the highest implemented level (5). `/edi/fhir*` also
accept this app's own `.json` / `.xml` exports, not just raw X12.

## Run locally (development)

Backend:
```bash
cd backend
pip install -r requirements-dev.txt   # runtime deps + pytest; the image installs requirements.txt only
uvicorn main:app --reload --port 5080
```

Frontend:
```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

## Test

```bash
cd backend && python -m pytest -q
```

## Status

| Version | Scope | Status |
|---------|-------|--------|
| **v1** | Phases 0–9 — 8 transaction types → JSON/XML/CSV, batch, UX | ✅ complete |
| **v2** | FHIR R4 Bundles + structural validation (V2-A…D) | ✅ complete |
| **v3** | WEDI SNIP validation Levels 1–5 | ✅ complete |

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs three jobs on every
push and PR: the backend `pytest` suite, the frontend `tsc + vite build`, and
**FHIR conformance** — the official HL7 validator run against a Bundle exported
from every fixture (`backend/scripts/export_fhir_bundles.py`). Base R4 is a hard
gate (`backend/scripts/check_fhir_conformance.py` decides the verdict, waiving
only AMA-licensed CPT membership findings); published IG profiles (US Core,
CARIN Blue Button) run advisory-only until the mappings carry their must-support
slices.

To reproduce the gate locally you need Java 17+:

```bash
cd backend && python scripts/export_fhir_bundles.py build/fhir
curl -sL -o validator_cli.jar https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar
java -jar validator_cli.jar build/fhir -version 4.0.1 -output outcome.json
python scripts/check_fhir_conformance.py outcome.json
```
