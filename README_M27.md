# M27 (Performance History) — Setup & Verification

## What's new in this module

```text
app/services/performance_history_service.py   can_view_employee_history, build_history
app/schemas/performance_history.py             ScoreBreakdownEntryOut, TransitionEntryOut,
                                                 PerformanceHistoryRecordOut, PerformanceHistoryOut
app/api/routes/performance_history.py          2 endpoints: /me, /{employee_id}
sql/037_seed_performance_history_permissions.sql  New PERFORMANCE_HISTORY.VIEW code (no new table)
tests/test_performance_history_service.py       9 unit tests
tests/test_performance_history_routes_smoke.py  6 end-to-end ASGI tests
```

No new model or table. Like M24-M26 before it, this is a "consumption layer" module — it reads
three data sources that already exist (`Employee_Performance`, `Performance_Scores`,
`Workflow_History`) and assembles them per-record, per-employee, for the first time. Nothing here
writes anything.

## Design decisions

**No RBAC matrix row — the same gap M18/M20/M21/M22/M23 already hit.** Section 5's matrix never
mentions Performance History. The only textual anchor is Section 7's Employee screen #8, "My
Performance History": a read-only, cross-cycle view of one employee's own past appraisal outcomes.
Authority for viewing *other* employees' history is inferred by reusing the same role-tiering
logic Dashboards (M24) and Reports (M25) already established, rather than inventing a sixth
version of it.

**A single-record boolean check, not a list-level filter — a genuine departure from M24/M25/M26's
shape.** Every prior "consumption layer" module (`apply_dashboard_scope`, `build_appraisal_status_rows`
via the same helper, `apply_audit_scope`) takes a SQLAlchemy query and narrows it. Performance
History's endpoints are different in kind: `GET /performance-history/{employee_id}` always names
exactly one target employee up front — there is no "list of records this caller can see" to filter,
only "can this caller see *this* employee's history." So `can_view_employee_history()` is written
as a single-record boolean, mirroring the tiering (self / team / department / plant / org) in
spirit, but checked directly against one `Employee` row's `ManagerID`/`HODID`/`PlantID` rather than
joined into a query.

**What "aggregation" means here, and why it hasn't existed until now.** Dashboards aggregates
*counts* across many employees' current records; Reports produces a *roster* of current records,
one row each. Neither drills into a single record's own history. This module pulls together, for
one employee across every cycle they've ever been appraised in: the `Employee_Performance` summary
itself (status, final score, final rating, lock state), the `Performance_Scores` breakdown
(`KPI_WEIGHTED`/`COMPETENCY_WEIGHTED`/`FINAL`, from M18's scoring engine), and the
`Workflow_History` timeline (every stage transition, from M19) — a genuine "how did we get to this
score, and when" view per record, not just a list of past cycle names.

**System Administrator is denied outright — mirrors M25's Reports decision, not M24's Dashboards
system-health carve-out.** Performance History is pure business content (scores, ratings) with no
technical-view equivalent for Sys Admin to be handed instead, consistent with this codebase's
running principle since M2: System Administrator "has no business approval rights."

**`GET /performance-history/me` needs no scope check at all.** It is inherently the caller's own
record — `ctx.employee_id` is used directly, with a 404 only if the acting user has no linked
employee record (e.g. a pure Sys Admin account). `GET /performance-history/{employee_id}` is the
only endpoint that runs `can_view_employee_history()`.

**Route ordering:** `/me` is declared before `/{employee_id}` so it is never shadowed by the
path-parameter route (the same ordering concern flagged in every prior module with a literal path
alongside an `{id}` path).

## Business rules enforced (beyond plain filtering)

| Rule | Where | HTTP result |
|---|---|---|
| System Administrator cannot view anyone's performance history, including their own if linked | `can_view_employee_history` | 403 |
| A caller with no linked employee record gets no self-history | `my_performance_history` | 404 |
| An out-of-scope target employee returns "forbidden," not a filtered-empty list | `employee_performance_history` | 403 |
| A non-existent employee ID is a 404 before any scope check runs | `employee_performance_history` | 404 |
| Manager/HOD/Plant Head scope is checked against the target's own FK fields (`ManagerID`/`HODID`/`PlantID`), not a role-membership query | `can_view_employee_history` | — |

## Setup

```sql
-- after 001-036 from M1-M26
:r sql/037_seed_performance_history_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**304 tests total (290 carried over from M1-M26 + 14 new)**, all passing with zero regressions:
unit tests for every scope branch (`SYS_ADMIN` denial, `HR`/`MD`/`HR_ADMIN` org-wide, `PLANT_HEAD`
same-plant/other-plant, `HOD`/`MANAGER` own-reports/outsider, `EMPLOYEE` self-only) plus
`build_history`'s shape, ordering, score-breakdown grouping and transition grouping in
`test_performance_history_service.py`; **end-to-end ASGI tests**
(`test_performance_history_routes_smoke.py`) covering `/me`, a Manager viewing their own report, an
outsider getting 403, an unknown employee ID getting 404, HR/MD/HR Administrator all succeeding,
and System Administrator getting 403.

Route registration was also verified via `app.openapi()`: **143 total paths** across 32 routers (up
from 141 paths / 31 routers in M26), **169 path+method combinations, zero collisions**.

## What M28 will build on top of this

M28 (System Configuration) is the final module in the build-order table. It covers system-wide
settings — likely things like the AD/LDAP connection parameters, SMTP relay configuration for
M23's currently no-op `send_email_hook()`, file-storage path settings for M22's `storage_root()`,
and other org-wide toggles referenced but never centrally configured across M1-M27 — gated to
System Administrator specifically, closing the loop on the "System Administrator has no business
approval rights, but does have system administration rights" distinction this codebase has drawn
consistently since M2.
