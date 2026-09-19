# M26 (Audit Trail) — Setup & Verification

## What's new in this module

```text
app/services/audit_log_service.py   apply_audit_scope (SCOPE_DEPT/SCOPE_PLANT/SCOPE_ALL)
app/schemas/audit_log.py            AuditLogEntryOut
app/api/routes/audit_log.py         3 endpoints: list, get, export
sql/036_seed_audit_log_permissions.sql  New AUDIT_LOG.VIEW code (no new table, no .EDIT)
tests/test_audit_log_service.py       6 unit tests
tests/test_audit_log_routes_smoke.py   6 end-to-end ASGI tests
```

No new model or table - `Audit_Log` and its write path (`audit_service.write_audit()`, called by
every mutating endpoint since M1) already exist and are already insert-only at the DB-grant
level. This module is purely the reader that has never existed until now, matching M24/M25's
"consumption layer" pattern: it aggregates/filters what M1-M25 already wrote, and adds no new
write path of its own.

## Design decisions

**This module has an explicit RBAC matrix row, and it reads differently from every other row in
three specific ways worth flagging.** Section 5's "Audit Log" row is
`X | X | X | V(dept) | V(plant) | V(all) | V(all) | V(all, no edit)` for Employee/Manager/HOD/HR/
Plant Head/MD/HR Administrator/System Administrator:

1. **Employee/Manager/HOD get `X` - genuinely nothing, not a self-scoped view.** Every other
   module with a matrix row (Dashboards, Reports) gives every role *some* slice, even if it's just
   "Own." Audit Log is the first row where three roles are simply excluded outright - enforced by
   never granting them `AUDIT_LOG.VIEW` at all, so `require_permission()` turns them away with 403
   before any scope logic runs; there is no in-app filter for them to fall through to.

2. **HR is department-scoped here, not org-wide.** Every other RBAC row gives HR the same
   org-wide `C,V,E` as Plant Head/MD/HR Administrator (spec Section 4: "Plant Head and MD get full
   business admin rights"; HR is written alongside them in every other row). An audit trail is
   more sensitive than the records it describes, so the spec deliberately narrows HR's own reach
   here to their own department - flagged explicitly since assuming HR should see everything the
   way it does everywhere else in this codebase would be a real bug, not a faithful reading of
   this particular row.

3. **MD and HR Administrator both get `V(all)`, matching System Administrator's own
   `V(all, no edit)`** - the three broadest roles in this table - while Plant Head is narrowed to
   `V(plant)`, reusing the same plant-matching rule M16/M24/M25 already established, rather than
   joining MD/HR Administrator's org-wide reach.

**Rows with no `EmployeeID` are excluded from HR's and Plant Head's scoped views, not included by
accident.** `Audit_Log.EmployeeID` is nullable (e.g. a failed login attempt before any employee is
resolved). Such a row has no department or plant to compare against, so a naive `Employee.
DepartmentID == None` filter would incorrectly match *every other* department-less employee's
rows too (an over-broad `IS NULL` join) - `apply_audit_scope()` guards this explicitly with an
always-false filter (`sqlalchemy.false()`) whenever the acting HR/Plant Head has no department/
plant on file themselves, the same "no identity -> empty scope, never an accidental match"
principle Notification's `_own_query` (M23) already established. Org-wide viewers (MD/HR
Administrator/System Administrator) still see these rows exactly as recorded.

**No edit endpoint anywhere - true for every role, not just the ones the matrix says so for.**
The matrix's own note, "V(all, no edit)," is written only against System Administrator, but this
module implements it as a blanket rule: there is no `PUT`/`DELETE` on `Audit_Log` for any role,
matching the DB-grant-level insert-only enforcement already documented on the `Audit_Log` model
itself since M1 (`Audit immutability: Audit_Log insert-only at the DB grant level`).

## Business rules enforced (beyond plain filtering)

| Rule | Where | HTTP result |
|---|---|---|
| Employee/Manager/HOD have no access to the audit trail at all | permission grant (never `AUDIT_LOG.VIEW`) | 403 |
| An acting HR/Plant Head with no department/plant on file sees nothing, not everyone's department-less/plant-less entries | `apply_audit_scope` | 200, `[]` |
| A single entry outside the caller's scope is not found, not forbidden | `get_audit_log_entry` | 404 |

## Setup

```sql
-- after 001-035 from M1-M25
:r sql/036_seed_audit_log_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**290 tests total (278 carried over from M1-M25 + 12 new)**, all passing with zero regressions:
unit tests for every scope tier (dept, plant, org-wide for MD/HR Administrator/System
Administrator, and the no-department/no-plant empty-scope guard) in `test_audit_log_service.py`,
plus **end-to-end ASGI tests** (`test_audit_log_routes_smoke.py`) covering HR seeing only their
own department, MD seeing everything, Employee/Manager/HOD all getting 403, a single-entry lookup
respecting scope (404 on someone else's), filtering by module/employee, and the export route.

Route registration was also verified via `app.openapi()`: **141 total paths** across 31 routers
(up from 138 paths / 30 routers in M25), **167 path+method combinations, zero collisions**.

## What M27+ will build on top of this

M27 (Performance History) is next. Unlike M24-M26 (Dashboards/Reports/Audit Trail, which each
found an explicit RBAC matrix row to build against), Performance History has no row of its own in
Section 5's matrix - the same kind of gap M18/M20/M21/M22/M23 already hit - but Section 7's
Employee screen #8, "My Performance History," gives it a concrete anchor: a read-only view over an
employee's own past `Employee_Performance`/`Performance_Ratings` records across completed cycles,
most likely extending the same self/team/dept/org/plant tiering this module and M24/M25 already
share rather than inventing a sixth version of it.
