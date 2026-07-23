"""Bundled code-set membership tables for SNIP Level 5.

Free code sets only — ICD-10-CM, ICD-10-PCS, HCPCS Level II, and Place of
Service. CPT is AMA-licensed and deliberately excluded (see
``docx/v3/3-snip-rules.md`` §3.6 and ``README.md`` here).

Each ``<set>.txt`` is one code per line: blank lines and ``#`` comments are
ignored, and only the first whitespace-separated token on a line is read, so
``CODE  human description`` is fine. Sets are loaded lazily once per process and
cached. Membership is exact after normalization (upper-case, dots and spaces
stripped) — X12 sends ICD codes without the decimal point (``E119`` not
``E11.9``), and normalization makes either form match.

Refreshing a set = replace its ``.txt`` file with an updated official list. That
is a **data** change, not a code change; the loader picks up whatever is bundled.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, FrozenSet

_DIR = os.path.dirname(__file__)
_FILES = {
    "icd10cm": "icd10cm.txt",
    "icd10pcs": "icd10pcs.txt",
    "hcpcs": "hcpcs.txt",
    "pos": "pos.txt",
}


def _normalize(code: str) -> str:
    return (code or "").strip().upper().replace(".", "").replace(" ", "")


@lru_cache(maxsize=None)
def _load(set_name: str) -> FrozenSet[str]:
    fname = _FILES.get(set_name)
    codes = set()
    if fname:
        path = os.path.join(_DIR, fname)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    codes.add(_normalize(line.split()[0]))
    return frozenset(codes)


def contains(set_name: str, code: str) -> bool:
    """True if ``code`` is a member of the named set. Unknown set / empty → False."""
    if not code:
        return False
    return _normalize(code) in _load(set_name)


def available(set_name: str) -> bool:
    """True if the named set is bundled and non-empty."""
    return len(_load(set_name)) > 0


def counts() -> Dict[str, int]:
    """Loaded code count per set — for diagnostics and tests."""
    return {name: len(_load(name)) for name in _FILES}
