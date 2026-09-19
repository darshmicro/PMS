# M12 (Employee Self-Assessment) — Setup & Verification

## What's new in this module

```text
app/models/self_assessment.py       SelfAssessment - one row per Employee_KPI
app/services/self_assessment_service.py  compute_achievement_pct, lookup_self_score,
                                      validate_self_score, ensure_own_record,
                                      ensure_stage_editable, validate_submission_ready
app/schemas/self_assessment.py      SelfAssessmentKPIUpdate/Out, SelfAssessmentOut
app/api/routes/self_assessments.py  6 endpoints: list/get, acknowledge, edit-per-KPI,
                                      submit, stage-wise export
sql/010_create_self_assessment_tables.sql   DDL: Self_Assessments, with a CHECK
                                      constraint for the SelfScore 1-5 bound
sql/011_seed_self_assessment_permissions.sql  New SELF_ASSESSMENT.VIEW / .EDIT codes
tests/test_self_assessment_service.py    22 unit tests for every validator
tests/test_self_assessment_routes_smoke.py  3 end-to-end ASGI route tests
```

## Design decisions

**Self-assessment is owner-only, unlike Assignment.** The RBAC matrix's "Own
Self-Assessment" row grants Create/View/Edit to the **Employee** alone (until submit);
Manager/HOD/HR/Plant Head/MD/HR Administrator get View only. This is a real behavioral
difference from M11's Assignment module, where a Manager or HR user could act on an
employee's behalf. `SELF_ASSESSMENT.EDIT` is therefore granted only to the `EMPLOYEE`
role in `011_seed_self_assessment_permissions.sql`, and every mutating route additionally
calls `ensure_own_record()`, which checks `performance.EmployeeID == ctx.employee_id` -
so even if an EMPLOYEE-role account somehow held the assignment-scope permission, they
still couldn't edit anyone else's self-assessment. The 403 this produces is distinct from
the 404 a Manager/HOD gets when the record falls entirely outside their *view* scope
(`_apply_scope`), which is tested separately (see below).

**Three workflow transitions live in this module**, matching the design doc's state
diagram (`Section 6`) more precisely than a single "submit" action would:

```text
KPI_ASSIGNED --[acknowledge]--> EMPLOYEE_ACKNOWLEDGED --[first KPI edit]--> SELF_ASSESSMENT --[submit]--> MANAGER_REVIEW
```

`acknowledge()` seeds one `DRAFT` `Self_Assessment` row per `Employee_KPI` so there's
always a row to update in place. The move into `SELF_ASSESSMENT` status happens
automatically on the first successful KPI edit rather than needing its own explicit
endpoint - the diagram labels that arrow "Employee starts assessment," which editing a
KPI *is*, so a separate "start" call would just be a formality the UI would always fire
immediately before the first edit anyway.

**Non-numeric measurement types have no achievement percentage.** Section 8.1's
algorithm (Achievement -> AchievementPct -> scoring-rule lookup -> Score) only makes
sense for the numeric-target measurement types already established in M11
(`assignment_service.NUMERIC_TARGET_TYPES`, reused here so the two modules agree). For
`YESNO`/`DATE`/`MILESTONE`/`QUALITATIVE`, `AchievementPct` stays `NULL` and the employee
supplies `SelfScore` (1-5) directly in the request body - there's nothing in the spec to
compute it from, and inventing a percentage for a qualitative KPI would be worse than
just asking for the score.

**A gap in the configured scoring bands is a hard failure, not a silent default.** If no
`KPI_Scoring_Rules` band (KPI-specific or the global `KPIID IS NULL` default) covers the
computed achievement percentage, the edit is rejected with a 400 naming the percentage,
rather than picking some default score. In a system whose entire purpose is an accurate,
auditable appraisal, silently misrepresenting an employee's achievement would be worse
than blocking the edit until HR fixes the gap.

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| Only the owning employee may create/edit their own self-assessment | `ensure_own_record` | 403 |
| A record outside the caller's view scope at all (Manager/HOD/broad-role) | `_apply_scope` (404, not 403 - the record isn't visible to them, full stop) | 404 |
| Edits only allowed while status is `EMPLOYEE_ACKNOWLEDGED` or `SELF_ASSESSMENT`, and never on a locked record | `ensure_stage_editable` | 409 |
| Can only acknowledge a record currently in `KPI_ASSIGNED` | route handler | 409 |
| Self score must be 1-5 | `validate_self_score` | 400 |
| Achievement% must resolve to a configured scoring band (KPI-specific first, then global default) | `lookup_self_score` | 400 |
| Every assigned KPI must have both Achievement and SelfScore recorded before submission | `validate_submission_ready` | 400 |

The per-row `SelfScore` bound also got a SQL Server `CHECK` constraint in
`010_create_self_assessment_tables.sql` as defense in depth. The cross-row
"every KPI assessed" rule can't be expressed as a single-table CHECK and lives only in
the service layer, following the same split established for M11's weightage-total rule.

## One real bug caught and fixed during verification

The service-layer unit tests (`test_self_assessment_service.py`) pass plain Python
`float`s directly into `compute_achievement_pct()`, so they never exposed a type
mismatch. The end-to-end route test did: `Employee_KPI.Target` is a SQLAlchemy
`Numeric(18,4)` column, and once a row has actually been persisted and re-read from the
database, SQLAlchemy hands it back as `decimal.Decimal`, not `float`. Python's `/`
operator refuses to mix `float` and `Decimal` (`TypeError: unsupported operand type(s)
for /`), so every achievement update against a real (not just in-memory-constructed) KPI
row was crashing with a 500. Fixed by coercing both operands to `float()` explicitly
before dividing. This is exactly the kind of bug the end-to-end ASGI route tests exist to
catch that a pure validator unit test, called with hand-built Python values, cannot - the
same lesson M3/M4's route-ordering bug first established for this project.

## Setup

```sql
-- after 001-009 from M1-M11
:r sql/010_create_self_assessment_tables.sql
:r sql/011_seed_self_assessment_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**79 tests total (60 carried over from M1-M11 + 19 new)**, all passing with zero
regressions: pure validator unit tests for every business rule above
(`test_self_assessment_service.py`), plus **end-to-end ASGI route tests**
(`test_self_assessment_routes_smoke.py`) covering the full lifecycle - acknowledge,
reject a second acknowledge, edit a numeric KPI and confirm the score is auto-derived
from the achievement percentage, confirm the status auto-advances to `SELF_ASSESSMENT`
after the first edit, reject submission while a qualitative KPI has no self score,
supply a direct self score for the qualitative KPI, reject an out-of-range self score,
submit successfully and confirm every KPI's row flips to `SUBMITTED`, confirm
post-submission edits are blocked (409), confirm the stage-wise export route works, and
confirm the View-but-not-Edit split for a non-owning role (HR) with legitimate view
access.

Route registration was also verified via `app.openapi()`: 89 total paths across 17
routers, zero path collisions.

## What M13+ will build on top of this

`Employee_Performance.Status == MANAGER_REVIEW` is where Manager Review (M13) picks up.
Each KPI's `Self_Assessment` row (Achievement, AchievementPct, SelfScore, comments)
becomes read-only reference context the manager reviews against, entering their own
score/comments on a parallel `Manager_Reviews` table (per the ER diagram) rather than
overwriting the employee's own record - preserving both perspectives for HOD/HR/Plant
Head/MD review later, exactly as the spec's "never silently" language in Section 8.1
implies. M13 will also be the first module to produce the `RETURNED` status this
module's `ensure_stage_editable()` deliberately does not yet accept (see the model's
docstring) - once a return path exists, this module's editable-status set will be
extended to include it.
