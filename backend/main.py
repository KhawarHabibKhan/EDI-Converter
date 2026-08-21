"""EDI-Converter backend — FastAPI application.

This module is the "waiter": it handles HTTP concerns only (routing, uploads,
status codes, CORS) and delegates all EDI logic to the ``engine`` package.

Phase 0: health check + skeleton.
Phase 1: POST /edi/json for 837P conversion.
Later phases add auto-detect, CSV, and validation (see docx/4-phases.md).
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from engine import converter, csv_writer, input_adapter, xml_writer
from engine.fhir import validator as fhir_validator
from engine.fhir import writer as fhir_writer
from engine.validation import runner as snip_runner
from logging_config import configure_logging, log_requests

log = configure_logging()

app = FastAPI(
    title="EDI-Converter API",
    description="Convert healthcare X12 EDI (837/835/834/271/277) to JSON, CSV, "
    "and validation reports. Self-hosted; no commercial engine.",
    version="0.1.0",
)

# Request logging. Deliberately records only traffic shape — never body content,
# parsed output, or filenames, all of which can carry PHI. See logging_config.py.
app.middleware("http")(log_requests)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
#  System endpoints
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness check used by Docker, the frontend, and monitoring."""
    return {"status": "ok", "service": "edi-converter", "version": app.version}


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    """Friendly root pointing at the interactive API docs."""
    return {"message": "EDI-Converter API. See /docs for the interactive API."}


# --------------------------------------------------------------------------- #
#  Conversion endpoints
# --------------------------------------------------------------------------- #
async def _read_upload(
    file: UploadFile, allowed: Optional[set[str]] = None
) -> tuple[str, str]:
    """Validate and decode an uploaded EDI file.

    Returns (file_name, decoded_text). Raises HTTPException on any problem.
    ``allowed`` overrides the accepted extension set (the FHIR endpoint widens
    it to include ``.json`` / ``.xml``).
    """
    allowed = allowed or settings.ALLOWED_EXTENSIONS
    name = file.filename or "upload.edi"
    ext = os.path.splitext(name)[1].lower()
    if ext and ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: "
            f"{', '.join(sorted(allowed))}.",
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw_bytes) > settings.max_file_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.MAX_FILE_MB} MB limit.",
        )

    try:
        text = raw_bytes.decode(settings.ENCODING)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid text/EDI.")
    return name, text


def _convert_or_raise(text: str, type: str) -> dict:
    """Run the converter, translating engine errors into HTTP errors."""
    try:
        return converter.convert_edi(text, type)
    except converter.UnsupportedTransactionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:  # noqa: BLE001 — never leak internals / PHI
        # Log the traceback so the failure is diagnosable; the response stays
        # generic. Only the requested type is recorded, never file content.
        log.exception("conversion failed", extra={"context": {"type": type}})
        raise HTTPException(
            status_code=500, detail="Unexpected error converting the EDI file."
        )


@app.post("/edi/json", tags=["conversion"])
async def edi_to_json(
    file: UploadFile = File(...),
    type: str = Query("auto", description="Transaction type, or \"auto\" to detect."),
) -> dict:
    """Convert an uploaded EDI file to JSON.

    Response shape:
        { transaction_type, file_name, data, issues }
    """
    file_name, text = await _read_upload(file)
    data = _convert_or_raise(text, type)
    return {
        "transaction_type": data.get("source_transaction", type),
        "file_name": file_name,
        "data": data,
        "issues": [],  # populated once the validator lands (Phase 6)
    }


@app.post("/edi/xml", tags=["conversion"])
async def edi_to_xml(
    file: UploadFile = File(...),
    type: str = Query("auto", description="Transaction type, or \"auto\" to detect."),
) -> Response:
    """Convert an uploaded EDI file to XML.

    Uses the same mapper output as ``/edi/json`` and serializes it with the
    shared ``engine.xml_writer`` so every transaction type gets XML uniformly.
    """
    _, text = await _read_upload(file)
    data = _convert_or_raise(text, type)
    xml = xml_writer.to_xml(data)
    return Response(content=xml, media_type="application/xml")


@app.post("/edi/csv", tags=["conversion"])
async def edi_to_csv(
    file: UploadFile = File(...),
    type: str = Query("auto", description="Transaction type, or \"auto\" to detect."),
) -> Response:
    """Convert an uploaded EDI file to CSV (tabular, one row per detail line)."""
    _, text = await _read_upload(file)
    data = _convert_or_raise(text, type)
    csv_text = csv_writer.to_csv(data)
    return Response(content=csv_text, media_type="text/csv")


# FHIR endpoint accepts our JSON/XML exports in addition to raw EDI.
_FHIR_EXTENSIONS = settings.ALLOWED_EXTENSIONS | {".json", ".xml"}


@app.post("/edi/fhir", tags=["fhir"])
async def edi_to_fhir(file: UploadFile = File(...)) -> Response:
    """Convert EDI / our JSON / our XML to a FHIR R4 Bundle (v2).

    Accepts ``.edi/.dat`` (raw X12) or an EDI-Converter ``.json`` / ``.xml``
    export. The input adapter normalizes any of these to the v1 dict, then the
    FHIR writer emits a Bundle (``type: collection``) centered on the primary
    resource (837 → ``Claim`` in V2-A). Returns ``application/fhir+json``.
    """
    file_name, text = await _read_upload(file, allowed=_FHIR_EXTENSIONS)
    try:
        data, transaction_type = input_adapter.detect_and_load(text, file_name)
        bundle = fhir_writer.to_fhir(data, transaction_type)
    except (input_adapter.InputFormatError, fhir_writer.UnsupportedFhirError,
            converter.UnsupportedTransactionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:  # noqa: BLE001 — never leak internals / PHI
        log.exception("FHIR bundle build failed")
        raise HTTPException(
            status_code=500, detail="Unexpected error building the FHIR Bundle."
        )

    import json as _json

    return Response(
        content=_json.dumps(bundle, indent=2),
        media_type="application/fhir+json",
    )


@app.post("/edi/fhir/validate", tags=["fhir"])
async def edi_fhir_validate(file: UploadFile = File(...)) -> dict:
    """Validate an upload for the FHIR pipeline — **source + output**.

    Two complementary checks, combined into one report so the FHIR page matches
    the Converter page:
      1. **Source (SNIP):** when the input is raw X12 EDI, run the same SNIP
         validation the Converter page runs (levelled issues). This is what
         catches source problems (missing segments, bad amounts) — a lenient
         mapper can still turn a broken 837 into a structurally-valid Bundle,
         so the Bundle check alone would miss them.
      2. **Output (FHIR R4):** build the Bundle and validate its base-R4
         structure (`stage: "fhir"`).

    Accepts ``.edi/.dat/.json/.xml`` (JSON/XML exports skip SNIP — it only
    applies to raw X12). Report shape mirrors ``/edi/validate``.
    """
    file_name, text = await _read_upload(file, allowed=_FHIR_EXTENSIONS)

    issues: list[dict] = []
    transaction_type = None
    snip_level = None

    # 1) SNIP validation of the raw X12 source (identical to the Converter page).
    try:
        fmt = input_adapter.detect_format(text, file_name)
    except input_adapter.InputFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if fmt == "edi":
        snip = snip_runner.validate(text)
        transaction_type = snip["transaction_type"]
        snip_level = snip["snip_level"]
        for it in snip["issues"]:
            issues.append({
                "severity": it["severity"], "message": it["message"],
                "segment": it["segment"], "position": it["position"],
                "level": it["level"], "stage": "snip",
            })

    # 2) Build the Bundle and validate its FHIR R4 structure.
    try:
        data, ttype = input_adapter.detect_and_load(text, file_name)
        transaction_type = transaction_type or ttype
        bundle = fhir_writer.to_fhir(data, ttype)
    except (input_adapter.InputFormatError, fhir_writer.UnsupportedFhirError,
            converter.UnsupportedTransactionError, ValueError) as exc:
        if fmt != "edi":
            # No SNIP context and the Bundle can't be built → nothing to report.
            raise HTTPException(status_code=400, detail=str(exc))
        # EDI that can't convert: keep the SNIP findings, note the build failure.
        issues.append({
            "severity": "ERROR", "message": f"Could not build a FHIR Bundle from this input: {exc}",
            "segment": "", "position": 0, "stage": "fhir",
        })
    except Exception:  # noqa: BLE001 — never leak internals / PHI
        log.exception("FHIR validation failed")
        raise HTTPException(status_code=500, detail="Unexpected error building the FHIR Bundle.")
    else:
        report = fhir_validator.validate_report(bundle)
        for it in report["issues"]:
            issues.append({
                "severity": it["severity"], "message": it["message"],
                "segment": it["path"], "position": 0, "stage": "fhir",
            })

    errors = sum(1 for i in issues if i["severity"] == "ERROR")
    warnings = sum(1 for i in issues if i["severity"] == "WARNING")
    return {
        "file_name": file_name,
        "transaction_type": transaction_type,
        "snip_level": snip_level,
        "valid": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "issue_count": len(issues),
        "issues": issues,
    }


@app.post("/edi/validate", tags=["validation"])
async def edi_validate(
    file: UploadFile = File(...),
    snip_level: Optional[int] = Query(
        None,
        ge=1,
        le=snip_runner.HIGHEST_LEVEL,
        description="WEDI SNIP level (cumulative). Defaults to the highest implemented.",
    ),
) -> dict:
    """Validate an X12 file through the WEDI SNIP levels and return the issues.

    Levels are cumulative (a level-N request also reports levels 1..N-1). Level 1
    is envelope integrity; Level 2 adds transaction-type requirement checks. Each
    issue is labeled with its ``level``. The report also names the detected
    ``transaction_type`` and the applied ``snip_level``.
    """
    file_name, text = await _read_upload(file)
    result = snip_runner.validate(text, snip_level)
    issues = result["issues"]
    errors = sum(1 for i in issues if i["severity"] == "ERROR")
    warnings = sum(1 for i in issues if i["severity"] == "WARNING")
    return {
        "file_name": file_name,
        "transaction_type": result["transaction_type"],
        "snip_level": result["snip_level"],
        "valid": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "issue_count": len(issues),
        "issues": issues,
    }
