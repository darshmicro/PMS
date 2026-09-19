# M24 (Dashboards) — Setup & Verification

## What's new in this module

```text
app/services/dashboard_service.py   apply_dashboard_scope, summarize, system_health
app/schemas/dashboard.py            DashboardSummaryOut, SystemHealthOut
app/api/routes/dashboard.py         2 endpoints: GET /dashboard/summary, GET /dashboard/system-health
sql/034_seed_dashboard_permissions.sql  New DASHBOARD.VIEW code (no new table)
tests/test_dashboard_service.py       10 unit tests
tests/test_dashboard_routes_smoke.py   7 end-to-end ASGI tests
```

No new model or table - this module is a pure read-time aggregation over `Employee_Performance`
(plus `Rating_Master`, `Audit_Log`, `Notifications`, `Users`/`Employees` for the system-health
view). It is also the first module since M17 to have an **explicit RBAC matrix row to build
against** rather than one inferred from screen names and adjacent DDL - Section 5's "Dashboards"
row reads `Own | Team | Dept | Org | Plant | Org | Org | System health only` for
Employee/Manager/HOD/HR/Plant Head/MD/HR Administrator/System Administrator respectively.

## Design decisions

**Plant Head is deliberately split out of `BROAD_ACCESS_ROLES` for this module only.** Every
module since M11 shares one `BROAD_ACCESS_ROLES = {"HR", "HR_ADMIN", "PLANT_HEAD", "MD",
"SYS_ADMIN"}` constant, because every *other* RBAC matrix row gives Plant Head the same org-wide
business-admin rights as HR/MD (spec Section 4's own note, quoted throughout this codebase:
"Plant Head and MD get full business admin rights... except system-level config"). The
Dashboards row is the first place the spec itself narrows that: Plant Head's column reads
"Plant," not "Org" - matching Plant Head Approval's (M16) plant-matching ownership rule rather
than the broader org-wide grouping. `dashboard_service.apply_dashboard_scope()` therefore does
**not** reuse the shared constant; it resolves Plant Head's own `Employee.PlantID` (the same
single-employee lookup M16's `ensure_is_reviewing_plant_head()` already does) and filters to
appraisal records whose subject shares that plant, while HR/MD/HR Administrator stay org-wide.

**System Administrator gets an entirely different dashboard shape, not a narrower business one.**
"System health only" isn't a smaller slice of appraisal data - it's technical/operational data
instead of business data, consistent with this codebase's running principle that Sys Admin "is a
distinct technical role with no business approval rights" (spec Section 3-4, already quoted in
the `Role` model's own docstring since M2). Rather than force Sys Admin through
`DashboardSummaryOut` with every business field null, this module gives it a separate endpoint
(`GET /dashboard/system-health`) and schema (`SystemHealthOut`) that never exposes an individual
score, rating or appraisal comment - only counts (active employees/users, appraisal status
totals, audit log volume, notification volume). Each endpoint rejects the other's caller
in-handler (403, pointing at the correct endpoint) rather than through a second permission code -
`DASHBOARD.VIEW` is the one permission every role holds; which of the two shapes applies to a
given caller is the matrix row itself, not a grant.

**"Pending my action" reuses the transition authority already built in M13-M17, not a new
rule.** `ACTIONABLE_STAGES_BY_ROLE` maps each acting role to the single stage its own
review/approval module lets it act on (Manager -> `MANAGER_REVIEW`, HOD -> `HOD_REVIEW`, and so
on) - the same stage each role's transition endpoint already gates on, just counted rather than
acted on here. HR Administrator has no entry (it holds full View/Export/Masters-admin rights
everywhere but never itself appears as an actor in the six-stage workflow diagram), so its
pending count is always 0 - flagged explicitly since it's easy to assume HR Administrator should
mirror HR's `HR_REVIEW` count and it deliberately does not.

**Overdue counting reuses M19's `compute_sla_status()` directly rather than re-deriving SLA
logic.** A record counts as overdue here under the exact same rule the Workflow Engine already
established (past a stage's End date, per `Performance_Cycles`), applied per in-scope record
that is still mid-workflow (excludes `DRAFT`/`KPI_ASSIGNED`, which have no SLA window yet, and
`FINAL_APPROVED`, which is already done).

**No export endpoint here.** The RBAC matrix keeps "Reports/Exports" as its own separate row
(`Own | Team-scoped | Dept-scoped | Org-scoped | Plant-scoped | Org-scoped | Org-scoped | X`),
distinct from "Dashboards" - so stage-wise Excel exports (spec Section 36A) stay entirely with
M25, and this module stays a live, in-app summary only, matching every export in this codebase
being tied to a specific record/module rather than a dashboard snapshot.

## Business rules enforced (beyond plain aggregation)

| Rule | Where | HTTP result |
|---|---|---|
| System Administrator cannot call the business summary endpoint | `dashboard_summary` | 403 (points to `/dashboard/system-health`) |
| Only System Administrator can call the system-health endpoint | `dashboard_system_health` | 403 (points to `/dashboard/summary`) |

## Setup

```sql
-- after 001-033 from M1-M23
:r sql/034_seed_dashboard_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**264 tests total (247 carried over from M1-M23 + 17 new)**, all passing with zero regressions:
unit tests for every scope tier (Own/Team/Dept/Org/Plant), the status/rating/average/overdue/
pending-action aggregation logic including the HR-Administrator-has-no-actionable-stage case, and
the system-health counts (`test_dashboard_service.py`), plus **end-to-end ASGI tests**
(`test_dashboard_routes_smoke.py`) covering HR's org-wide view, a Plant Head correctly excluding
another plant's record, a Manager's pending-action count, an Employee's own-only view, and the
two endpoints' mutual 403 rejection of each other's caller.

Route registration was also verified via `app.openapi()`: **136 total paths** across 29 routers
(up from 134 paths / 28 routers in M23), **162 path+method combinations, zero collisions**.

## What M25+ will build on top of this

M25 (Reports & Exports) is next - the RBAC matrix's own separate "Reports/Exports" row, and
Section 7's "Reports & Export Center (stage-wise export UI per Sec 36A)" screen. Unlike this
module's live aggregation, M25 is squarely about the stage-wise Excel export convention already
used by every prior module (`build_export_workbook()`), likely centralizing/cataloguing the
per-module exports that already exist (self-assessment, reviews, approvals, attachments, PIP,
development plan, notifications) behind one discoverable "Export Center," per its own row's
Own/Team/Dept/Org/Plant/Org/Org scope - the same tiering this module just implemented, reused
rather than re-derived.
