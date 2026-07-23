"""SNIP validation package (v3).

Extends the envelope-only Level 1 validator up through the WEDI SNIP levels.
Levels are cumulative: running level N runs 1..N. Rules are hand-built and
data-driven — zero new runtime dependencies. The public entry point is
``runner.validate(raw, snip_level)``.

See docx/v3/ for the design, rules, and per-level rule reference.

Implemented so far: Level 1 (envelope), Level 2 (requirement).
"""

HIGHEST_LEVEL = 2
