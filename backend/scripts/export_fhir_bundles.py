"""Export a FHIR Bundle for every test fixture — input for IG certification.

The runtime validator (``engine/fhir/validator.py``) is a zero-dependency
base-R4 structural check. Real **IG conformance** (US Core / CARIN Blue Button)
is proven separately by the official HL7 validator, which needs Java and the
published IG packages — so it runs in CI, not at runtime (docx/v2 decision 4).

This script is the bridge: it turns each fixture into a Bundle on disk so the
HL7 validator has something to chew on.

Usage:
    python scripts/export_fhir_bundles.py [out_dir]      # default: build/fhir
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from engine import input_adapter  # noqa: E402
from engine.fhir import writer as fhir_writer  # noqa: E402

FIXTURES = BACKEND / "tests" / "fixtures"


def main(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    written, failed = 0, 0

    for src in sorted(FIXTURES.glob("*")):
        if src.suffix.lower() not in (".edi", ".dat"):
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        try:
            data, ttype = input_adapter.detect_and_load(text, src.name)
            bundle = fhir_writer.to_fhir(data, ttype)
        except Exception as exc:  # noqa: BLE001 — surface, don't hide
            print(f"  SKIP {src.name}: {exc}")
            failed += 1
            continue
        target = out_dir / f"{src.stem}.bundle.json"
        target.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        kinds = sorted({e["resource"]["resourceType"] for e in bundle.get("entry", [])})
        print(f"  {target.name}  [{ttype}]  {', '.join(kinds)}")
        written += 1

    print(f"\n{written} Bundle(s) written to {out_dir}" + (f", {failed} skipped" if failed else ""))
    return 0 if written and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else BACKEND / "build" / "fhir")))
