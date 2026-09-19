# M19 (Workflow Engine) — Setup & Verification

## What's new in this module

```text
app/models/workflow_history.py          WorkflowHistory - dedicated, insert-only per-record
                                          transition log (distinct from Audit_Log)
app/services/workflow_engine_service.py STAGE_WINDOWS/ensure_within_stage_window,
                                          WORKFLOW_GRAPH/get_next_stages,
                                          compute_sla_status, record_transition
app/schemas/workflow_engine.py          WorkflowHistoryEntryOut, WorkflowStatusOut
app/api/routes/workflow_engine.py       1 read-only endpoint: current status + SLA + history
sql/024_create_workflow_engine_tables.sql   DDL: Workflow_History
sql/025_seed_workflow_engine_permissions.sql  New WORKFLOW_ENGINE.VIEW code (no .EDIT)
tests/test_workflow_engine_service.py       12 unit tests
tests/test_workflow_engine_routes_smoke.py  2 end-to-end ASGI tests

MODIFIED (retrofit, additive only - see design decisions):
  app/services/self_assessment_service.py, manager_review_service.py, hod_review_service.py,
  hr_review_service.py, plant_head_approval_service.py, md_approval_service.py
    -> each ensure_stage_editable() now also calls ensure_within_stage_window()
  app/api/routes/self_assessments.py, manager_reviews.py, hod_reviews.py, hr_reviews.py,
  plant_head_approvals.py, md_approvals.py
    -> each of the 10 existing stage-transition call sites now also calls record_transition()
  tests/test_md_approval_routes_smoke.py's fixture gained a RatingMaster row (M18-related,
    already fixed when M18 shipped - noted here only because this module's own tests touch
    the same fixture pattern)
```

## Design decisions

**The stage-window gate isn't new scope invented for this module - it's a promise this
codebase already made itself.** `PerformanceCycle`'s own docstring, written back in M5, reads:
*"The workflow engine (M19) reads these dates to gate which stage is currently open - they are
not just informational."* Every stage since M12 has had a `StageStart`/`StageEnd` pair sitting
on `Performance_Cycles`, entirely unused until now. `ensure_within_stage_window()` makes good
on that promise: called from inside every module's own `ensure_stage_editable()`, right after
the existing status/lock checks, so nothing about *where* a stage's window is enforced needed
to change - only that it now actually happens.

**Only the Start date is a hard gate; the End date deliberately is not.** Acting before a
stage has opened is refused outright (409) - the data an earlier stage depends on may not
even exist yet (e.g. Manager Review shouldn't be actionable before its own window opens, per
this module's own smoke test). Acting *after* a stage's End date is different: this codebase's
spec references an audited "reopen" workflow event for after-the-fact corrections (the same
Section 4/32 citation used in M17/M18's READMEs) - but that section doesn't actually exist
anywhere in the design document as delivered (its Section 4 is "SQL Table Structure," and
there is no Section 32 at all; the document tops out at Section 10). Since no reopen path has
ever been built, hard-blocking action after End would strand a late record with **no forward
path whatsoever** - clearly worse than allowing a late completion. So lateness is surfaced as
data instead: `compute_sla_status()` reports `is_overdue`/`days_overdue` for the workflow
status endpoint (and, later, M23's Notifications/escalation) to act on, never as a silent or
hard block. A window with either bound left `NULL` is never gated at all - the columns are
nullable, and an administrator who hasn't configured them yet shouldn't accidentally freeze
every record sitting in that stage.

**`Workflow_History` is a genuinely separate table from `Audit_Log`, not a duplicate of it.**
Every transition endpoint since M12 already calls `write_audit(action="WORKFLOW_TRANSITION",
...)` - so why a second table for what looks like the same event? Because they serve different
readers: `Audit_Log` is the "everything, by anyone, anywhere" compliance trail spec Section 32
describes (insert-only, all action types, all modules). `Workflow_History` is scoped to one
thing - one record's stage journey - and is the natural data source for a single ordered
timeline view of a single appraisal, which `Audit_Log` alone would require filtering/joining
to reconstruct. Both get written at every transition, from the same call site, because they
answer different questions.

**The retrofit into 6 already-shipped modules is additive-only, not a rewrite.** M19's remit
("stage sequencing, SLA, escalation, return-routing") could be read as license to centralize
and rewrite the transition logic M13-M17 already built - each has its own working, tested
`ensure_stage_editable()`/transition-endpoint pattern. That rewrite was deliberately avoided:
real regression risk for six shipped, tested modules, for a refactor the user hasn't asked
for. Instead, every change to existing files is a single added line at an existing call site
(`ensure_within_stage_window(performance)` at the end of `ensure_stage_editable()`;
`record_transition(...)` next to the existing `write_audit(...)` call) - nothing about any
existing validation, RBAC check, or transition target changed. `WORKFLOW_GRAPH`/
`get_next_stages()` documents the whole graph in one declarative place (matching exactly what
the six modules already implement, edge for edge) for the read-only status endpoint and for
later modules (Dashboards/M24, Notifications/M23) to query, rather than becoming a second,
competing source of truth those modules would have to be kept in sync with.

**No `WORKFLOW_ENGINE.EDIT`.** Like Scoring Engine (M18), this module has no manual write
path - `Workflow_History` rows are only ever produced as a side effect of a real transition
happening through its owning module's own endpoint. `WORKFLOW_ENGINE.VIEW` follows the exact
same broad grant and self/reports/dept/broad-access scoping as `ASSIGNMENT.VIEW` (M11) and
`SCORING_ENGINE.VIEW` (M18) - seeing a record's workflow status is the same visibility
question as seeing the record itself.

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| A stage cannot be acted on before its cycle window opens (when configured) | `ensure_within_stage_window` | 409 |
| A stage's window closing does NOT block action - surfaced as `is_overdue` instead | `compute_sla_status` | - (data only) |
| Every stage transition writes a `Workflow_History` row alongside its `Audit_Log` entry | `record_transition`, called from 10 existing endpoints | - |

## Setup

```sql
-- after 001-023 from M1-M18
:r sql/024_create_workflow_engine_tables.sql
:r sql/025_seed_workflow_engine_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**188 tests total (174 carried over from M1-M18 + 14 new)**, all passing with zero
regressions: pure unit tests for the stage graph, the window gate (before/within/after, no
window configured, status with no window mapping), SLA computation, and `record_transition`
(`test_workflow_engine_service.py`), plus **end-to-end ASGI tests**
(`test_workflow_engine_routes_smoke.py`) proving the gate actually blocks a real endpoint
(`/manager-reviews/{id}/submit`, called 30 days before its cycle's `ManagerReviewStart`) and
that a real transition through `/hod-reviews/{id}/approve` shows up in
`/workflow-engine/{id}/status`'s history. All 174 carried-over tests still pass unchanged,
confirming the six-module retrofit is genuinely additive - no existing test needed to change
its expectations (the six modules' own seeded `PerformanceCycle` fixtures never set stage
dates, so the new gate is a no-op for them, exactly as designed for "not yet configured"
windows).

Route registration was also verified via `app.openapi()`: **118 total paths** across 24
routers, zero path collisions.

## What M20+ will build on top of this

M20 (Development Plan, per the build-order table: "Skill gap, training, target dates") is next
- its own DDL (`Development_Plans`) was already visible alongside `Workflow_History` in the
same section of the design doc, and unlike this module's dependency chain, it looks
self-contained (one row per `Employee_Performance`, no upstream score/approval prerequisite to
guard). Separately, this module's own README should be read together with M18's: the
`Employee_Competency` gap flagged there is still open, and the "Section 4/32 reopen workflow
event" this module found does not actually exist in the delivered design document - if a real
correction/reopen path is wanted, it needs its own deliberate design, not an assumption
carried forward from a citation that doesn't resolve to real content.
