# M13 (Manager Review) — Setup & Verification

## What's new in this module

```text
app/models/manager_review.py        ManagerReview - one row per Employee_KPI
app/services/manager_review_service.py  validate_manager_score, validate_override_has_comments,
                                      ensure_is_reviewing_manager, ensure_stage_editable,
                                      validate_submission_ready, stamp_action
app/schemas/manager_review.py       ManagerReviewKPIUpdate/Out, ManagerReviewReturnRequest, ManagerReviewOut
app/api/routes/manager_reviews.py   6 endpoints: list/get, edit-per-KPI, submit, return, stage-wise export
sql/012_create_manager_review_tables.sql   DDL: Manager_Reviews, with CHECK constraints for
                                      the ManagerScore 1-5 bound and the Action enum
sql/013_seed_manager_review_permissions.sql  New MANAGER_REVIEW.VIEW / .EDIT codes
tests/test_manager_review_service.py     18 unit tests for every validator
tests/test_manager_review_routes_smoke.py  2 end-to-end ASGI route tests
```

## Design decisions

**Edit rights are Manager-only, not "any broad-admin role."** The RBAC matrix's Manager
Review row is `C,V,E,R` for Manager and `V` for everyone else in the chain - including
HOD, HR, Plant Head and MD, despite Plant Head/MD's general grant of full business-admin
rights elsewhere (spec Section 4). This is a deliberate exception the matrix itself
carves out: those roles get their own edit rights starting at HOD Review (M14) onward,
not here. So `MANAGER_REVIEW.EDIT` is seeded to the `MANAGER` role alone, and the route
layer further restricts even that to the employee's own direct manager via
`ensure_is_reviewing_manager()`, which checks `Employee.ManagerID == ctx.employee_id` -
the same relationship column the Employee Master (M4) and Assignment (M11) scoping
already rely on.

**No separate "acknowledge" step, unlike Self-Assessment.** The design doc's state
diagram gives Manager Review a single status with two exits (submit to HOD, or return to
the employee) - there's no diagrammed intermediate the way `EMPLOYEE_ACKNOWLEDGED`
exists for M12. So `Manager_Review` rows are created lazily: the first `PUT` to a KPI
creates its row via get-or-create, rather than requiring an explicit "start review" call
the diagram doesn't ask for.

**Score overrides are never silent.** Section 8.1: *"Manager/HOD/HR may override with
their own score + mandatory comments (never silently)."* Whenever a manager's score for
a KPI differs from the employee's own self-assessed score, `ManagerComments` must be
non-empty - checked both at write time (`validate_override_has_comments`, on every
`PUT`) and again defensively at submission time (`validate_submission_ready`), in case a
row was ever created some other way. When the employee never recorded a self score at
all, there's nothing to "override," so the check is skipped rather than demanding
comments for a score that has no baseline to differ from.

**Returning is deliberately less strict than submitting.** `submit()` requires every
assigned KPI to have a manager score (and every override to carry comments) before the
record can move on to HOD Review. `return()` has no such gate - a manager can send a
record back to the employee at any point, half-reviewed, e.g. "please add evidence for
KPI One" before touching KPI Two at all. What *is* mandatory on return is a reason,
recorded on the audit trail's existing `Reason` field (the same mechanism M3/M4
established for "deactivate requires a reason") rather than adding a new column, since a
justification for sending work back is exactly what that field already exists for.

**Resolves the open question left in M12.** M12's model docstring flagged uncertainty
about whether `Employee_Performance` would ever need a generic `RETURNED` status,
because the design doc's diagram shows both a generic `SELF_ASSESSMENT --> RETURNED -->
SELF_ASSESSMENT` loop *and* specific labelled return arrows (`MANAGER_REVIEW -->
SELF_ASSESSMENT`, etc.). Having now built the concrete return path, the answer is: no.
The specific arrow is the one actually implemented - `return()` sends the whole-record
status straight back to `SELF_ASSESSMENT`, which was already in M12's
`EDITABLE_STATUSES`, so **no code change to M12 was needed**. `RETURNED` only ever
appears as a per-row informational status (`Self_Assessment.Status`, set on every KPI
when a manager returns the record) to let the employee's UI distinguish "sent back for
rework" from "never touched" - never as a whole-record `Employee_Performance.Status`
value. This is verified directly in `test_return_to_employee_requires_reason_and_resets_stage`,
which returns a record and then successfully edits the self-assessment again through
M12's own endpoint with zero changes to that module.

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| Only the employee's own direct Manager may edit their Manager Review | `ensure_is_reviewing_manager` | 403 |
| A record outside the caller's view scope entirely | `_apply_scope` | 404 |
| Edits only allowed while status is `MANAGER_REVIEW`, and never on a locked record | `ensure_stage_editable` | 409 |
| Manager score must be 1-5 | `validate_manager_score` | 400 |
| A score that differs from the employee's self score requires comments | `validate_override_has_comments` | 400 |
| Every assigned KPI must have a manager score before submission (forward to HOD) | `validate_submission_ready` | 400 |
| A reason is required to return the record to the employee | route handler | 400 |

The per-row `ManagerScore` bound and the `Action` enum also got SQL Server `CHECK`
constraints in `012_create_manager_review_tables.sql` as defense in depth. The cross-row
rules (every KPI scored, override-requires-comments across the whole record) stay in the
service layer, following the same split established since M8.

## Setup

```sql
-- after 001-011 from M1-M12
:r sql/012_create_manager_review_tables.sql
:r sql/013_seed_manager_review_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**95 tests total (79 carried over from M1-M12 + 16 new)**, all passing with zero
regressions: pure validator unit tests for every business rule above
(`test_manager_review_service.py`), plus **end-to-end ASGI route tests**
(`test_manager_review_routes_smoke.py`) covering the full submit lifecycle (a
non-manager blocked entirely, matching a score requires no comments, an unexplained
override rejected, submission blocked until every KPI is scored, submission succeeds and
transitions to `HOD_REVIEW`, post-submission edits blocked) and the return lifecycle (a
reason is mandatory, a partially-reviewed record can still be returned, the return resets
the record to `SELF_ASSESSMENT` and is immediately re-editable through M12's own
endpoint).

Route registration was also verified via `app.openapi()`: 95 total paths across 18
routers, zero path collisions.

## What M14+ will build on top of this

`Employee_Performance.Status == HOD_REVIEW` is where HOD Review (M14) picks up, per the
ER diagram's `HOD_Reviews` table - a coarser-grained review than Manager's (one row per
`Employee_Performance`, not per KPI, with `HODScore` as a computed/derived overall
percentage rather than a 1-5 per-KPI score). HOD Review's three-way exit
(`APPROVE_FORWARD` to HR Review, `RETURN_TO_MANAGER`, or `RETURN_TO_EMPLOYEE`) is the
first stage in this system with more than two possible actions, and will need its own
design decision on how that maps onto `Employee_Performance.Status` - following the same
"use the diagram's own labelled arrow as the concrete target status" resolution this
module established.
