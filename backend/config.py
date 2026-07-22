"""Application settings for the EDI-Converter backend.

Values can be overridden with environment variables so nothing is hard-coded
(see docx/3-rules.md). Keep this module free of any web or EDI logic.
"""

from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _list_env(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    """Runtime configuration, populated from environment variables."""

    # Maximum accepted upload size (megabytes).
    MAX_FILE_MB: int = _int_env("EDI_MAX_FILE_MB", 10)

    # File extensions we accept for conversion.
    ALLOWED_EXTENSIONS: set[str] = {".edi", ".dat", ".txt", ".x12"}

    # Text encoding used to decode uploaded EDI (utf-8-sig strips a BOM).
    ENCODING: str = os.getenv("EDI_ENCODING", "utf-8-sig")

    # Origins allowed to call this API from a browser (the frontend dev server).
    CORS_ORIGINS: list[str] = _list_env(
        "EDI_CORS_ORIGINS",
        ["http://localhost:5173", "http://localhost:8091", "http://localhost"],
    )

    @property
    def max_file_bytes(self) -> int:
        return self.MAX_FILE_MB * 1024 * 1024


settings = Settings()
