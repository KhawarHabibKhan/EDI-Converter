# 7 — Backend Plan

> **Project name:** EDI-Converter
> **Last updated:** 2026-07-21
>
> Concrete build plan for the backend. Follow `4-phases.md` for ordering and
> `3-rules.md` for conventions. This document says *exactly what to build* in
> `backend/`.

---

## 7.1 Goal

A Dockerized **FastAPI** service that accepts X12 EDI, parses it with our own
`x12_reader`, maps it to a dict via per-transaction mappers, and serializes to
**JSON / XML** (CSV + validation in later phases). This replaces the
datainsight.health engine at `:5080`.

---

## 7.2 Folder layout (target)

```
backend/
├── Dockerfile
├── requirements.txt
├── config.py                 # settings, limits, CORS
├── main.py                   # FastAPI app + routes
├── engine/
│   ├── __init__.py
│   ├── converter.py          # convert_edi(raw, type) -> dict   (entry point)
│   ├── detector.py           # detect_transaction_type(raw) -> str
│   ├── validator.py          # validate_edi(raw) -> list[Issue]
│   ├── x12_reader.py         # tokenizer: raw text -> segments (+ delimiters)
│   ├── xml_writer.py         # dict -> XML (shared serializer, all types)
│   ├── csv_writer.py         # dict -> CSV rows (Phase 7)
│   ├── models.py             # Pydantic response models
│   └── mappers/
│       ├── __init__.py
│       ├── map_837.py        # professional + institutional
│       ├── map_835.py
│       ├── map_834.py
│       ├── map_271.py
│       └── map_277.py
└── tests/
    ├── conftest.py
    ├── fixtures/             # sample EDI files copied from Input files/
    ├── test_detector.py
    ├── test_map_837.py
    ├── test_map_835.py
    ├── test_xml.py
    └── test_api.py
```

---

## 7.3 API contract (endpoints)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `GET` | `/health` | — | `{"status": "ok"}` |
| `POST` | `/edi/json` | multipart file **or** text | `{transaction_type, data, issues[]}` |
| `POST` | `/edi/xml` | multipart file **or** text | `application/xml` |
| `POST` | `/edi/csv` | multipart file **or** text | `text/csv` (Phase 7) |
| `POST` | `/edi/validate` | multipart file **or** text | `{issues: [...]}` (Phase 6) |

**Query params:** `type` = `auto` (default) `| 837P | 837I | 835 | 834 | 271 | 277`,
`pretty` = `true|false`.

### Response shape (JSON)
```json
{
  "transaction_type": "837P",
  "file_name": "claim.dat",
  "data": { "...mapped claim json..." },
  "issues": [
    { "severity": "WARNING", "message": "...", "segment": "SV1", "line": 21 }
  ]
}
```

### Error shape
```json
{ "error": "Could not detect a valid X12 transaction.", "detail": "No ISA segment found." }
```
HTTP codes per `3-rules.md` §3.4 (200 / 400 / 413 / 422 / 500).

---

## 7.4 Module responsibilities & signatures

### `config.py`
```python
class Settings:
    MAX_FILE_MB: int = 10
    ALLOWED_EXTENSIONS = {".edi", ".dat", ".txt", ".x12"}
    CORS_ORIGINS = ["http://localhost:5173"]
    ENCODING = "utf-8-sig"
```

### `main.py` (FastAPI — web only, no EDI logic)
```python
@app.get("/health")            -> {"status": "ok"}
@app.post("/edi/json")         -> _convert_or_raise(text, type) -> dict
@app.post("/edi/xml")          -> xml_writer.to_xml(_convert_or_raise(...))
@app.post("/edi/csv")          -> engine.csv_writer + converter   (Phase 7)
@app.post("/edi/validate")     -> engine.validator.validate_edi(...) (Phase 6)
# shared helpers: _read_upload(file) and _convert_or_raise(text, type)
```

### `engine/xml_writer.py`
```python
def to_xml(data: dict, root: str = "EdiDocument") -> str:
    # recursively serialize dict/list/scalars to pretty XML;
    # escapes text, sanitizes keys into valid tag names,
    # wraps list items in <item>. Shared by ALL transaction types.
```

### `engine/converter.py`
```python
def convert_edi(raw: str, transaction_type: str = "auto") -> dict:
    if transaction_type == "auto":
        transaction_type = detect_transaction_type(raw)
    tree = x12_reader.parse(raw)
    mapper = _MAPPERS[transaction_type]      # dispatch table
    return mapper.to_json(tree)
```

### `engine/detector.py`
```python
def detect_transaction_type(raw: str) -> str:
    # find ST segment: ST*837*... + GS/version to split 837P vs 837I
    # returns "837P" | "837I" | "835" | "834" | "271" | "277"
    # raises DetectionError if none found
```

### `engine/x12_reader.py`
```python
def parse(raw: str) -> SegmentTree:
    # wrap pyx12; normalize delimiters (auto-detect from ISA)
    # returns a navigable loop/segment structure
```

### `engine/mappers/map_837.py`
```python
def to_json(tree) -> dict:
    # port of edi_1500_to_json.py:
    #   CLM -> box 26/27/28, HI -> diagnoses, SV1/DTP -> service lines,
    #   NM1/N3/N4/DMG -> insured/patient/payer/providers
    # add is_institutional branch for 837I (revenue codes, DRG, occurrences)
```

Each other mapper (`map_835`, `map_834`, `map_271`, `map_277`) exposes the same
`to_json(tree) -> dict` interface.

### `engine/validator.py`
```python
def validate_edi(raw: str) -> list[Issue]:
    # structural checks (envelope balance ISA/IEA, ST/SE counts),
    # required segments per type, code-set sanity
    # returns [] when clean
```

### `engine/models.py` (Pydantic v2)
`Issue`, `ConversionResponse`, plus optional typed output models (`Claim`,
`ServiceLine`, `Payment`, `MemberCoverage`) reused from `edi_1500_to_json.py`
naming.

---

## 7.5 Build order (maps to phases)

1. **Phase 0:** `main.py` with `/health`, `Dockerfile`, `requirements.txt`.
2. **Phase 1:** `x12_reader` + `map_837` (port existing script) + `/edi/json` +
   `xml_writer` + `/edi/xml` + `test_map_837` + `test_xml`.
3. **Phase 2:** `detector` + dispatch table + tests.
4. **Phase 3–5:** `map_837i`, `map_835`, `map_834`, `map_271`, `map_277` + tests.
5. **Phase 6:** `validator` + `/edi/validate`.
6. **Phase 7:** `csv_writer` + `/edi/csv` + batch.

---

## 7.6 requirements.txt (starting point)
```
fastapi>=0.110
uvicorn[standard]>=0.29
pydantic>=2.6
python-multipart>=0.0.9     # file uploads
pytest>=8.0                 # dev/test
httpx>=0.27                 # test client
```
> No EDI/XML library needed: parsing uses our own `x12_reader`, and XML uses the
> stdlib (`xml.sax.saxutils`) via `xml_writer`.

## 7.7 Dockerfile (shape)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5080"]
```

---

## 7.8 Testing strategy
- **Unit test each mapper** against real sample files in `tests/fixtures/`
  (start with `837P-all-fields.dat` and the `271/` samples).
- **Golden-file tests:** compare mapper output to a stored expected JSON;
  update deliberately when mapping changes.
- **API tests** with `httpx` + FastAPI `TestClient`: upload → 200 + correct type.
- **Error tests:** empty file → 400; oversized → 413; garbage → structured error.
- A mapper is not "done" without tests (per `3-rules.md`).

## 7.9 Definition of done (backend)
- [ ] `docker compose up` serves `/health`.
- [ ] All 6 transaction types convert correctly with tests passing.
- [ ] Validation endpoint returns structured issues.
- [ ] No PHI written to disk or logs; in-memory only.
- [ ] CORS allows the frontend origin.
