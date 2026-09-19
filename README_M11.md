# M11 (KPA/KPI Assignment) — Setup & Verification

## What's new in this module

```text
app/models/assignment.py            EmployeePerformance, EmployeeKPA, EmployeeKPI - the appraisal
                                      "envelope" (one per employee+cycle) that every later stage
                                      (M12 Self-Assessment onward) attaches to via PerformanceID
app/services/assignment_service.py  validate_target, validate_row_weightage, check_duplicate_kpi,
                                      recompute_rollups, ensure_editable, validate_submission_ready
app/schemas/assignment.py           AssignmentCreate/Out, EmployeeKPACreate/Out, EmployeeKPICreate/
                                      Update/Out
app/api/routes/assignments.py       11 endpoints: create/list/get assignment, add/remove KPA,
                                      add/edit/remove KPI, submit, stage-wise export
sql/008_create_assignment_tables.sql   DDL: Employee_Performance, Employee_KPA, Employee_KPI,
                                      with a CHECK constraint for the per-row weightage bound
sql/009_seed_assignment_permissions.sql  New ASSIGNMENT.VIEW / ASSIGNMENT.EDIT permission codes
tests/test_assignment_service.py    16 unit tests for every validator
tests/test_assignment_routes_smoke.py  3 end-to-end ASGI route tests covering the full
                                      create -> assign -> submit lifecycle
```

Unlike M5-M10 (which reused the generic `MASTERS.VIEW/EDIT/DEACTIVATE` codes), this module
introduces its own permission codes, `ASSIGNMENT.VIEW` and `ASSIGNMENT.EDIT`, because assignment
visibility and edit rights follow the **record-scoped** Manager/HOD/broad-role pattern from the
Employee Master (M4), not the flat "everyone views, HR+ edits" pattern the masters use. A Manager
can only see and assign KPAs/KPIs for their own direct reports; a HOD sees their department but
cannot edit at this stage (HOD's own authority begins at the review stage, M14); HR, Plant Head,
MD and HR Administrator see and can assign for everyone, per spec Section 4's grant of full
business-level admin rights to Plant Head/MD.

## Design decisions (the spec leaves these underspecified)

The spec's own instruction for this module is one sentence: *"Provide validation to prevent:
Weightage >100%, Weightage <100%, Duplicate KPI, Invalid target, Missing mandatory KPI."* Three
of these terms needed an explicit interpretation, documented in `assignment_service.py`'s module
docstring:

| Term | Interpretation chosen | Why |
|---|---|---|
| "Weightage must equal 100%" | A single flat rule across every KPI in the whole appraisal, not a nested "KPAs sum to 100, and each KPA's KPIs sum to 100" rule | Matches Section 13's weighted-score formula, which treats each KPI's Weightage as its absolute share of the appraisal (`KPI Score x KPI Weightage / Max Score`), not a share of its parent KPA |
| "Missing mandatory KPI" | An assigned KPA with zero attached KPIs blocks submission | The spec defines no per-KPI "mandatory" flag anywhere in the KPI Master field list (Section 8); the only structural reading available is at the KPA level |
| "Duplicate KPI" | The same KPI cannot appear twice **anywhere** in one employee's appraisal, even filed under two different KPAs | Prevents the same metric being double-counted toward the 100% total |

A fourth decision, not named by the spec at all: `Employee_KPI.MeasurementType` is **copied**
from `KPI_Master` at assignment time rather than read live via the foreign key, so a later edit
to the KPI Master (M6/M7) can never silently reinterpret an in-flight or historical appraisal's
scoring. `Employee_KPA.Weightage` is likewise a read-only rollup, recomputed by
`recompute_rollups()` after every KPI add/edit/remove rather than stored authoritatively — the
KPI rows are the source of truth.

## Workflow enforced

```text
DRAFT --[submit, only when every validation below passes]--> KPI_ASSIGNED
```

`ensure_editable()` blocks every mutating endpoint (add/remove KPA, add/edit/remove KPI) once
status has left `DRAFT` or the record is locked, returning `409 Conflict` — an appraisal cannot
be quietly altered after the employee has moved into self-assessment (M12).

`validate_submission_ready()` runs all three submission-time checks together and reports the
first one that fails, in this order: at least one KPA assigned -> every assigned KPA has at
least one KPI -> total weightage across every KPI equals 100% (within a small rounding
tolerance — see bug #2 below).

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| A KPI's row weightage must be >0 and <=100 | `validate_row_weightage` | 400 |
| A numeric-measurement-type KPI requires a non-negative Target | `validate_target` | 400 |
| A KPI can only be filed under an `Employee_KPA` whose KPAID matches the KPI's own KPA in the master | route handler (`add_kpi`) | 400 |
| The same KPI cannot appear twice in one appraisal, even under different KPAs | `check_duplicate_kpi` | 409 |
| Only a KPA/employee within the caller's scope can be assigned to | `_apply_scope` + route handler | 403 |
| An assignment already exists for this employee+cycle | route handler (`create_assignment`) | 409 |
| No mutation once status has left DRAFT or the record is locked | `ensure_editable` | 409 |
| Every assigned KPA must have >=1 KPI, and total weightage must equal exactly 100%, before submission | `validate_submission_ready` | 400 |

Per-row bound (`Weightage > 0 AND Weightage <= 100`) also got a SQL Server `CHECK` constraint in
`008_create_assignment_tables.sql` as defense in depth. The cross-row rules (duplicate-KPI,
total-equals-100%) can't be expressed as a CHECK constraint and live only in the service layer —
the same split established for the KPI Scoring Rule / Rating Master bands in M8/M9.

## Two real bugs caught and fixed during verification

1. **Floating-point tolerance failure.** `test_submission_tolerates_rounding_noise_near_100`
   (33.33 x 3 = 99.99, which should pass the "must equal 100%" check within the documented 0.01
   tolerance) was failing: `100.0 - 99.99` evaluates to `0.010000000000005116` in IEEE-754
   float, which is *greater than* the 0.01 tolerance by a hair, so a value the business rule is
   explicitly meant to accept was being rejected. Fixed by rounding the delta to 2 decimal places
   (Weightage's own stored precision) before comparing it to the tolerance:
   `round(abs(total - 100.0), 2) > WEIGHTAGE_TOLERANCE`. Confirmed via `pytest -v`: the rounding
   test now passes, and the below-100/above-100/exact-100 tests still correctly reject or accept.
2. **Test-authoring bug, not a production bug** (documented here because it looked like one at
   first): the first draft of the end-to-end smoke test tried to trigger the duplicate-KPI check
   by re-adding a KPI under a *different* `Employee_KPA` than the one its master-data KPA
   actually belongs to — which correctly hit the *KPA-mismatch* rule (400) before the
   duplicate-KPI rule ever got a chance to run (409). The route behavior was correct; the test
   was asserting the wrong rejection reason. Fixed by isolating the duplicate-KPI scenario under
   the KPI's own correct KPA, and adding a separate assertion for the KPA-mismatch case.

## Setup

```sql
-- after 001-007 from M1-M10
:r sql/008_create_assignment_tables.sql
:r sql/009_seed_assignment_permissions.sql
```

No sample assignment data is seeded: M1-M10's seed scripts create no sample `Employees` rows to
assign against (`Employees` is populated by AD sync / the Employee Master screens in a real
deployment), so there is nothing meaningful to pre-populate here without inventing fictitious
employee records outside the spec's own sample-data conventions.

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**60 tests total (44 carried over from M1-M10 + 16 new)**, all passing with zero regressions:
pure validator unit tests for every business rule above (`test_assignment_service.py`), plus
**end-to-end ASGI route tests** (`test_assignment_routes_smoke.py`) that drive the actual HTTP
routes through the full lifecycle — create an assignment, reject a second one for the same
employee+cycle, add two KPAs, reject a KPI filed under the wrong KPA, reject a duplicate KPI,
reject an out-of-bounds weightage, reject a missing numeric target, reject submission while a
KPA has no KPI, reject submission while the total is off 100%, edit a KPI's weightage to reach
exactly 100%, submit successfully, confirm the transitioned record can no longer be mutated
(409), and confirm the stage-wise export route (`/assignments/{id}/export`, spec Section 36A) is
reachable and returns a real `.xlsx` workbook.

Route registration was also verified via `app.openapi()`: 83 total paths across 16 routers, zero
path collisions.

## What M12+ will build on top of this

`Employee_Performance.PerformanceID` is the anchor every later workflow stage attaches to.
Self-Assessment (M12) adds employee-entered achievement values and comments against each
`Employee_KPI` row without touching the KPI/weightage structure locked in by this module's
`KPI_ASSIGNED` status; Manager Review (M13) and every stage after it advance
`Employee_Performance.Status` further along the same state-machine pattern established here
(`ensure_editable` gating mutation to whichever stage currently "owns" the record).
