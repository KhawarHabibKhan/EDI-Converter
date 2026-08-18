"""The FHIR Bundle export used by CI conformance testing (v2 · V2-D).

`scripts/export_fhir_bundles.py` feeds the official HL7 validator in CI. These
tests keep it honest: if a fixture stops producing a Bundle, CI would otherwise
just validate fewer files and still go green.
"""

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / "scripts" / "export_fhir_bundles.py"
FIXTURE_COUNT = len([p for p in (BACKEND / "tests" / "fixtures").glob("*")
                     if p.suffix.lower() in (".edi", ".dat")])


def test_every_edi_fixture_exports_a_bundle(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True, text=True, cwd=str(BACKEND),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    bundles = sorted(tmp_path.glob("*.bundle.json"))
    assert len(bundles) == FIXTURE_COUNT, f"expected {FIXTURE_COUNT} Bundles, got {len(bundles)}"

    for path in bundles:
        bundle = json.loads(path.read_text(encoding="utf-8"))
        assert bundle["resourceType"] == "Bundle"
        assert bundle.get("entry"), f"{path.name} has no entries"
        for entry in bundle["entry"]:
            # fullUrl + resource.id are what let the validator resolve references.
            assert entry.get("fullUrl"), f"{path.name}: entry without fullUrl"
            assert entry["resource"].get("id"), f"{path.name}: resource without id"
