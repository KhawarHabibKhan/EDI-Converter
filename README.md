# EDI-Converter

Self-hosted web app that converts healthcare **X12 EDI** into clean **JSON**,
**XML**, and **CSV**, with structural **validation** and **batch** processing.
It replaces the commercial datainsight.health engine with our own Dockerized
backend — no license required.

Full planning lives in [`docx/`](docx/): requirements, architecture, rules,
phases, design, the two implementation plans, and the living progress log
(`6-memory.md`).

## Features

- **Transaction types:** 837P, 837I, 835, 834, 270, 271, 276, 277
- **Auto-detection** of the transaction type (or force it)
- **Output formats:** JSON, XML, CSV
- **Automatic structural validation** on file add (ISA/IEA, GS/GE, ST/SE
  pairing, control numbers, segment counts) — report shown automatically plus a
  validity chip; no button needed
- **Batch** conversion of multiple files into one combined download
- **Maximize** the result into a large centered overlay for easy reading
- Realistic loading animation (~2 s convert / ~2–3 s validate)
- Glassmorphism UI, light/dark theme, paste / drag-drop / upload, copy & download
- 100% self-hosted; files processed in memory, never stored

## Structure

```
EDI-Converter/
├── docx/         planning documents (read 6-memory.md first)
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
| `POST` | `/edi/validate` | `{valid, error_count, warning_count, issues[]}` |

`type` accepts `auto` (default) or `837P · 837I · 835 · 834 · 270 · 271 · 276 · 277`.

## Run locally (development)

Backend:
```bash
cd backend
pip install -r requirements.txt
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

**All phases (0–8) complete.** All 8 transaction types convert to JSON/XML/CSV,
with validation and batch. See [`docx/6-memory.md`](docx/6-memory.md).
