# M18 (Scoring Engine) — Setup & Verification

## What's new in this module

```text
app/models/employee_competency.py       EmployeeCompetency - a table the ERD/DDL always had
                                          but no prior module (M1-M17) ever created
app/models/performance_score.py         PerformanceScore, PerformanceRating
app/services/scoring_engine_service.py  compute_kpi_weighted_pct, compute_competency_weighted_pct,
                                          get_final_score, lookup_rating_band, run_scoring_engine
app/schemas/scoring_engine.py           PerformanceScoreOut, PerformanceRatingOut
app/api/routes/scoring_engine.py        2 read-only endpoints: get result, stage-wise export
app/api/routes/md_approvals.py          MODIFIED: /approve now calls run_scoring_engine()
                                          right after finalize_and_lock(), in the same transaction
sql/022_create_scoring_engine_tables.sql   DDL: Employee_Competency, Performance_Scores,
                                          Performance_Ratings
sql/023_seed_scoring_engine_permissions.sql  New SCORING_ENGINE.VIEW code (no .EDIT - see below)
tests/test_scoring_engine_service.py       16 unit tests for every computation/validator
tests/test_scoring_engine_routes_smoke.py  2 end-to-end ASGI tests (through the real MD-approve hook)
```

Also touched: `tests/test_md_approval_routes_smoke.py` now seeds a `RatingMaster` band, because
approving at MD Approval genuinely depends on one existing from this module onward (see below).

## Design decisions

**"Final Score %" is HRReview.HRScore, not a fresh Section 8.4 recomputation.** The spec's
literal formula is `KPI component % + Competency component % (+ calibration adjustment)`. But
this codebase's own review chain never computes that sum directly: M14 gave HOD Review a
single aggregate `HODScore` column (the DDL only offers one), independently entered by the
HOD and only checked against the KPI-weighted figure as a reference - diverging is allowed
with comments, never overridden by the reference. M15 then derived `HRReview.HRScore` as
`HODScore + CalibrationAdjustment`. That whole-record score - not an independent recomputation
- is what's actually been reviewed, calibrated and approved by the time MD signs off. So the
`FINAL` figure this module records, copies to `Employee_Performance.FinalScorePct`, and uses
for rating derivation, is `HRReview.HRScore` itself. `KPI_WEIGHTED` and `COMPETENCY_WEIGHTED`
are still computed and stored in `Performance_Scores` (Section 8.2/8.3's literal figures, for
audit/traceability of how the appraisal was scored), but they are not summed to produce
`FINAL` - continuing the exact "concrete schema over narrative formula" resolution established
in M14 and reused in M15, now extended to explain how it reconciles with Section 8.4's text.

**`Employee_Competency` didn't exist, and this module builds only the minimum of it.** The
ERD/DDL has always included this table (`Employee_Performance` -> `Employee_Competency` <-
`Competency_Master`), and Section 8.3's formula needs it - but no module in the M1-M17 build
sequence ever created it: M10 (Competency Master) only built the org-wide competency list,
and M11 (KPA/KPI Assignment) is scoped to exactly what its name says. This is a genuine gap in
the module build-order table, not a decision made anywhere else. Rather than either (a)
blocking the Scoring Engine on a workflow that was never designed, or (b) inventing an
assignment/scoring workflow (who assigns competencies, at what stage, with what RBAC row) that
the user hasn't asked for and might design differently, this module takes the narrowest path:
it creates the table (so the formula is computable at all) and reads whatever rows already
exist, but exposes no create/edit endpoint of its own. A record with zero assigned
competencies gets a Competency component of exactly `0.0` - a legitimate "this org isn't using
competency scoring yet" state - while a record with an assigned-but-unscored competency blocks
finalization with a 400 (incomplete data is not a valid zero). **This is flagged here
explicitly**: populating `Employee_Competency` needs its own module/decision before competency
scoring will ever contribute anything but zero in practice.

**The engine runs exactly once, automatically, from inside MD Approval's own `/approve`.**
Section 8.5 says rating derivation happens "only at the `FINAL_APPROVED` transition" - and
that transition has exactly one entry point in this codebase: `md_approvals.py`'s
`approve_and_finalize()` (M17). M17's own README flagged this as the expected hook, so this
module wires into it directly (`run_scoring_engine(db, performance, ctx.user_id)`, called
right after `finalize_and_lock()`, in the same transaction, before `db.commit()`) rather than
adding a separate manual "compute now" endpoint. A consequence worth calling out: **approving
a record at MD Approval now genuinely depends on a Rating Master band covering its score** - if
none does, `run_scoring_engine` raises a 409 and the whole approval (including the lock) rolls
back, since nothing was committed yet. `test_md_approval_routes_smoke.py`'s fixture needed a
`RatingMaster` row added for exactly this reason once this module's tests exposed it.

**No `SCORING_ENGINE.EDIT` - this module has no manual write path at all.** Every other module
that produces a workflow-relevant number has an edit endpoint gated by role. This one doesn't:
the whole point of running the engine automatically and exactly once, immutably, is that
nobody edits a Final Score/Rating directly - a wrong result gets fixed by the eventual audited
"reopen" workflow event spec Section 4/32 describes, never by a PUT here. `SCORING_ENGINE.VIEW`
is the only permission code this module adds, granted to the same broad set of roles
`ASSIGNMENT.VIEW` (M11) already covers, with the identical self/reports/dept/broad-access
scoping (`scoring_engine.py`'s `_apply_scope` is a direct copy of `assignments.py`'s) - seeing
a record's final score is a natural extension of the same visibility every earlier stage of
that same record already has.

**Idempotent by construction, not just by the workflow's own locking.** `MD_Approval`'s
`ensure_stage_editable()`/`IsLocked` guard already prevents a second `/approve` call from ever
reaching this module in the normal workflow. `run_scoring_engine()` adds a defense-in-depth
check anyway: if a `Performance_Ratings` row already exists for a `PerformanceID`, it's
returned as-is rather than re-inserted - consistent with Section 8.5's "immutable once
inserted" rule, enforced at the service layer (and backed by a `UniqueConstraint` at the DB
level) rather than trusting the workflow guard alone.

## Business rules enforced (beyond plain CRUD)

| Rule | Where | HTTP result |
|---|---|---|
| The KPI-weighted figure requires every assigned KPI to have a manager score (else recorded as absent, not partial) | `compute_kpi_weighted_pct` | - (returns `None`, simply omitted from `Performance_Scores`) |
| An assigned-but-unscored competency blocks finalization | `compute_competency_weighted_pct` | 400 |
| A completed HR Review score must exist to finalize at all | `get_final_score` | 409 |
| The final score must fall within an active Rating Master band | `lookup_rating_band` | 409 |
| A `Performance_Ratings` row is never inserted twice for the same record | `run_scoring_engine` | - (idempotent no-op) |

`Employee_Competency.Score` and `Performance_Scores.ScoreType` also got SQL Server `CHECK`
constraints (`022_create_scoring_engine_tables.sql`) as defense in depth.

## Setup

```sql
-- after 001-021 from M1-M17
:r sql/022_create_scoring_engine_tables.sql
:r sql/023_seed_scoring_engine_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**174 tests total (160 carried over from M1-M17 + 14 new)**, all passing with zero
regressions: pure computation/validator unit tests for every rule above
(`test_scoring_engine_service.py`, including the KPI/Competency weighted-percentage math,
the assigned-but-unscored guard, the missing-HR-score guard, rating-band lookup including
inactive bands being ignored, and idempotency), plus **end-to-end ASGI tests**
(`test_scoring_engine_routes_smoke.py`) that exercise the *real* integration path - approving
a fully-seeded record at `/md-approvals/{id}/approve` and then confirming the computed
`Performance_Scores`/`Performance_Ratings` are visible at `/scoring-engine/{id}` - plus a test
confirming a missing Rating Master band fails the approval with a 409 and leaves the record
unlocked and un-transitioned (the whole-transaction rollback behavior).

Route registration was also verified via `app.openapi()`: **117 total paths** across 23
routers, zero path collisions.

## What M19+ will build on top of this

M19 (Workflow Engine, per the build-order table: "Stage sequencing, SLA, escalation,
return-routing") is the natural next module - it's the first one explicitly positioned to
generalize the return-routing and stage-transition logic that's so far been duplicated,
module by module, across M13-M18 (`ensure_stage_editable`, `_do_return`-style helpers, the
`old_status`/`new_status` audit pattern). It's also a candidate to own SLA/escalation timers,
which nothing built so far tracks at all. Separately, the `Employee_Competency` gap flagged
above remains open: some future module (a revision to M11's scope, or a dedicated one) needs
to decide who assigns competencies to a record and when they're scored, or competency scoring
will stay permanently at 0% in any real deployment of this system.
