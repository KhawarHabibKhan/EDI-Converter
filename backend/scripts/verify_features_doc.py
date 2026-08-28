"""Verify FEATURES.md against the source it claims to describe.

Counts the validation rules defined in the code, counts the rows in the rule
tables in FEATURES.md, and diffs the two. Exits non-zero on any mismatch, so it
can run in CI and stop the document drifting away from the code.

    python scripts/verify_features_doc.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
FEATURES = REPO / "FEATURES.md"
VALIDATION = BACKEND / "engine" / "validation"

# --------------------------------------------------------------------------- #
#  Side A — count what the code actually defines
# --------------------------------------------------------------------------- #
HELPERS = r"C\.(require_segment|require_qualified|require_elements|require_any|check_decimal_element|check_d8_dates)\("


def count_code() -> dict[str, int]:
    counts: dict[str, int] = {}

    # Level 1: every _issue(...) call site in validator.py, minus its definition.
    v = (BACKEND / "engine" / "validator.py").read_text(encoding="utf-8")
    counts["L1"] = len(re.findall(r"_issue\(", v)) - len(re.findall(r"def _issue\(", v))

    # Level 2: helper invocations across the per-type rule modules, plus the one
    # hand-written rule (_require_principal_diagnosis) that does not use them.
    level2 = 0
    for path in sorted((VALIDATION / "rules").glob("t*.py")):
        level2 += len(re.findall(HELPERS, path.read_text(encoding="utf-8")))
    t837p = (VALIDATION / "rules" / "t837p.py").read_text(encoding="utf-8")
    level2 += len(re.findall(r"def _require_principal_diagnosis\(", t837p))
    counts["L2"] = level2

    # Levels 3-5: each make(...) call is one distinct finding.
    for level in (3, 4, 5):
        src = (VALIDATION / f"level{level}.py").read_text(encoding="utf-8")
        counts[f"L{level}"] = len(re.findall(r"\bmake\(", src))

    return counts


# --------------------------------------------------------------------------- #
#  Side B — count the rows in the document's rule tables
# --------------------------------------------------------------------------- #
def count_doc() -> dict[str, int]:
    text = FEATURES.read_text(encoding="utf-8")
    counts = {
        # Level 1 rows are the only ones ending in a bare severity column.
        "L1": len(re.findall(r"\| (?:ERROR|WARNING) \|$", text, re.M)),
        # Level 2 rows are the only two-column rows keyed by a code identifier.
        "L2": len(re.findall(r"^\| `[^|]*\|[^|]*\|$", text, re.M)),
        # Level 3 rows state an equation; Level 4 rows have a third column.
        "L3": len(re.findall(r"^\| (?:837P / 837I|835) \| [^|]*=[^|]*\|$", text, re.M)),
        "L4": len(re.findall(r"^\| (?:837P / 837I|837I|834) \|[^|]*\|[^|]*\|$", text, re.M)),
        # Level 5 rows each carry a status.
        "L5": len(re.findall(r"Active —|Disabled by default|INFO, emitted once", text)),
    }
    return counts


def main() -> int:
    if not FEATURES.exists():
        print(f"FEATURES.md not found at {FEATURES}")
        return 1

    code, doc = count_code(), count_doc()
    levels = ["L1", "L2", "L3", "L4", "L5"]

    print(f"{'level':<8}{'code':>6}{'doc':>6}{'diff':>7}")
    print("-" * 27)
    ok = True
    for level in levels:
        delta = doc[level] - code[level]
        flag = "" if delta == 0 else "  <-- MISMATCH"
        if delta:
            ok = False
        print(f"{level:<8}{code[level]:>6}{doc[level]:>6}{delta:>+7}{flag}")
    print("-" * 27)
    print(f"{'TOTAL':<8}{sum(code.values()):>6}{sum(doc.values()):>6}"
          f"{sum(doc.values()) - sum(code.values()):>+7}")

    if not ok:
        print("\nFAIL - FEATURES.md and the code disagree.")
        print("Either a rule was added without documenting it, or a documented")
        print("row does not correspond to a rule in the source.")
        return 1
    print("\nPASS - every rule in the code has exactly one row in FEATURES.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
