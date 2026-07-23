# v2 · 5 — FHIR Mapping Reference

> **Project:** EDI-Converter — Version 2 (FHIR R4)
> **Last updated:** 2026-07-23
>
> The domain reference: how each transaction's **normalized dict** (v1 output) maps
> to FHIR resources. FHIR paths follow **FHIR R4 base**; exact profile slices are
> confirmed against the published IGs at implementation time.

---

## 5.1 General approach

1. Input becomes the v1 **normalized dict** (via the input adapter).
2. Build **supporting resources** first (Patient, Coverage, Organization) so the
   primary resource can reference them.
3. Build the **primary resource** (Claim / EOB / …), mapping fields, tagging codes
   with their `system` URI, and pointing references at step 2.
4. Wrap all resources in a **Bundle** (`type: collection`).

Three FHIR ideas do the heavy lifting:
- **CodeableConcept** — a code plus the `system` it came from.
- **Reference** — a link between resources (`"Patient/patient-1"`).
- **Bundle** — the folder holding the primary + referenced resources.

## 5.2 Code-system URIs
See `3-fhir-rules.md` §3.5 for the canonical table (ICD-10-CM, ICD-10-PCS,
CPT/HCPCS, NPI, claim-type, adjudication, gender).

---

## 5.3 837P / 837I → `Claim`   *(V2-A)*

**Bundle entries:** `Patient`, `Coverage`, `Organization` (payer), optional
`Organization`/`Practitioner` (billing/rendering), `Claim`.

### Claim
| Our dict field | FHIR `Claim` path | Notes |
|----------------|-------------------|-------|
| (constant) | `status` = `active` | |
| 837P vs 837I (form) | `type.coding` | `professional` / `institutional` (claim-type CS) |
| `patient` / `insured` | `patient.reference` → `Patient` | |
| `payer` | `insurer.reference` → `Organization` | |
| `providers.billing` | `provider.reference` → `Organization`/`Practitioner` | |
| (constant) | `use` = `claim` | |
| `patient_account_no` | `identifier[]` | patient control number |
| `total_charge` | `total` = money(USD) | |
| `box_21_diagnoses[]` | `diagnosis[]` | `sequence` + `diagnosisCodeableConcept` (ICD-10-CM) |
| `service_lines[]` | `item[]` | one item per line (below) |
| subscriber (`group_number`) | `insurance[].coverage.reference` → `Coverage` | `focal=true` |

### Claim.item (per `service_lines[]` entry)
| Our line field | FHIR `Claim.item` path |
|----------------|------------------------|
| (index) | `sequence` |
| `box_24d_procedure_code` (+ modifiers) | `productOrService.coding` (CPT/HCPCS) |
| `box_24f_charges` / `box_47_line_charge` | `net` = money |
| `box_24g_units` / `box_46_units` | `quantity.value` |
| `box_24a_service_date` / `service_date` | `servicedDate` (or `servicedPeriod` for ranges) |
| `box_24e_diagnosis_pointers` | `diagnosisSequence[]` |
| `box_42_revenue_code` (837I) | `revenue.coding` |

### Patient / Coverage / Organization (referenced)
| Source | Resource → path |
|--------|-----------------|
| `insured`/`patient` `last_name_or_org`,`first_name` | `Patient.name` (family/given) |
| `patient.date_of_birth` | `Patient.birthDate` |
| `patient.gender` | `Patient.gender` |
| `insured.id` (member id) | `Patient.identifier` / `Coverage.subscriberId` |
| `group_number` | `Coverage.class` (group) |
| `payer` → | `Coverage.payor.reference` → `Organization` |
| `payer.last_name_or_org`,`id` | `Organization.name`, `Organization.identifier` |

---

## 5.4 835 → `ExplanationOfBenefit`   *(V2-B)*

**Bundle entries:** `Patient`, `Coverage`, `Organization` (payer/payee), `EOB`.

| Our dict field | FHIR `ExplanationOfBenefit` path |
|----------------|----------------------------------|
| (constant) | `status`=`active`, `use`=`claim`, `outcome`=`complete` |
| `claims[].patient_control_number` | `identifier[]` / `claim.reference` |
| `payer` | `insurer.reference` → `Organization` |
| `payee` | `Organization` (payee) |
| `claims[].total_charge` / `total_paid` | `total[]` (submitted / benefit) |
| `service_payments[]` | `item[]` (procedure, `net`, `servicedDate`) |
| `service_payments[].paid_amount` | `item.adjudication[]` (benefit) |
| `adjustments[]` (CAS group/reason/amount) | `item.adjudication[]` / `adjudication` (CO/PR/OA/PI) |
| `header.payment` (BPR/TRN) | `payment.amount`, `payment.identifier` |

Profile target: **CARIN Blue Button** (the strict part — the reason V2-B is its own
phase).

---

## 5.5 834 → `Coverage`   *(V2-C)*

| Our dict field | FHIR `Coverage` path |
|----------------|----------------------|
| `members[].subscriber_indicator` | `relationship` (self/dependent) |
| `members[].member` | `beneficiary.reference` → `Patient` |
| `members[].references` (subscriber/group) | `subscriberId`, `class[]` |
| `payer` | `payor.reference` → `Organization` |
| `coverages[].insurance_line` | `type.coding` (HLT/DEN/VIS) |
| `coverages[].dates[]` | `period.start` / `period.end` |
| `members[].benefit_status` | `status` (active/cancelled) |

---

## 5.6 270 / 271 → `CoverageEligibilityRequest` / `Response`   *(V2-C)*

| Our dict field | FHIR path |
|----------------|-----------|
| subscriber `info` | `patient.reference` → `Patient` |
| payer | `insurer.reference` → `Organization` |
| provider | `provider.reference` |
| (constant) | `purpose` = `benefits` / `validation` |
| 271 `eligibility[]` (EB) | Response `insurance[].item[]` (benefit, network, amounts) |
| 270 `inquiries[]` (EQ) | Request `item[].category` (service type codes) |

## 5.7 276 / 277 → `Task`   *(V2-C)*

| Our dict field | FHIR `Task` path |
|----------------|------------------|
| (constant) | `status`, `intent`=`order`, `code`=claim-inquiry |
| `claims[].trace_number` | `identifier[]` |
| `claims[].statuses[]` (STC category/status) | `businessStatus` / `output[]` |
| patient / provider | `for.reference` / `requester.reference` |

---

## 5.8 Worked example — 837P sample → Claim Bundle

**Our dict (simplified):**
```json
{
  "source_transaction": "ANSI X12 837P",
  "claims": [{
    "patient_account_no": "PATACCT001",
    "total_charge": "350.00",
    "insured": { "last_name_or_org": "SMITH", "first_name": "JOHN", "id": "MEMBER12345" },
    "payer":   { "last_name_or_org": "ACME INSURANCE COMPANY", "id": "PAYER001" },
    "box_21_diagnoses": [{ "code": "J209", "qualifier": "ABK" }],
    "service_lines": [{ "box_24d_procedure_code": "99213", "box_24f_charges": "150.00" }]
  }]
}
```

**FHIR Bundle (abridged):**
```json
{
  "resourceType": "Bundle",
  "type": "collection",
  "entry": [
    { "resource": { "resourceType": "Patient", "id": "patient-1",
        "name": [{ "family": "SMITH", "given": ["JOHN"] }],
        "identifier": [{ "value": "MEMBER12345" }] } },
    { "resource": { "resourceType": "Organization", "id": "org-payer",
        "name": "ACME INSURANCE COMPANY" } },
    { "resource": { "resourceType": "Coverage", "id": "coverage-1",
        "status": "active",
        "beneficiary": { "reference": "Patient/patient-1" },
        "payor": [{ "reference": "Organization/org-payer" }] } },
    { "resource": {
        "resourceType": "Claim",
        "status": "active",
        "type": { "coding": [{ "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                               "code": "professional" }] },
        "use": "claim",
        "patient": { "reference": "Patient/patient-1" },
        "insurer": { "reference": "Organization/org-payer" },
        "identifier": [{ "value": "PATACCT001" }],
        "diagnosis": [{ "sequence": 1,
          "diagnosisCodeableConcept": { "coding": [{
            "system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "J209" }] } }],
        "insurance": [{ "sequence": 1, "focal": true,
          "coverage": { "reference": "Coverage/coverage-1" } }],
        "item": [{ "sequence": 1,
          "productOrService": { "coding": [{
            "system": "http://www.ama-assn.org/go/cpt", "code": "99213" }] },
          "net": { "value": 150.00, "currency": "USD" } }],
        "total": { "value": 350.00, "currency": "USD" }
    } }
  ]
}
```

Note how `Patient`, `Organization`, and `Coverage` are separate entries the `Claim`
**references**, each diagnosis/procedure code carries its **system**, and the whole
set travels in one **Bundle** — the three FHIR ideas in action.
