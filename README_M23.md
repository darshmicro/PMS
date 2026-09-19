# M23 (Notifications) — Setup & Verification

## What's new in this module

```text
app/models/notification.py           Notification - EmployeeID-scoped, no lock/cycle tie
app/services/notification_service.py  STAGE_RECIPIENT_KIND, STAGE_MESSAGE, send_email_hook,
                                        create_notification, mark_read, resolve_recipients,
                                        notify_stage_transition
app/schemas/notification.py          NotificationOut, UnreadCountOut
app/api/routes/notifications.py      5 endpoints: list, unread-count, mark read, mark all
                                        read, export (no create - see below)
sql/032_create_notification_tables.sql  DDL: Notifications
sql/033_seed_notification_permissions.sql  New NOTIFICATION.VIEW code (no .EDIT)
tests/test_notification_service.py      12 unit tests
tests/test_notification_routes_smoke.py  6 end-to-end ASGI tests

Retrofitted (additive only, one added line each):
app/api/routes/self_assessments.py      2 notify_stage_transition() calls
app/api/routes/manager_reviews.py       2 notify_stage_transition() calls
app/api/routes/hod_reviews.py           2 notify_stage_transition() calls
app/api/routes/hr_reviews.py            1 notify_stage_transition() call
app/api/routes/plant_head_approvals.py  2 notify_stage_transition() calls
app/api/routes/md_approvals.py          2 notify_stage_transition() calls
```

## Design decisions

**No RBAC matrix row exists for this module either - Section 5's matrix never reaches it.** What
Section 7 does give is different from every prior gap (M18/M20/M21/M22): "Notifications panel" is
listed under **Common** screens (#4), not under any one role's section - unlike every other
screen in that list, which is role-scoped. Read literally, that means visibility here isn't
tiered the way every other module's is (self/reports/department/broad-access); it's simply "your
own notifications, and only your own," for every role including HR/Plant Head/MD/HR
Administrator - nobody, however broad their business authority elsewhere, can see into anyone
else's inbox. `NOTIFICATION.VIEW` is therefore granted to all eight roles (including System
Administrator, since the screen is Common), and there is no `NOTIFICATION.EDIT` at all - marking
a notification read is bundled into `NOTIFICATION.VIEW` as part of using your own inbox, not a
separately grantable capability.

**"Stage-based triggers" reuses M19's existing transition signal rather than building a second
one.** The build-order table's own description for this module is "In-app + email, stage-based
triggers." Rather than have every review/approval endpoint independently decide when to notify
whom, this module hooks the exact same call sites M19's Workflow Engine already established for
"a transition just happened" - `record_transition()`, called at 11 sites across the 6
already-shipped review/approval files. Each site gets exactly one additional line,
`notify_stage_transition(db, performance)`, immediately after its existing `record_transition()`
call - the same additive-only retrofit principle M19 itself used and documented (a single added
call, never a rewrite of the surrounding validation/transition logic). All 229 carried-over tests
passed unchanged after this retrofit, the same verification M19 relied on.

**Recipients resolve through existing per-employee FKs first, role membership only where no FK
exists.** The DDL gives `Notifications` a single `EmployeeID`, not a role or broadcast list, so
"who gets notified when a record reaches stage X" has to resolve to concrete employees.
`Employee.ManagerID`/`HODID`/`HRID` (all from M4) cover Manager Review, HOD Review and HR Review
directly - HR falls back to role membership only when the employee has no `HRID` set, since that
field was documented in M4 as optional. Plant Head and MD have no equivalent FK at all (Plant
Head Approval's own ownership check, M16, compares `PlantID` rather than a person), so those two
resolve via role membership instead: every active `User` holding the `PLANT_HEAD` role whose own
`Employee.PlantID` matches the reviewed employee's plant (mirroring M16's own plant-matching
rule), and every active `User` holding the `MD` role org-wide (mirroring MD Approval's own
org-wide scope, M17). A status with no recipient mapping (e.g. `DRAFT`, `KPI_ASSIGNED`) or a stage
whose resolved FK is unset (e.g. no Manager assigned yet) simply produces zero notifications
rather than an error.

**Section 35's "Notification Configuration" admin screen, and SMTP/template settings generally,
are explicitly out of scope here.** The RBAC matrix's own "System Configuration (SMTP, AD server,
storage path)" row (HR Administrator only) places that configuration under System Configuration
(M28), not this module - so M23 fires notifications using whatever SMTP settings `config.py`
already exposes (`SMTP_SERVER`/`SMTP_PORT`/`SMTP_FROM`, declared in M1 like `FILE_STORAGE_PATH`
before it, unused until now), not a configurable template engine of its own.

**Email delivery is a documented no-op hook, the same pattern as Attachment's virus-scan
hook (M22).** No SMTP relay is reachable from this sandboxed environment (its outbound network is
allow-listed to package registries and GitHub only), so `send_email_hook()` is where a real
deployment wires `smtplib` in - every in-app notification is routed through it first, and it
always passes through silently as shipped.

**There is no `POST /notifications` endpoint.** Notifications are exclusively a byproduct of
`notify_stage_transition()` firing at an existing workflow transition; nothing in the spec asks
for ad hoc, manually-authored notifications, so this module doesn't invent that capability.

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| A caller can only ever see/mark-read their own notifications | `_own_query` / `_get_own_notification` | 404 on someone else's |
| A caller with no linked Employee record (e.g. a technical Sys Admin account) sees an empty inbox, not an error | `_own_query` | 200, `[]` |

## Setup

```sql
-- after 001-031 from M1-M22
:r sql/032_create_notification_tables.sql
:r sql/033_seed_notification_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**247 tests total (229 carried over from M1-M22 + 18 new)**, all passing with zero regressions
across the 6 retrofitted files: unit tests for every `STAGE_RECIPIENT_KIND` resolution path
(self, manager, HOD, HR-via-contact, HR-via-role-fallback, Plant Head/MD via role, unmapped
status, missing FK) and the create/mark-read/email-hook helpers (`test_notification_service.py`),
plus **end-to-end ASGI tests** (`test_notification_routes_smoke.py`) proving the retrofit actually
fires - acknowledging a self-assessment notifies the employee, submitting it notifies their
Manager - alongside inbox scoping, mark-read/mark-all-read/unread-count, a 404 on someone else's
notification, the export route, and the no-employee-identity edge case.

Route registration was also verified via `app.openapi()`: **134 total paths** across 28 routers
(up from 129 paths / 27 routers in M22), **160 path+method combinations, zero collisions**.

## What M24+ will build on top of this

M24 (Dashboards) is next. Its own description ("role-specific dashboards, 7 roles") and the RBAC
matrix's "Dashboards" row (`Own`/`Team`/`Dept`/`Org`/`Plant`/`Org`/`Org`/`System health only`)
give it the clearest textual grounding of any module since Workflow Engine - unlike Notifications,
Development Plan or PIP, Dashboards has an explicit matrix row to build against directly, with
`_apply_scope`-style role tiering already spelled out per role rather than needing to be inferred.
