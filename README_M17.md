# M17 (MD Final Approval) — Setup & Verification

## What's new in this module

```text
app/models/md_approval.py             MDApproval - one row per Employee_Performance,
                                        structurally identical to PlantHeadApproval (no score)
app/services/md_approval_service.py   get_hr_score, ensure_stage_editable,
                                        validate_return_has_comments, stamp_decision,
                                        finalize_and_lock
app/schemas/md_approval.py            MDApprovalActionRequest, MDApprovalOut
app/api/routes/md_approvals.py        5 endpoints: list, get, approve, return, stage-wise export
sql/020_create_md_approval_tables.sql   DDL: MD_Approvals, with a CHECK constraint
                                        restricting Decision to APPROVE/RETURN
sql/021_seed_md_approval_permissions.sql  New MD_APPROVAL.VIEW / .EDIT codes
tests/test_md_approval_service.py       11 unit tests for every validator
tests/test_md_approval_routes_smoke.py  3 end-to-end ASGI route tests
```

## Design decisions

**Approval is the workflow's terminus, so this module is the first to actually lock a
record.** `Employee_Performance.IsLocked` has existed since M11 and every stage's own
`ensure_stage_editable()` has checked it since - but no module has ever *set* it to `True`.
The design doc's workflow diagram gives `FINAL_APPROVED` an outgoing arrow with no actor at
all: `FINAL_APPROVED --> LOCKED : System locks record`. That phrasing ("System locks", not "X
approves/returns") is the tell that this isn't a separate stage with its own table or RBAC
row - it's a mechanical consequence of reaching `FINAL_APPROVED`. So `finalize_and_lock()`
sets `Status = FINAL_APPROVED` and `IsLocked = True` together, in the same call the
`/approve` endpoint makes in the same transaction, rather than modelling `LOCKED` as a
distinct `Status` value the record passes through.

**Score/rating computation is explicitly out of scope here, even though Section 8.5 ties it
to this exact transition.** The spec text reads: *"Lookup `Rating_Master` band containing
`FinalScorePct` → `RatingID` → insert into `Performance_Ratings`, only at `FINAL_APPROVED`
transition."* Taken literally, that could mean this module should compute the final weighted
score and derive a rating right here. But this codebase's own build-order table lists that
work as a separate, later module - **M18, Scoring Engine** ("Weighted score calc, rating
derivation") - and the `Performance_Scores`/`Performance_Ratings` tables that work belongs to
haven't been built yet. Rather than smuggling a partial, ad-hoc version of the Scoring
Engine into this module, `Employee_Performance.FinalScorePct`/`FinalRatingID` (both already
present on the model since M4/M12, both nullable) are left untouched here - `finalize_and_lock()`'s
own docstring flags this explicitly as the hook point M18 will need to call into. This
continues the same discipline followed at every stage since M13: build exactly what this
module's own table and RBAC row call for, and let a later module own the computation that
genuinely belongs to it.

**MD Approval is org-wide, like HR Review - no `_apply_scope` at all.** The MD is a single
top-level executive role, not scoped by department, plant, or reporting line the way
Manager/HOD/Plant Head are. So, exactly as HR Review (M15) had no ownership-scoping function,
`_get_performance()` here is a plain lookup guarded only by the `MD_APPROVAL.VIEW`/`.EDIT`
permission grant - there's no `ensure_is_reviewing_md()` because there's no relationship to
check.

**The narrowest RBAC row in the whole workflow so far.** At every prior approval stage, the
role that had just handed the record off kept at least View: HR kept View on Plant Head
Approval despite no longer holding Edit there. MD Approval breaks that pattern entirely: the
matrix row is `X | X | X | X | X | C,V,A,R | V | X` - Plant Head, the stage immediately
before this one, gets **no access at all**, not even View. Only MD (edit) and HR
Administrator (view) hold anything here. `sql/021` grants `MD_APPROVAL.VIEW` to exactly `MD`
and `HR_ADMIN`, and `MD_APPROVAL.EDIT` to `MD` alone.

**Comments doubles as the mandatory return reason, same as M16.** `MD_Approvals` has no
dedicated reason field either - `Comments` is optional on `/approve`, mandatory (and
non-blank) on `/return`, continuing the asymmetric-strictness pattern between forward and
return actions established in M13 and reused in M16.

**A missing HR score is still a 409 on approve, not a 400 or silent zero.** Nothing between
HR Review (M15) and here changes the score - Plant Head Approval (M16) is itself a
score-less gate - so `get_hr_score()` still reads `HR_Reviews.HRScore` directly, duplicating
the same 409-for-data-integrity guard used in M16 and M15, rather than importing across
modules (consistent with this codebase's convention of small, duplicated per-module helpers
over a shared cross-module service).

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| A completed HR Review score must exist before MD can approve | `get_hr_score` | 409 |
| Actions only allowed while status is `MD_APPROVAL`, and never on a locked record | `ensure_stage_editable` | 409 |
| A return requires non-empty Comments as the reason | `validate_return_has_comments` | 400 |
| Approving sets `Status = FINAL_APPROVED` and `IsLocked = True` together | `finalize_and_lock` | - |

The `Decision` column also got a SQL Server `CHECK` constraint in
`020_create_md_approval_tables.sql` restricting it to `APPROVE`/`RETURN`, as defense in
depth, matching M16's identical constraint.

## Setup

```sql
-- after 001-019 from M1-M16
:r sql/020_create_md_approval_tables.sql
:r sql/021_seed_md_approval_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**160 tests total (149 carried over from M1-M16 + 11 new)**, all passing with zero
regressions: pure validator unit tests for every business rule above
(`test_md_approval_service.py`, including a direct assertion that `finalize_and_lock()` sets
both `Status` and `IsLocked` together), plus **end-to-end ASGI route tests**
(`test_md_approval_routes_smoke.py`) covering the full approve lifecycle (approving
transitions the record to `FINAL_APPROVED` and locks it, and both `/approve` and `/return`
are then blocked with 409), the return path (rejected without comments, succeeds with
comments and sends the record back to `PLANT_HEAD_APPROVAL` without locking it), and the
data-integrity guard when no HR score exists at all.

Route registration was also verified via `app.openapi()`: **115 total paths** across 22
routers, zero path collisions.

## What M18+ will build on top of this

M18 (Scoring Engine) is the natural next module and has real, unfinished work waiting for it:
`Employee_Performance.FinalScorePct`/`FinalRatingID` are still `NULL` on every record this
codebase produces, including ones that have just been locked by this module. Per spec Section
8.4/8.5, the engine needs to (a) compute `Performance_Scores` rows (`KPI_WEIGHTED`,
`COMPETENCY_WEIGHTED`, `FINAL`) from the KPI/Competency data already captured since M9-M12,
(b) copy the `FINAL` figure to `Employee_Performance.FinalScorePct`, and (c) look up the
covering `Rating_Master` band to insert a `Performance_Ratings` row - "only at the
`FINAL_APPROVED` transition" per spec, which after this module means hooking into
`finalize_and_lock()` (or the moment right after it) rather than recomputing scores at every
earlier stage. `Performance_Ratings`' own DDL marks it immutable once inserted - any post-hoc
correction is explicitly a separate, audited "reopen" workflow event (spec Section 4/32), not
an in-place edit - which is a design question M18 (or a later workflow-engine module) will
need to resolve on its own terms.
