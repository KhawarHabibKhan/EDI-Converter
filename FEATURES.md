# EDI-Converter — What It Does

## 1. What this project is

Health insurers and clinics exchange claims, payments and eligibility checks as
**X12 EDI** files — a 1970s text format that is machine-readable and unreadable to
people. This project does two things with those files: it **converts** them into
formats people and modern software can use (JSON, XML, CSV, and FHIR), and it
**checks** them against the industry's five standard levels of validation before
they are sent to a payer. It runs entirely on your own servers, with no
commercial licence and no third-party EDI library.

**The thing most people get wrong: this is a validator that happens to convert,
not a converter that happens to validate.** Converting a claim is the easy half —
the parser is deliberately forgiving and will happily read a broken file. The
value is in the 92 rules that tell you *why a payer will reject it*, weeks before
the payer does.

---

## 2. How one file travels through the system

```
   upload (.edi / .dat / .txt / .x12)
        │
        ▼
   main.py ─────────── size, extension and encoding checks
        │
        ▼
   x12_reader.py ───── split into segments; read delimiters from the ISA header
        │
        ├─────────────────────────────┐
        ▼                             ▼
   detector.py                  validation/runner.py
   "which of the 8              │
    types is this?"             ├── level1  envelope integrity      (always)
        │                       ├── level2  required segments       (if level ≥ 2)
        ▼                       ├── level3  the money adds up       (if level ≥ 3)
   mappers/map_*.py             ├── level4  conditional rules       (if level ≥ 4)
   X12 → plain dictionary       └── level5  codes are real          (if level ≥ 5)
        │                             │
        ├──────────────┐              ▼
        ▼              ▼        deduplicate, sort by position
   xml_writer     csv_writer          │
   json           fhir/writer.py      ▼
        │              │        issue list  {severity, level, message, segment, position}
        ▼              ▼
     response      FHIR R4 Bundle
```

| Stage | Module | What happens | Fails how |
|---|---|---|---|
| Intake | [main.py](backend/main.py) | Checks file size, extension, text encoding | `400` or `413`, never a crash |
| Tokenize | [x12_reader.py](backend/engine/x12_reader.py) | Splits into segments; reads the delimiters out of the ISA header | `400` if no segments found |
| Detect | [detector.py](backend/engine/detector.py) | Reads the ST segment to identify the transaction type | Falls back to the type you selected |
| Map | [mappers/](backend/engine/mappers/) | One mapper per type turns segments into a plain dictionary | Lenient by design — missing data becomes empty, not an error |
| Validate | [validation/runner.py](backend/engine/validation/runner.py) | Runs levels 1..N, merges and de-duplicates the findings | Always returns a report, never throws |
| Serialize | [xml_writer.py](backend/engine/xml_writer.py) · [csv_writer.py](backend/engine/csv_writer.py) · [fhir/writer.py](backend/engine/fhir/writer.py) | Renders the dictionary in the requested format | `400` if the type has no mapper |

**The important consequence of that "lenient by design" row:** conversion
succeeding tells you nothing about whether the file is correct. The two paths are
independent on purpose, which is why the UI validates every file automatically the
moment you add it.

---

## 3. Core concepts

### The five SNIP levels

WEDI SNIP is the healthcare industry's shared vocabulary for *how deeply a file
was checked*. Levels are **cumulative** — asking for level 5 also runs 1 to 4.

| Level | Name | The question it answers |
|---|---|---|
| **1** | Integrity | Is the envelope intact? Do the counts and control numbers match? |
| **2** | Requirement | Are the segments and fields this transaction type requires present? |
| **3** | Balancing | Does the money add up? |
| **4** | Situational | Given what this file says, is something else now required? |
| **5** | Code sets | Are the medical codes real codes? |

Levels 6 and 7 (payer-specific rules) are out of scope and not implemented.

### Severities

| Severity | Meaning | Effect on `valid` |
|---|---|---|
| `ERROR` | The file is wrong and will likely be rejected | Sets `valid: false` |
| `WARNING` | Suspicious, but not fatal | File is still `valid` |
| `INFO` | A note about the check itself, not the file | File is still `valid` |

### The eight transaction types

| Code | Plain English | Paper equivalent |
|---|---|---|
| **837P** | A doctor's or clinic's claim | CMS-1500 |
| **837I** | A hospital's claim | UB-04 |
| **835** | Payment / remittance advice | — |
| **834** | Enrolling members in a plan | — |
| **270** | "Is this patient covered?" | — |
| **271** | The answer to 270 | — |
| **276** | "What is happening with my claim?" | — |
| **277** | The answer to 276 | — |

---

## 4. Feature list

### Conversion

- **Reads all eight transaction types** listed above, each with its own mapper in
  [mappers/](backend/engine/mappers/).
- **Detects the type for you** by reading the ST segment
  ([detector.py](backend/engine/detector.py)). 837P and 837I look nearly identical,
  so it also reads the implementation-guide version to tell them apart.
- **Four output formats:** JSON, XML, CSV and FHIR R4. XML and CSV are generated
  from the same dictionary as JSON, so all formats always agree with each other.
- **CSV flattens to one row per detail line** — service line, payment or benefit —
  which is the shape people actually want in Excel.
- **Reads its own output back in.** The FHIR converter accepts this app's JSON and
  XML exports as input, not just raw EDI ([input_adapter.py](backend/engine/input_adapter.py)).
- **Delimiters come from the file, not from assumption.** Different senders use
  different separators; they are read from fixed positions in the ISA header.
- **Version-aware parsing.** Before X12 4030, the ISA11 byte is not a delimiter at
  all but the letter `U`. Treating it as one splits real data — service-type codes
  like `UC` become `["", "C"]`. Guarded in [x12_reader.py](backend/engine/x12_reader.py).

### Validation

- **Five cumulative SNIP levels, selectable per request** via `?snip_level=1..5`,
  defaulting to the strictest.
- **Every issue is labelled** with the level that raised it, the segment, and its
  position in the file.
- **Messages name both sides of a failure.** A balancing error reads
  "CLM02 claim total 150.00 does not equal the sum of service-line charges 100.00" —
  not "validation failed".
- **Exact decimal arithmetic.** Money is compared with `Decimal`, never floating
  point, so 0.1 + 0.2 problems cannot produce phantom imbalances
  ([level3.py](backend/engine/validation/level3.py)).
- **Findings are de-duplicated and sorted** by position, so the report reads in
  file order ([runner.py](backend/engine/validation/runner.py)).
- **A broken file never crashes the validator.** If the file cannot even be
  tokenized, that fact is returned as a level-1 issue.

### FHIR

- **All eight types map to FHIR R4** resources: `Claim`, `ExplanationOfBenefit`,
  `Coverage`, `CoverageEligibilityRequest`/`Response`, `Task`, each bundled with
  the `Patient` and `Organization` records it refers to.
- **Validates the source and the output.** `/edi/fhir/validate` runs the SNIP
  rules on the input *and* a structural check on the generated Bundle — because a
  lenient mapper turns a broken claim into a structurally valid Bundle, so checking
  only the output would call that a pass.
- **Independently verified in CI** against HL7's official validator, not just our
  own ([ci.yml](.github/workflows/ci.yml)).

### Privacy and safety

- **Nothing is stored.** Files are parsed in memory and discarded. No database, no
  upload folder, no retention policy.
- **Errors never quote your file back.** Unexpected failures return a generic
  message; the detail goes to the log, not the response.
- **Logs record traffic shape only** — method, path, status, duration, size — never
  body content or filenames, both of which carry patient data
  ([logging_config.py](backend/logging_config.py)).
- **No authentication exists.** Anyone who can reach the URL can convert files.
  Fine behind a VPN; not fine on the public internet with real patient data.

### Operations

- **Runs with one command** (`docker compose up`). Both containers run as a
  non-root user with a read-only filesystem.
- **A deployment is verified, not assumed** — [smoke_test.py](deploy/smoke_test.py)
  runs 17 checks against a live URL and exits non-zero on failure.
- **Measured, not estimated performance:** ~152 validations/second on one CPU core.

---

## 5. The enumerable core — all 92 validation rules

This is the product surface. Every row is a distinct check that can appear in a
report. Counts were extracted with ripgrep against the source, not transcribed.

### Level 1 — Integrity · 15 rules · runs on every file regardless of type

Source: [validator.py](backend/engine/validator.py)

| Fires on | What it checks | Severity |
|---|---|---|
| *(whole file)* | File contains no X12 segments at all | ERROR |
| `ISA` | Interchange header is missing | WARNING |
| `ISA` | File does not begin with ISA | WARNING |
| `IEA` | Interchange trailer is missing | ERROR |
| `IEA` | IEA02 control number does not match ISA13 | ERROR |
| `GE` | A group trailer appears with no matching GS | ERROR |
| `GE` | GE01 declares a different number of transactions than exist | ERROR |
| `GE` | GE02 control number does not match GS06 | ERROR |
| `ST` | Transaction type is not a recognised healthcare type | WARNING |
| `SE` | A transaction trailer appears with no matching ST | ERROR |
| `SE` | SE01 segment count does not match the real count | ERROR |
| `SE` | SE02 control number does not match ST02 | ERROR |
| `GS` | A group was opened and never closed | ERROR |
| `ST` | A transaction was opened and never closed | ERROR |
| `IEA` | IEA01 declares a different number of groups than exist | ERROR |

### Level 2 — Requirement · 62 rules

Every rule below is an ERROR. Source: [rules/](backend/engine/validation/rules/)

**Shared by 837P and 837I — 17 rules** · [t837p.py](backend/engine/validation/rules/t837p.py)

| Fires on | What must be present |
|---|---|
| `ST03` | The transaction names which implementation guide it follows |
| `BHT` | Beginning-of-transaction segment exists |
| `BHT01/02/06` | Structure code, purpose code and claim indicator are filled in |
| `NM1*41` | The submitter is named |
| `NM1*40` | The receiver is named |
| `HL*20` | A billing-provider level exists in the hierarchy |
| `NM1*85` | Billing provider has a name, an ID qualifier and an NPI |
| `HL*22/23` | A subscriber or patient level exists |
| `SBR` | Subscriber information segment exists |
| `NM1*IL` | Subscriber has a name and a member ID |
| `NM1*PR` | Payer has a name and an identifier |
| `CLM` | A claim segment exists |
| `CLM01/02` | Claim has a patient account number and a total charge |
| `CLM02` | The total charge is a valid decimal number |
| `HI` | A diagnosis segment exists, and one diagnosis is flagged principal (ABK/BK) |
| `DTP*472` | A service date is present |
| `DTP` | Dates flagged D8 are valid CCYYMMDD |

**837P only — 3 rules** · [t837p.py](backend/engine/validation/rules/t837p.py)

| Fires on | What must be present |
|---|---|
| `SV1` | At least one professional service line exists |
| `SV1-01/02` | Every line has a procedure code and a charge |
| `SV1-02` | Every line charge is a valid decimal number |

**837I only — 3 rules** · [t837i.py](backend/engine/validation/rules/t837i.py)

| Fires on | What must be present |
|---|---|
| `SV2` | At least one institutional service line exists |
| `SV2-01/03` | Every line has a revenue code and a charge |
| `SV2-03` | Every line charge is a valid decimal number |

**835 payments — 13 rules** · [t835.py](backend/engine/validation/rules/t835.py)

| Fires on | What must be present |
|---|---|
| `BPR` | Financial information segment exists |
| `BPR01/02` | Payment states a handling code and an amount |
| `BPR02` | The total payment is a valid decimal number |
| `TRN` | Reassociation trace segment exists |
| `TRN02` | The trace number is filled in |
| `N1*PR` | The payer is named |
| `N1*PE` | The payee is named |
| `CLP` | At least one claim payment exists |
| `CLP01-04` | Payment has a control number, status, charge and paid amount |
| `CLP03` | The claim charge is a valid decimal number |
| `CLP04` | The claim payment is a valid decimal number |
| `SVC01/02` | Every service payment has a procedure code and a charge |
| `SVC02` | Every service charge is a valid decimal number |

**834 enrolment — 9 rules** · [t834.py](backend/engine/validation/rules/t834.py)

| Fires on | What must be present |
|---|---|
| `BGN` | Beginning segment exists |
| `BGN01/02` | Transaction purpose and reference number are filled in |
| `N1*P5` | The plan sponsor is named |
| `N1*IN` | The insurer is named |
| `INS` | Member-level detail segment exists |
| `INS01/03` | Member has a subscriber indicator and a maintenance code |
| `NM1*IL` | The member is named |
| `HD` | Health coverage segment exists |
| `HD01/03` | Every coverage has a maintenance type and an insurance line |

**270 / 271 eligibility — 9 rules** · [t270_271.py](backend/engine/validation/rules/t270_271.py)

| Fires on | What must be present |
|---|---|
| `BHT` | Beginning-of-transaction segment exists |
| `BHT01/02` | Hierarchical structure and purpose codes are filled in |
| `HL*20` | An information-source level exists |
| `HL*21` | An information-receiver level exists |
| `HL*22` | A subscriber level exists |
| `NM1*PR` | The payer / information source is named |
| `NM1*IL` | The subscriber is named |
| `EQ` | A 270 inquiry actually asks about something |
| `EB` | A 271 response actually carries benefit information |

**276 / 277 claim status — 8 rules** · [t276_277.py](backend/engine/validation/rules/t276_277.py)

| Fires on | What must be present |
|---|---|
| `BHT` | Beginning-of-transaction segment exists |
| `BHT01/02` | Hierarchical structure and purpose codes are filled in |
| `HL*20` | An information-source level exists |
| `HL*21` | An information-receiver level exists |
| `NM1*PR` | The payer is named |
| `TRN` | Claim status trace segment exists |
| `TRN02` | Every trace carries a trace number |
| `STC` | A 277 response actually carries claim status information |

### Level 3 — Balancing · 5 rules · exact decimal arithmetic

Source: [level3.py](backend/engine/validation/level3.py)

| Applies to | The equation that must hold |
|---|---|
| 837P / 837I | Claim total `CLM02` = sum of all service-line charges |
| 835 | Line charge `SVC02` = line paid `SVC03` + that line's adjustments |
| 835 | Claim charge `CLP03` = sum of its service-line charges |
| 835 | Claim payment `CLP04` = sum of its service-line payments |
| 835 | Total payment `BPR02` = sum of claim payments − provider adjustments |

### Level 4 — Situational · 4 rules · "if this, then that is required"

Source: [level4.py](backend/engine/validation/level4.py)

| Applies to | If this is true… | …then this is required |
|---|---|---|
| 837P / 837I | The claim is accident-related (`CLM11`) | An accident date `DTP*439` |
| 837I | An admission segment `CL1` is present | An admission date `DTP*435` |
| 837P / 837I | `SBR01` says this payer is not primary | An other-payer loop naming the primary |
| 834 | A health coverage `HD` is present | A coverage begin date `DTP*348` |

### Level 5 — Code sets · 6 rules

Source: [level5.py](backend/engine/validation/level5.py) · code lists in [codesets/](backend/engine/validation/codesets/)

| Fires on | What it checks | Status |
|---|---|---|
| `HI` | Diagnosis codes exist in ICD-10-CM | Active — **seed subset**, not the full CMS list |
| `HI` | Inpatient procedure codes exist in ICD-10-PCS (837I) | Active — **seed subset** |
| `SV1` / `SV2` | HCPCS Level II codes exist in HCPCS | Active — **seed subset** |
| `CLM05-01` | Place-of-service code is a real one (837P) | Active — complete official set |
| `SV1` / `SV2` | CPT codes exist in CPT | **Disabled by default.** CPT is AMA-licensed and not bundled |
| `SV1` | Note recording that CPT was format-checked only | INFO, emitted once per file |

> **Honest gap:** the ICD-10-CM, ICD-10-PCS and HCPCS lists are small seed subsets
> containing the codes used by the test files plus common ones. Real production
> claims will contain valid codes these lists do not know, and Level 5 will flag
> them. Swapping in the full CMS lists is a data change, not a code change — see
> [codesets/README.md](backend/engine/validation/codesets/README.md).

---

## 6. The pattern

If you read one section, read this one. All 92 rules have the same shape.

| Every rule… | Which is why… |
|---|---|
| belongs to exactly one of 5 levels | you can dial strictness up or down with one number |
| applies to specific transaction types | an 835 is never judged by 837 rules |
| names the segment it fires on | the report points at a place in the file |
| produces one issue, never an exception | a broken file still gets a full report |
| carries `{severity, level, message, segment, position}` | every report is the same shape, whatever failed |

The runner then merges the levels, removes duplicates, and sorts by position in
the file. **Nothing else in the system decides whether a file is acceptable** —
`valid` is simply "no ERROR issues". One rule, one row, one place to add the next.

Adding a rule means writing one function that returns issues and registering it in
its level module. No schema change, no configuration, no restart logic.

---

## 7. The one thing to demonstrate

Show the same claim twice.

**Case A — a file that is perfectly formed and completely wrong.**
Take a valid 837P and change one service line's charge from `150.00` to `100.00`,
leaving the claim total at `150.00`. Every envelope count still matches. Every
required segment is present. Levels 1 and 2 pass clean. Level 3 reports:

> `CLM02 claim total 150.00 does not equal the sum of service-line charges 100.00`

That is a claim a payer rejects and a structural checker approves. It is the whole
argument for the product in one line.

**Case B — a file that is malformed but harmless.**
Take the same claim and change `SE*23` to `SE*99`. The data is untouched and the
claim is financially perfect, but the envelope now lies about its own size. Level 1
reports a segment-count mismatch and the file is rejected before anyone looks at
the money.

Two files, two opposite failures, one report format. Then set `?snip_level=1` on
the first file and watch it pass — which shows what the levels are actually for.

---

*Counts in this document were extracted from the source with ripgrep on
2026-08-21: 15 Level-1 checks, 62 Level-2 rules, 5 Level-3, 4 Level-4, 6 Level-5.
Total 92. The API exposes 8 endpoints.*
