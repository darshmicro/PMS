# M21 (PIP Module) — Setup & Verification

## What's new in this module

```text
app/models/pip.py                PIP - EmployeeID-scoped, not tied to one
                                   Employee_Performance record
app/services/pip_service.py      validate_outcome, ensure_open, ensure_can_act,
                                   close_pip, stamp_updated
app/schemas/pip.py               PIPCreate, PIPUpdate, PIPCloseRequest, PIPOut
app/api/routes/pip.py            5 endpoints: list, get, create, edit, close, export
sql/028_create_pip_tables.sql    DDL: PIP, with a CHECK constraint on the
                                   inferred Outcome vocabulary
sql/029_seed_pip_permissions.sql New PIP.VIEW / .EDIT codes
tests/test_pip_service.py         9 unit tests
tests/test_pip_routes_smoke.py    6 end-to-end ASGI tests
```

## Design decisions

**No RBAC matrix row exists for this module - the same kind of gap M18 (`Employee_Competency`)
and M20 (Development Plan) both hit.** Section 5's matrix stops at "Audit Log" and never
mentions PIP. What the spec does give: Section 7's screen list places "18. PIP management list
+ PIP form" squarely under the **HR** section (not Manager's or HOD's), and the table's own
`ManagerID` column names a specific assigned manager for each PIP - read here as the person HR
has assigned to run that particular improvement plan, checked directly against `PIP.ManagerID`
rather than `Employee.ManagerID`'s org-chart line (the schema treats it as its own field, so
this module does too). Reading those together: **creating** a PIP is restricted to HR (plus the
broader business-admin roles that hold equivalent authority elsewhere in this codebase - Plant
Head, MD, HR Administrator); **editing and closing** are open to those same roles on any PIP,
and to the PIP's assigned manager on PIPs assigned to them; the PIP's **subject employee** may
view their own PIP only (a matter this consequential shouldn't be invisible to the person it's
about) and never edit it. `PIP.EDIT` is deliberately shared by both the broad-access roles and
the assigned-manager case (an ownership check happens in-app via `ensure_can_act`), but creation
needed a narrower gate than the permission alone provides, so `create_pip` checks
`_is_broad_access(ctx)` explicitly and returns 403 for a Manager who holds `PIP.EDIT` but isn't
allowed to *open* a new PIP.

**`Outcome`'s one-way lifecycle is the genuine "improvement plan lifecycle" the build-order
table promises - unlike Development Plan's open-ended field editing.** `Outcome` is nullable and
stays `NULL` while a PIP is open. Only a dedicated `POST /pip/{id}/close` action (never a
generic `PUT`) can set it, to one of `SUCCESSFUL` / `UNSUCCESSFUL` / `EXTENDED` - a vocabulary
inferred the same way Development Plan's `CompletionStatus` was (the DDL gives no enum), applied
both as a service-layer validator and a SQL `CHECK` constraint. Once `Outcome` is set,
`ensure_open()` rejects any further `PUT` or `/close` call with `409 Conflict` - the PIP is
closed, permanently, exactly like `Performance_Ratings` (M18) and unlike `Development_Plans`
(M20), which stays editable forever.

**`EmployeeID`-scoped, not `PerformanceID`-scoped - the first transactional module built this
way.** A PIP isn't tied to one appraisal cycle the way every review/approval table and even
Development Plan are; it can be opened whenever an employee's performance needs formal,
sustained improvement, independent of where they sit in a given cycle's workflow. Consequently
`_apply_scope` in `pip.py` filters `PIP` directly - there's no `Employee_Performance` join at
all, unlike every other module's scope helper.

**No stage/lock gate tied to `Employee_Performance.IsLocked`, for the same reason it has no
`PerformanceID`.** A PIP's own lifecycle gate is `Outcome`, entirely independent of any
appraisal cycle's lock state.

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| Outcome must be one of SUCCESSFUL / UNSUCCESSFUL / EXTENDED | `validate_outcome` | 400 |
| A PIP with an Outcome already set cannot be edited or closed again | `ensure_open` | 409 |
| Only HR/HR Admin/Plant Head/MD/SYS_ADMIN may create a new PIP | `create_pip` (in-handler check) | 403 |
| Only broad-access roles or the PIP's assigned manager may edit/close it | `ensure_can_act` | 403 |

## Setup

```sql
-- after 001-027 from M1-M20
:r sql/028_create_pip_tables.sql
:r sql/029_seed_pip_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**209 tests total (194 carried over from M1-M20 + 15 new)**, all passing with zero regressions:
unit tests for the outcome validator, the open/closed guard, and the ownership check
(`test_pip_service.py`), plus **end-to-end ASGI tests** (`test_pip_routes_smoke.py`) covering
the full create/edit/close lifecycle, a closed PIP rejecting further edits and a second close
with 409, only broad-access roles being able to open a new PIP (a Manager holding `PIP.EDIT`
gets 403), the assigned manager being able to edit/close their own PIPs but not one assigned to
someone else, the subject employee being able to view but not edit their own PIP, and an invalid
outcome being rejected on close.

Route registration was also verified via `app.openapi()`: **125 total paths** across 26 routers
(up from 121 paths / 25 routers in M20), **150 path+method combinations, zero collisions**.

## What M22+ will build on top of this

M22 (Attachments/Evidence) is next. Its DDL will need to answer whether it attaches to a single
`PerformanceID` (like every review/approval stage), to the newer `EmployeeID`-scoped tables this
module and Development Plan introduced, or both - the spec's screen list mentions evidence
uploads at multiple stages (self-assessment achievements, PIP action plans), so the attachment
table will likely need a polymorphic or dual-FK design rather than a single fixed parent column,
which none of M1-M21's tables have needed so far.
