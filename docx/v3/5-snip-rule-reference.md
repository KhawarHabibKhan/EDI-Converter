# v3 · 5 — SNIP Rule Reference

> **Project:** EDI-Converter — Version 3 (SNIP Level 2–5 validation)
> **Last updated:** 2026-07-23
>
> The domain reference: **representative** rules per SNIP level and transaction
> type, plus worked examples. The **authoritative** rules are the X12 **TR3
> implementation guides** (005010X222A1 for 837P, X223A2 837I, X221A1 835,
> X220A1 834, X279A1 270/271, X212 276/277); each rule is verified against its
> guide at implementation time. This doc is the working baseline, not a complete
> IG reproduction.

---

## 5.1 General approach
1. The runner parses once and detects the transaction type.
2. Level 1 (envelope) always runs.
3. For `snip_level ≥ 2`, the per-type rule set for each requested level runs
   cumulatively; issues are labeled with their level and merged.
4. Rules are **data + small predicates** (see `3-snip-rules.md` §3.4).

---

## 5.2 Level 2 — Requirement (representative, 837P)

Required loops/segments and key required elements (subset). Missing → `ERROR`
labeled `2`.

| Loop | Segment | Required elements (examples) | Note |
|------|---------|------------------------------|------|
| Header | `BHT` | BHT01 structure, BHT02 purpose, BHT06 claim/encounter | one per ST |
| 1000A | `NM1*41` (Submitter) | NM101, NM103, NM108/09 id | required |
| 1000B | `NM1*40` (Receiver) | NM101, NM103, NM108/09 id | required |
| 2000A | `HL` (Billing provider) | HL03 = 20 | required |
| 2010AA | `NM1*85` (Billing provider) | NM103, NM108=XX, NM109 (NPI) | + `N3`,`N4`; `REF*EI/SY` tax id |
| 2000B | `HL` (Subscriber) | HL03 = 22, `SBR` | required |
| 2010BA | `NM1*IL` (Subscriber) | NM103, NM108/09 member id | required |
| 2010BB | `NM1*PR` (Payer) | NM103, NM108=PI, NM109 | required |
| 2300 | `CLM` | CLM01 (acct #), CLM02 (total), CLM05 comp (POS:freq) | ≥1 per subscriber |
| 2300 | `HI` | ≥1 diagnosis (ABK principal) | required for 837P |
| 2400 | `LX` / `SV1` | SV101 (proc composite), SV102 (charge), SV104 (units) | ≥1 line per claim |
| 2400 | `DTP*472` | service date | required |

**Data-type checks (element-level):** dates `DT`=`CCYYMMDD` (8 digits); monetary
`R` (decimal, ≤2 fraction typically); `ID` values from their code list; `AN`
min/max length. **Repeat limits:** e.g. `HI` diagnosis composites ≤ 12; loop
repeat counts per the guide.

*(837I adds UB-04 loops: `CL1`, revenue `SV2`, type-of-bill in CLM05, occurrence/
value/condition `HI`. 835/834/270-271/276-277 each get their own table.)*

---

## 5.3 Level 3 — Balancing

Exact `Decimal` arithmetic. Mismatch → `ERROR` labeled `3`, naming both sides.

### 837 (claim vs service lines)
```
CLM02 (total claim charge)  ==  Σ service-line charges (SV102 / SV203)
```

### 835 (payment math)
```
per claim:   CLP03 (charge)  ==  CLP04 (paid) + CLP05 (patient resp) + Σ CAS amounts (claim + line)
per line:    SVC02 (charge)  ==  SVC03 (paid)               + Σ line CAS amounts
transaction: BPR02 (total paid)  ==  Σ CLP04 (paid)         + Σ PLB amounts (sign-aware)
```

**Worked example (illustrative):**
```
CLP*ACCT1*1*800*500*250 ...        charge 800, paid 500, patient resp 250
CAS*CO*45*250~                     contractual adj 250   (claim level)
                                   check: 500 + 250 + 250 = 1000 ≠ 800  → Level-3 ERROR
```
A balanced claim would instead satisfy `paid + patientResp + adjustments == charge`.
The rule reports: `"835 CLP: charge 800.00 ≠ paid 500.00 + patientResp 250.00 + adjustments 250.00 (= 1000.00)."`

---

## 5.4 Level 4 — Situational (representative)

`(condition present → dependent required)`. Violation → `ERROR`/`WARNING` labeled
`4`. Each rule cites its TR3 situational note in code.

| Txn | When (condition) | Then required |
|-----|------------------|---------------|
| 837P/I | COB indicated (`SBR` non-primary / multiple payers) | other-payer loops `2320`/`2330B` |
| 837P/I | Accident-related (`CLM11` accident code) | accident date `DTP*439` |
| 837I | Inpatient bill type (`CLM05-01`) | admission `DTP*435` + `CL1` |
| 837P | Referral/authorization present | `REF*9F`/`G1` value |
| 835 | `PLB` present | balanced against `BPR02` (ties to Level 3) |
| 834 | Coverage `HD` present | benefit dates `DTP*348/349` |
| 271 | Benefit `EB` active | associated service-type / coverage-level present |

---

## 5.5 Level 5 — Code sets

Membership tested against bundled sets (`validation/codesets/`). Unknown → `ERROR`
labeled `5`. See `3-snip-rules.md` §3.6 for sourcing/licensing.

| Coded element | Code system | Set file | Sourcing |
|---------------|-------------|----------|----------|
| `HI` diagnosis (ABK/ABF/…) | ICD-10-CM | `icd10cm.txt` | free |
| `HI` procedure (BBR/BBQ) 837I | ICD-10-PCS | `icd10pcs.txt` | free |
| `SV1`/`SV2` procedure (HC:) | HCPCS Level II | `hcpcs.txt` | free |
| `SV1`/`SV2` procedure (HC:) | **CPT** | — | **AMA-licensed → gated** |
| `CLM05-01` facility | Place of Service | `pos.txt` | free |
| qualifiers / status / CAS reason | X12 internal lists | bundled | free |

**CPT handling until licensing is decided:** procedure codes in the CPT range are
**format-checked only** (e.g. 5-digit numeric) and the report notes *"CPT
membership not validated (licensing pending)."* A feature flag switches on true
CPT membership once AMA licensing is approved — no code restructuring needed.

---

## 5.6 Worked example — one issue per level (broken 837P)

A single file can trip multiple levels; cumulative `snip_level=5` surfaces all:

| Level | Injected defect | Reported issue (labeled) |
|-------|-----------------|--------------------------|
| 1 | `SE01` count wrong | `L1 ERROR SE01 count … does not match` |
| 2 | 2400 `SV1` missing SV102 charge | `L2 ERROR 2400 SV1 missing required charge (SV102)` |
| 3 | `CLM02` 350.00 but lines sum 300.00 | `L3 ERROR CLM02 350.00 ≠ Σ lines 300.00` |
| 4 | accident code set, no `DTP*439` | `L4 ERROR accident indicated but accident date (DTP*439) missing` |
| 5 | diagnosis `Z9999` not in ICD-10-CM | `L5 ERROR diagnosis 'Z9999' not found in ICD-10-CM` |

A clean 837P at `snip_level=5` returns **zero errors** across all five levels —
the definition of "a payer will accept this claim" for the scope v3 targets.
