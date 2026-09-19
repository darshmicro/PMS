# M14 (HOD Review) — Setup & Verification

## What's new in this module

```text
app/models/hod_review.py            HODReview - one row per Employee_Performance (NOT per-KPI)
app/services/hod_review_service.py  compute_manager_weighted_score_pct, validate_hod_score,
                                      validate_override_has_comments, ensure_is_reviewing_hod,
                                      ensure_stage_editable, ensure_approve_ready, stamp_action
app/schemas/hod_review.py           HODReviewUpdate/Out, HODReviewReturnRequest
app/api/routes/hod_reviews.py       6 endpoints: list/get, edit, approve & forward,
                                      return-to-manager, return-to-employee, stage-wise export
sql/014_create_hod_review_tables.sql   DDL: HOD_Reviews, with CHECK constraints for the
                                      HODScore 0-100 bound and the Action enum
sql/015_seed_hod_review_permissions.sql  New HOD_REVIEW.VIEW / .EDIT codes
tests/test_hod_review_service.py     20 unit tests for every validator
tests/test_hod_review_routes_smoke.py  4 end-to-end ASGI route tests
```

## Design decisions

**HOD reviews the whole record, not KPI-by-KPI - following the schema over the narrative.**
Section 8.1's prose says *"Manager/HOD/HR may override with their own score"* as if HOD
re-scores each KPI the way Manager does. But the `HOD_Reviews` table the spec's own ER
diagram and DDL define has exactly one `HODScore` per `Employee_Performance`, no per-KPI
breakdown. Since the schema is what actually gets built and persisted, this module
follows it literally rather than inventing a parallel per-KPI HOD scoring table the spec
never defines. To keep the override discipline meaningful at this coarser grain, the
service computes a reference figure using Section 8.2's own weighted formula
(`ManagerScore x KPIWeightage / 5`, summed across every KPI) from the Manager Review
scores, and exposes it read-only as `manager_weighted_score_pct`. If the HOD's own score
differs from that reference by more than a small rounding tolerance, `HODComments`
become mandatory - "never silently," just applied at the record grain this table
actually offers instead of the KPI grain Manager Review uses.

**No view access at all for Employee or Manager - a genuine change from every prior
review-stage module.** Assignment (M11), Self-Assessment (M12) and Manager Review (M13)
all gave the employee or their manager at least View rights somewhere in the chain. HOD
Review's RBAC matrix row is different: Employee and Manager both get `X` (no access at
all), not even View. `sql/015` reflects this literally - neither role ever appears in
either permission grant, so `require_permission` rejects them with a 403 before the
route's own scope filter (`_apply_scope`) ever runs. Because of this, `_apply_scope` for
this module is simpler than every prior one: no self/reports branch is needed, only
HOD (department-scoped) versus the broad business-admin roles.

**Three exits, each a concrete labelled arrow, following M13's resolution pattern.** The
design doc's diagram gives HOD Review three distinct outcomes: approve & forward to HR
Review, return to Manager, or return to Employee. Each is its own endpoint
(`/approve`, `/return-to-manager`, `/return-to-employee`) that transitions
`Employee_Performance.Status` straight to that arrow's own named target - continuing the
"the diagram's own labelled arrow is the concrete target status, not a generic
intermediate RETURNED state" resolution M13 established. `return-to-employee` also
resets every `Self_Assessment.Status` to `RETURNED` (mirroring M13's return-to-employee
behavior exactly); `return-to-manager` touches no other table, since Manager Review's own
`Action`/`ActionedAt` fields record the manager's *own* prior decision and shouldn't be
retroactively altered by HOD's decision to send it back.

**Approving requires a score; returning doesn't.** Matching M13's asymmetry between
`submit()` (strict) and `return()` (lenient): `approve()` requires an `HODScore` to
already be recorded (`ensure_approve_ready`), but both return actions only require a
reason - an HOD can send a record back at any point in their review, fully or partially
scored, without first having to finish it.

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| Only the employee's own HOD may edit their HOD Review | `ensure_is_reviewing_hod` | 403 |
| A record outside the caller's view scope entirely (Employee/Manager never even reach this - see above) | `_apply_scope` | 404 |
| Edits only allowed while status is `HOD_REVIEW`, and never on a locked record | `ensure_stage_editable` | 409 |
| HOD score must be 0-100 | `validate_hod_score` | 400 |
| A score that differs meaningfully from the manager-weighted reference requires comments | `validate_override_has_comments` | 400 |
| An HOD score must exist before the record can be approved and forwarded to HR Review | `ensure_approve_ready` | 400 |
| A reason is required for either return action | route handler | 400 |

The `HODScore` bound and the `Action` enum also got SQL Server `CHECK` constraints in
`014_create_hod_review_tables.sql` as defense in depth. The override-requires-comments
rule needs the sibling Manager Review rows to compute its reference figure, so - like
every cross-row rule since M8 - it stays in the service layer.

## Setup

```sql
-- after 001-013 from M1-M13
:r sql/014_create_hod_review_tables.sql
:r sql/015_seed_hod_review_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**116 tests total (95 carried over from M1-M13 + 21 new)**, all passing with zero
regressions: pure validator unit tests for every business rule above
(`test_hod_review_service.py`), plus **end-to-end ASGI route tests**
(`test_hod_review_routes_smoke.py`) covering the full approve lifecycle (a different HOD
blocked entirely, the actual HOD can view the manager-weighted reference score,
approving blocked until scored, a matching score needs no comments, approve succeeds and
transitions to `HR_REVIEW`, post-approval edits blocked), the score-override path
(rejected without comments, accepted with them), and both return paths
(return-to-manager resets the record to `MANAGER_REVIEW` and is verified readable
through M13's own unmodified endpoint; return-to-employee resets every KPI's
Self-Assessment status to `RETURNED` and is verified editable again through M12's own
unmodified endpoint).

Route registration was also verified via `app.openapi()`: 101 total paths across 19
routers, zero path collisions.

## What M15+ will build on top of this

`Employee_Performance.Status == HR_REVIEW` is where HR Review & Calibration (M15) picks
up, per the ER diagram's `HR_Reviews` table - another whole-record review like this one,
but with a `CalibrationAdjustment` field the spec explicitly says is *"mandatory if
adjustment <> 0"* (its own AdjustmentReason column), a rule this module's
override-requires-comments pattern generalizes cleanly to. M15 is also the first stage
with unrestricted Create/View/Edit for HR alone (`C,V,E`, no Approve/Return action column
in the matrix the way HOD/Plant Head/MD have) - forwarding to Plant Head Approval (M16)
appears to be implicit in HR completing calibration rather than a separate labelled
action, which will need its own design decision once M15 is underway.
