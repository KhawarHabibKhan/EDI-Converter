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
from engine import converter, csv_writer, input_adapter, validator, xml_writer
from engine.fhir import validator as fhir_validator
from engine.fhir import writer as fhir_writer

app = FastAPI(
    title="EDI-Converter API",
    description="Convert healthcare X12 EDI (837/835/834/271/277) to JSON, CSV, "
    "and validation reports. Self-hosted; no commercial engine.",
    version="0.1.0",
)

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
    """Build the FHIR Bundle for an upload and validate its R4 structure (V2-D).

    Accepts the same inputs as ``/edi/fhir`` (``.edi/.dat/.json/.xml``). The
    report shape mirrors ``/edi/validate`` so the frontend renders it with the
    same component. Structural base-R4 checks only — IG profile certification is
    the documented V2-D CI follow-up.
    """
    file_name, text = await _read_upload(file, allowed=_FHIR_EXTENSIONS)
    try:
        data, transaction_type = input_adapter.detect_and_load(text, file_name)
        bundle = fhir_writer.to_fhir(data, transaction_type)
    except (input_adapter.InputFormatError, fhir_writer.UnsupportedFhirError,
            converter.UnsupportedTransactionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:  # noqa: BLE001 — never leak internals / PHI
        raise HTTPException(
            status_code=500, detail="Unexpected error building the FHIR Bundle."
        )

    report = fhir_validator.validate_report(bundle)
    # Adapt to the shared validation-report shape (segment/position like v1).
    issues = [
        {"severity": it["severity"], "message": it["message"], "segment": it["path"], "position": 0}
        for it in report["issues"]
    ]
    return {
        "file_name": file_name,
        "valid": report["valid"],
        "error_count": report["error_count"],
        "warning_count": report["warning_count"],
        "issue_count": report["issue_count"],
        "issues": issues,
    }


@app.post("/edi/validate", tags=["validation"])
async def edi_validate(file: UploadFile = File(...)) -> dict:
    """Validate the X12 envelope structure and return a list of issues."""
    file_name, text = await _read_upload(file)
    issues = validator.validate_edi(text)
    errors = sum(1 for i in issues if i["severity"] == "ERROR")
    warnings = sum(1 for i in issues if i["severity"] == "WARNING")
    return {
        "file_name": file_name,
        "valid": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "issue_count": len(issues),
        "issues": issues,
    }
