# M16 (Plant Head Approval) — Setup & Verification

## What's new in this module

```text
app/models/plant_head_approval.py         PlantHeadApproval - one row per Employee_Performance,
                                            no score column at all (see design decisions)
app/services/plant_head_approval_service.py  get_hr_score, ensure_is_reviewing_plant_head,
                                            ensure_stage_editable, validate_return_has_comments,
                                            stamp_decision
app/schemas/plant_head_approval.py        PlantHeadApprovalActionRequest, PlantHeadApprovalOut
app/api/routes/plant_head_approvals.py    5 endpoints: list, get, approve, return, stage-wise export
sql/018_create_plant_head_approval_tables.sql   DDL: PlantHead_Approvals, with a CHECK
                                            constraint restricting Decision to APPROVE/RETURN
sql/019_seed_plant_head_approval_permissions.sql  New PLANT_HEAD_APPROVAL.VIEW / .EDIT codes
tests/test_plant_head_approval_service.py       15 unit tests for every validator
tests/test_plant_head_approval_routes_smoke.py  4 end-to-end ASGI route tests
```

## Design decisions

**No score column at all - the first stage that's a pure decision gate.** Every review
stage so far (Manager/M13, HOD/M14, HR/M15) carries at least one score field. The design
doc's own DDL for `PlantHead_Approvals` breaks that pattern: `ApprovalID`, `PerformanceID`,
`Decision` (APPROVE/RETURN), `Comments`, `ActionedAt`, `ActionedBy` - nothing else. Read
together with the RBAC matrix's "Plant Head Approval: C,V,A,R" row (Create/View/Approve/
Return - conspicuously no Edit column, unlike every review stage's `C,V,E,A,R` or `C,V,E`),
the natural reading is that Plant Head does not touch the score at all: they authorize or
reject the record as a whole, based on the HR-calibrated score the record already carries.
So this module has exactly two actions - `/approve` and `/return` - and no PUT/edit endpoint,
because there is nothing scoreable to edit.

**Scoping compares plants, not people.** HOD Review (M14) scoped access through a direct
per-employee FK (`Employee.HODID`). Plant Head has no equivalent FK - the `Employee` model
(M4) only carries the employee's own `PlantID`. So `ensure_is_reviewing_plant_head()` compares
the *acting* Plant Head's own `Employee.PlantID` against the *reviewed* employee's `PlantID`,
rather than following a direct relationship column. This matches the build-order table's own
description of this module as "Plant-wide approve/return" - the grain is the plant, not a
manager-report or HOD-department relationship. `_apply_scope()` in the router mirrors this:
non-broad-access roles are filtered to records whose employee shares a plant with the caller's
own employee row, via a correlated subquery rather than a simple FK-equality filter.

**Comments doubles as the mandatory return reason.** There is no separate "reason" field on
this table (unlike M13/M14's dedicated return-reason bodies) - `Comments` is the table's only
free-text column, so it plays both roles: an optional note on approve, and the mandatory
reason on return. `validate_return_has_comments()` enforces this the same way every return
action has enforced a mandatory reason since M13 (`return()` strict on `Comments`, `approve()`
lenient - continuing the asymmetric-strictness pattern between forward and return actions).

**Edit rights belong to Plant Head alone, gating both actions with one permission code.**
Since there is no separate "edit vs. approve/return" distinction on this table (nothing to
edit independent of a decision), `PLANT_HEAD_APPROVAL.EDIT` gates both `/approve` and
`/return`, exactly as `HOD_REVIEW.EDIT` gated all three of HOD Review's transition endpoints
in M14. MD and HR Administrator get View only (their `V` in the matrix row); Employee,
Manager, HOD and HR get no access at all - this is the first stage since HOD Review (M14)
where HR itself has *no* access, a further step in the pattern that visibility narrows as a
record moves further up the approval chain, even though HR reviewed and forwarded the very
same record one stage earlier.

**A missing HR score is a 409, not a 400 or a silent zero.** `get_hr_score()` requires a
completed `HR_Reviews` row (with `HRScore` set) to exist before Plant Head can approve at
all. In the normal workflow this can never actually happen (a record only reaches
`PLANT_HEAD_APPROVAL` by HR completing calibration, per M15), so hitting this path means
something is wrong with the data itself - continuing the exact same 409-for-data-integrity
pattern used for the missing-HOD-score guard in M15's `get_hod_score()`. Note this guard is
enforced on `/approve` (approving without a real score to approve would be meaningless) but
deliberately *not* required on `/return` - a return should always be possible regardless of
whether the score situation is itself the problem being flagged.

**One exit each way, closing the loop HR Review's single exit left open.** HR Review (M15)
had exactly one exit and no return path of its own. This module supplies the return arrow
the design doc's diagram always intended (`PLANT_HEAD_APPROVAL -> HR_REVIEW`) - and, unlike
M13/M14's returns which send work back to be *redone* by an earlier stage, this return sends
the record back to be *reconsidered* by HR, who may adjust the calibration and forward it
again. It lands on the same `HR_REVIEW` status HR Review already treats as editable, so - the
same "later module's return path needs zero changes to the module it returns into" pattern
established in M13/M14 - HR Review required no code changes at all to receive it.

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| A completed HR Review score must exist before Plant Head can approve | `get_hr_score` | 409 |
| Actions only allowed while status is `PLANT_HEAD_APPROVAL`, and never on a locked record | `ensure_stage_editable` | 409 |
| Only the reviewed employee's Plant Head (same `PlantID`) may approve or return | `ensure_is_reviewing_plant_head` | 403 |
| A return requires non-empty Comments as the reason | `validate_return_has_comments` | 400 |

The `Decision` column also got a SQL Server `CHECK` constraint in
`018_create_plant_head_approval_tables.sql` restricting it to `APPROVE`/`RETURN`, as defense
in depth. The return-requires-comments rule is a single-row rule in principle, but - like
every business rule that isn't a fixed per-column bound since M8 - it stays in the service
layer rather than a CHECK constraint, since a CHECK constraint can't express "non-empty only
when this specific action is being taken."

## Setup

```sql
-- after 001-017 from M1-M15
:r sql/018_create_plant_head_approval_tables.sql
:r sql/019_seed_plant_head_approval_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**149 tests total (134 carried over from M1-M15 + 15 new)**, all passing with zero
regressions: pure validator unit tests for every business rule above
(`test_plant_head_approval_service.py`, including the plant-matching ownership check under
matching/mismatched/no-plant/unknown-employee conditions), plus **end-to-end ASGI route
tests** (`test_plant_head_approval_routes_smoke.py`) covering the full approve lifecycle
(approving transitions the record to `MD_APPROVAL`, post-approval actions are blocked), the
return path (rejected without comments, succeeds with comments and sends the record back to
`HR_REVIEW`), scoping (a Plant Head from a different/no-matching plant gets a 404 via
`_apply_scope` before any ownership check runs - the same 404-not-403 pattern established in
M14), and the data-integrity guard when no HR score exists at all.

Route registration was also verified via `app.openapi()`: **110 total paths** across 21
routers, zero path collisions.

## What M17+ will build on top of this

`Employee_Performance.Status == MD_APPROVAL` is where MD Final Approval (M17) picks up. Per
the RBAC matrix ("MD Approval: C,V,A,R" for MD, no View even for HR Administrator or Plant
Head this time - the matrix row reads `X | X | X | X | X | C,V,A,R | V | X`, so this is the
*narrowest* access row yet, with only MD and HR Administrator holding anything at all) and
the diagram's two exits (`approve -> FINAL_APPROVED`, `MD returns for clarification ->
PLANT_HEAD_APPROVAL`), MD Approval will very likely mirror this module's shape almost
exactly - the `MD_Approvals` DDL read alongside `PlantHead_Approvals` earlier in this session
is structurally identical (`ApprovalID`/`PerformanceID`/`Decision`/`Comments`/`ActionedAt`/
`ActionedBy`, no score column). The one genuinely new piece is that an MD approval is the
workflow's *final* one: reaching `FINAL_APPROVED` is expected to lock the record (this
codebase already has an `IsLocked` flag on `Employee_Performance`, checked by every stage's
`ensure_stage_editable()` so far but never yet *set* by any module) - M17 is likely the first
module that actually flips it.
