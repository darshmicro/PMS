# M20 (Development Plan) — Setup & Verification

## What's new in this module

```text
app/models/development_plan.py          DevelopmentPlan - zero or more rows per
                                          Employee_Performance, no lock/stage gate
app/services/development_plan_service.py  validate_completion_status, stamp_updated
app/schemas/development_plan.py         DevelopmentPlanCreate, DevelopmentPlanUpdate,
                                          DevelopmentPlanOut
app/api/routes/development_plans.py     5 endpoints: list, get, create, edit, export
sql/026_create_development_plan_tables.sql   DDL: Development_Plans, with a CHECK
                                          constraint on the inferred CompletionStatus vocabulary
sql/027_seed_development_plan_permissions.sql  New DEVELOPMENT_PLAN.VIEW / .EDIT codes
tests/test_development_plan_service.py      3 unit tests
tests/test_development_plan_routes_smoke.py 3 end-to-end ASGI tests
```

## Design decisions

**No RBAC matrix row exists for this module - the same kind of gap M18 found with
Employee_Competency.** Spec Section 5's matrix runs from "Own Self-Assessment" through "Audit
Log," and nothing named "Development Plan" appears anywhere in it. What the spec does give:
Section 7's screen list has an Employee-facing "My Development Plan" screen, and both
`HODReview` and `ManagerReview` (M13/M14) already capture free-text `DevelopmentRecommendation`/
`TrainingRequirement` fields during their own review stages. Reading those together, this
module reuses `ASSIGNMENT.EDIT`/`.VIEW`'s exact role split from M11 rather than inventing a
narrower one with no textual basis: Manager, HOD, HR, Plant Head, MD and HR Administrator can
create/edit; Employee gets View only, own-record scope, matching the "My Development Plan"
screen. HOD is folded into the edit set (M11's `ASSIGNMENT.EDIT` left HOD view-only) because
HOD's own review stage is one of the two places the underlying recommendation text already
gets written.

**No stage or lock gate at all - deliberately, unlike every review/approval module so far.**
A development plan's whole purpose is tracking a skill gap through to a training `TargetDate`,
and that date routinely falls well after the appraisal cycle that created the plan has already
reached `FINAL_APPROVED`/`IsLocked`. Every other module's `ensure_stage_editable()` blocks
edits on a locked record; this module has no such function at all, so `CompletionStatus`
(and every other field) stays editable regardless of the underlying `Employee_Performance`'s
status or lock state. `test_editing_survives_appraisal_lock` proves this directly - a plan
created before lock is still updatable to `COMPLETED` after the record is finalized and locked.

**`CompletionStatus`'s vocabulary is inferred, not read off the DDL.** Unlike every other
validated vocabulary in this codebase (measurement types from KPI Master, workflow statuses
from the diagram, RBAC actions from the matrix legend), the DDL for `Development_Plans` gives
only a default value (`'PENDING'`) and no enum or CHECK constraint - the spec never actually
enumerates the allowed values. `PENDING` / `IN_PROGRESS` / `COMPLETED` is the minimum
vocabulary that makes "track training completion over time" (this module's own description in
the build-order table) meaningful at all, applied as both a service-layer validator and a SQL
`CHECK` constraint (defense in depth) - flagged explicitly here since it's an interpretive
addition, not a schema fact.

**Zero or more rows per record, not one.** Unlike every review/approval table since M13 (all
carrying a `UniqueConstraint` on `PerformanceID`, reused/overwritten across the record's
lifecycle), `Development_Plans` has no such constraint in the spec's own DDL - a record can
have several skill gaps, each tracked as its own row with its own target date and completion
status. The API reflects this: `POST /development-plans` always creates a new row, list/get
return a collection, and there's no "create-or-update the one row" helper the way
`_get_or_create_review`-style functions work in the review-stage modules.

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| CompletionStatus must be one of PENDING / IN_PROGRESS / COMPLETED | `validate_completion_status` | 400 |

That's the only service-layer rule this module needs - there's no score, no multi-field
cross-validation, and (deliberately) no stage/lock gate.

## Setup

```sql
-- after 001-025 from M1-M19
:r sql/026_create_development_plan_tables.sql
:r sql/027_seed_development_plan_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**194 tests total (188 carried over from M1-M19 + 6 new)**, all passing with zero
regressions: unit tests for the completion-status validator
(`test_development_plan_service.py`), plus **end-to-end ASGI tests**
(`test_development_plan_routes_smoke.py`) covering the full create/view/edit lifecycle, the
invalid-status rejection, the stage-wise export, editing surviving a subsequent appraisal
lock, and an employee being able to view but not create a plan on their own record (a plain
403 from the missing `DEVELOPMENT_PLAN.EDIT` permission, no ownership check needed since the
permission gate itself is the only thing employees lack).

Route registration was also verified via `app.openapi()`: **121 total paths** across 25
routers, zero path collisions.

## What M21+ will build on top of this

M21 (PIP Module, per the build-order table: "Improvement plan lifecycle") is next, and its own
DDL (`PIP`, visible in the same design-doc section as `Development_Plans`) looks structurally
similar - `EmployeeID`-scoped rather than `PerformanceID`-scoped this time (a PIP isn't tied to
one appraisal cycle the way a development plan is), with `PIPStartDate`/`PIPEndDate` and an
`Outcome` field suggesting it has more of a genuine lifecycle (open -> running -> closed) than
this module's free-form completion tracking. Like Development Plan and Employee_Competency
before it, PIP has no RBAC matrix row of its own either - Section 5's matrix still stops at
Audit Log - so M21 will need to make a similar reasoned, documented call about who may open,
edit and close a PIP.
