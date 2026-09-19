# M15 (HR Review & Calibration) — Setup & Verification

## What's new in this module

```text
app/models/hr_review.py             HRReview - one row per Employee_Performance
app/services/hr_review_service.py   get_hod_score, validate_calibration_adjustment_reason,
                                      compute_hr_score, validate_hr_score_bounds,
                                      ensure_stage_editable, ensure_complete_ready, stamp_completed
app/schemas/hr_review.py            HRReviewUpdate, HRReviewOut
app/api/routes/hr_reviews.py        4 endpoints: list/get, edit, complete calibration, stage-wise export
sql/016_create_hr_review_tables.sql    DDL: HR_Reviews, with a CHECK constraint for the
                                      HRScore 0-100 bound
sql/017_seed_hr_review_permissions.sql  New HR_REVIEW.VIEW / .EDIT codes
tests/test_hr_review_service.py     18 unit tests for every validator
tests/test_hr_review_routes_smoke.py  4 end-to-end ASGI route tests
```

## Design decisions

**HRScore is derived, not independently entered.** The stage is literally named "HR
Review **& Calibration**," and Section 8.4's final-score formula lists *"+ HR Calibration
Adjustment, if any, with reason"* as something added on top of the KPI+Competency
component sum - not a wholesale re-score. So `HRScore` is always computed as
`HODScore + CalibrationAdjustment` and recomputed by the service on every edit, rather
than being a field HR types a number into directly. This also means a record with no
adjustment at all still gets a valid `HRScore` (equal to the HOD's own score) the moment
HR touches the record - "no adjustment needed" is itself a valid, completable outcome,
not a state requiring extra action.

**Only one exit, unlike every review stage since M13.** The design doc's diagram gives
`HR_REVIEW` exactly one arrow out (`HR completes calibration -> PLANT_HEAD_APPROVAL`) and
none of its own back into an earlier stage - confirmed by the RBAC matrix, whose HR
Review/Calibration row is `C,V,E` for HR with no Approve/Return columns the way HOD's and
(coming in M16) Plant Head's rows have. So this module has a single `/complete` action,
not a family of transition endpoints. A return path *into* `HR_REVIEW` does exist
(`PLANT_HEAD_APPROVAL -> HR_REVIEW`, arriving in M16), but it lands on the same
`HR_REVIEW` status this module already treats as editable - continuing the now-familiar
pattern from M13/M14 where a later module's return path needs zero changes to the
modules it returns into.

**Edit rights belong to HR alone - not even HR Administrator.** Continuing the literal
RBAC-matrix-over-general-rule pattern established in M13/M14: HR Administrator, Plant
Head and MD all get View only on this specific row, despite Plant Head/MD's broader
business-admin rights elsewhere and HR Administrator's general "administers on HR's
behalf" role. `sql/017` grants `HR_REVIEW.EDIT` to `HR` and nobody else.

**No department scoping - HR reviews org-wide.** Unlike Manager (own reports) or HOD (own
department), HR's role in this system is calibrating *across* departments, so there is no
`_apply_scope` function in this module at all - any record is visible to anyone holding
`HR_REVIEW.VIEW`, and the permission grant itself is the only access control (this is also
why there's no per-record "is this actually your report" check the way `ensure_is_reviewing_manager`
/ `ensure_is_reviewing_hod` provide in M13/M14).

**A missing HOD score is a 409, not a 400 or a silent zero.** `get_hod_score()` requires a
completed `HOD_Reviews` row to exist before HR can touch the record at all. In the normal
workflow this can never actually happen (a record only reaches `HR_REVIEW` by HOD
approving and forwarding it, per M14), so hitting this path means something is wrong with
the data itself - a `409 Conflict` communicates "the record isn't in a valid state for
this operation" more accurately than a `400` (which would suggest the *request* was bad)
or quietly treating the missing score as zero (which would silently understate every
downstream calculation).

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| A completed HOD Review score must exist before HR can review at all | `get_hod_score` | 409 |
| Edits only allowed while status is `HR_REVIEW`, and never on a locked record | `ensure_stage_editable` | 409 |
| A non-zero calibration adjustment requires a non-empty reason | `validate_calibration_adjustment_reason` | 400 |
| The resulting HR score (HOD score + adjustment) must stay within 0-100 | `validate_hr_score_bounds` | 400 |
| Calibration (even a zero adjustment) must be recorded before the record can be forwarded to Plant Head Approval | `ensure_complete_ready` | 400 |

The `HRScore` bound also got a SQL Server `CHECK` constraint in
`016_create_hr_review_tables.sql` as defense in depth. The adjustment-requires-reason
rule and the score-derivation itself both depend on more than a single column in
isolation, so - consistent with every cross-field/cross-row rule since M8 - they stay in
the service layer.

## Setup

```sql
-- after 001-015 from M1-M14
:r sql/016_create_hr_review_tables.sql
:r sql/017_seed_hr_review_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**134 tests total (116 carried over from M1-M14 + 18 new)**, all passing with zero
regressions: pure validator unit tests for every business rule above
(`test_hr_review_service.py`), plus **end-to-end ASGI route tests**
(`test_hr_review_routes_smoke.py`) covering the full completion lifecycle (completing
before any calibration is recorded fails, a comments-only edit auto-derives
`HRScore == HODScore`, completion succeeds and transitions to `PLANT_HEAD_APPROVAL`,
post-completion edits blocked), the adjustment-requires-reason rule (rejected without a
reason, accepted and correctly recomputes `HRScore` with one), an adjustment that would
push the score out of the valid range, and the data-integrity guard when no HOD score
exists at all.

Route registration was also verified via `app.openapi()`: 105 total paths across 20
routers, zero path collisions.

## What M16+ will build on top of this

`Employee_Performance.Status == PLANT_HEAD_APPROVAL` is where Plant Head Approval (M16)
picks up. Per the RBAC matrix ("Plant Head Approval: C,V,A,R" for Plant Head, View only
for MD/HR Administrator, no access for anyone earlier in the chain) and the diagram's two
exits (`approve -> MD_APPROVAL`, `returns -> HR_REVIEW`), this is the first approval
stage with genuine authority to reject and send an entire record back for
recalibration - unlike M13/M14's returns, which send work back to be *redone*, Plant
Head's return sends it back to be *reconsidered* by HR, closing the loop this module's
single-exit design left open.
