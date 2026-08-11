"""Turn the HL7 validator's OperationOutcome output into a CI pass/fail.

Why not just use the validator's exit code: it fails on **any** error, including
"Unknown code … in the CodeSystem 'http://www.ama-assn.org/go/cpt'". CPT is
AMA-licensed, so HL7 ships only a *fragment* of it — an "unknown" CPT code there
means "not in the fragment", not "invalid". Gating the build on that would make
CI depend on which CPT codes HL7 happens to bundle, and it duplicates a decision
already made in v3: CPT membership is deliberately not validated (docx/v3
decision 9, `engine/validation/level5.py` ``CPT_MEMBERSHIP``).

So: every other error fails the build; CPT membership errors are reported and
waived.

Accepts either output the CLI can produce: an ``OperationOutcome`` (or Bundle of
them) from ``-output``, or the plain-text report from ``-output-style compact``.

Usage:
    java -jar validator_cli.jar <dir> -version 4.0.1 -output outcome.json
    python scripts/check_fhir_conformance.py outcome.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

CPT_SYSTEM = "http://www.ama-assn.org/go/cpt"
FATAL = ("fatal", "error")

# Text report: "[line, col] <path>: Error - <message>", preceded by a file header.
_TEXT_ISSUE = re.compile(r"^\s*\[[^\]]*\]\s*(?P<path>.*?):\s*(?P<sev>Error|Fatal)\s*-\s*(?P<msg>.*)$")
_TEXT_FILE = re.compile(r"^\s*(?P<file>\S+\.json)\s+\d\d:\d\d:\d\d\s*$")


def _outcomes(doc: Dict[str, Any]) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Yield (source file, OperationOutcome) — the CLI emits one or a Bundle."""
    if doc.get("resourceType") == "Bundle":
        for entry in doc.get("entry") or []:
            res = entry.get("resource") or {}
            if res.get("resourceType") == "OperationOutcome":
                yield _source_of(res), res
    elif doc.get("resourceType") == "OperationOutcome":
        yield _source_of(doc), doc


def _source_of(outcome: Dict[str, Any]) -> str:
    """The validated file — the CLI tags it with the operationoutcome-file extension."""
    for ext in outcome.get("extension") or []:
        if str(ext.get("url", "")).endswith(("operationoutcome-file", "source")):
            return str(ext.get("valueString") or ext.get("valueUri") or "?").replace("\\", "/")
    return "?"


def _text(issue: Dict[str, Any]) -> str:
    return str((issue.get("details") or {}).get("text") or issue.get("diagnostics") or "")


def _location(issue: Dict[str, Any]) -> str:
    for key in ("expression", "location"):
        values = issue.get(key)
        if values:
            return str(values[0])
    return ""


def _findings(raw: str) -> Iterator[Tuple[str, str, str]]:
    """Yield (source file, location, message) for every error/fatal finding."""
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        source = "?"
        for line in raw.splitlines():
            header = _TEXT_FILE.match(line)
            if header:
                source = header.group("file")
                continue
            found = _TEXT_ISSUE.match(line)
            if found:
                yield source, found.group("path"), found.group("msg")
        return

    for source, outcome in _outcomes(doc):
        for issue in outcome.get("issue") or []:
            if issue.get("severity") in FATAL:
                yield source, _location(issue), _text(issue)


def main(path: Path) -> int:
    blocking: List[str] = []
    waived: List[str] = []

    for source, location, text in _findings(path.read_text(encoding="utf-8")):
        line = f"  {Path(source).name}  {location}\n      {text}"
        if CPT_SYSTEM in text and "Unknown code" in text:
            waived.append(line)
        else:
            blocking.append(line)

    if waived:
        print(f"WAIVED - CPT membership not validated (AMA-licensed, HL7 ships a "
              f"fragment only): {len(waived)} finding(s)")
        print("\n".join(waived))
        print()

    if blocking:
        print(f"FAIL - {len(blocking)} conformance error(s):")
        print("\n".join(blocking))
        return 1

    print("PASS - no base FHIR R4 conformance errors.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1])))
