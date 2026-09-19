# M5 (Performance Cycle) + M6 (KPA) + M7 (KPI) + M8 (Scoring Rules) + M9 (Rating) + M10 (Competency) — Setup & Verification

## What's new in this module

```text
app/models/performance_masters.py   PerformanceCycle, KPAMaster, KPIMaster, KPIScoringRule,
                                      RatingMaster, CompetencyMaster
app/services/performance_cycle_service.py  Stage date-sequencing validation (own start<=end,
                                      and each stage's end <= the next stage's start)
app/services/band_validation.py     Shared non-overlap validator for Scoring Rules + Rating bands
app/services/kpa_kpi_service.py     Weightage bounds, effective-date ordering, measurement-type
                                      whitelist, target ordering (Min <= Expected <= Stretch)
app/schemas/performance_cycle.py    Schema + snake_case<->PascalCase field map for the 14 stage-date fields
app/schemas/kpa.py, kpi.py, scoring.py, competency.py
app/api/routes/performance_cycles.py  7 endpoints
app/api/routes/kpa.py                 7 endpoints
app/api/routes/kpi.py                 7 endpoints
app/api/routes/scoring.py             10 endpoints (KPI Scoring Rules + Rating Master)
app/api/routes/competency.py          6 endpoints
sql/006_create_performance_masters.sql   DDL: 6 tables, with SQL Server CHECK constraints for the
                                      per-row rules (weightage 0-100, score 1-5, min<=max) - the
                                      cross-row "bands don't overlap" rule stays app-layer, like
                                      the KPI-weightage-sums-to-100% rule in M11
sql/007_seed_sample_performance_data.sql  Sample cycle/KPAs/KPIs/competencies (tagged SAMPLE-),
                                      PLUS the real default Rating scale and global Scoring Rules
                                      straight from the spec's own worked examples (Sections 12/21)
                                      - these aren't sample data, they're the shipped defaults
                                      HR/Plant Head/MD reconfigure from day one
tests/test_performance_cycle_service.py, test_band_validation.py, test_kpa_kpi_service.py,
tests/test_scoring_rating_integration.py, test_routes_smoke.py (NEW: end-to-end ASGI route tests)
```

No new permission codes were needed: KPA/KPI/Scoring Rules/Rating/Competency all reuse the
generic `MASTERS.VIEW` / `MASTERS.EDIT` / `MASTERS.DEACTIVATE` permissions already seeded in
M3 (`sql/002` + `sql/005`), since the design doc's RBAC matrix groups them under one row with
identical role assignments. Performance Cycle does the same. The audit trail still records a
distinct `Module` per entity (`PERFORMANCE_CYCLE`, `MASTERS.KPA`, `SCORING_RULES`, etc.), so
this simplification only affects *authorization*, not *traceability*.

## Business rules enforced (beyond plain CRUD)

| Master | Rule | Where |
|---|---|---|
| Performance Cycle | Each stage's start <= its own end | `performance_cycle_service.validate_cycle_dates` |
| Performance Cycle | A stage can't start before the previous stage in the mandated sequence ends | same |
| KPA / KPI / Competency | Weightage must be 0-100 | `kpa_kpi_service.validate_weightage` |
| KPA | Effective From <= Effective To | `kpa_kpi_service.validate_effective_dates` |
| KPI | Measurement Type must be one of the 10 spec-listed types | `kpa_kpi_service.validate_measurement_type` |
| KPI | Minimum Target <= Expected Target <= Stretch Target (when supplied) | `kpa_kpi_service.validate_target_ordering` |
| KPI Scoring Rules | Min <= Max, Score in 1-5, no two active bands overlap **within the same KPIID scope** (KPI-specific rules and the KPIID=NULL global set are independent scopes) | `band_validation.py` |
| Rating Master | Min% <= Max%, no two active rating bands overlap | `band_validation.py` |

All of the above are enforced **server-side in the route handlers**, not just as SQL CHECK
constraints or client-side hints — per-row rules (weightage bounds, min<=max, score range) also
got SQL Server CHECK constraints in `006_create_performance_masters.sql` as defense in depth,
but the cross-row rules (band overlap, weightage-across-siblings-sums-to-100% in M11) can't be
expressed as a CHECK constraint and live only in the service layer.

## One real bug caught and fixed during verification

`export_service.build_export_workbook` used `cell.font.copy(bold=True)` to bold the header row —
this is deprecated in the currently-installed openpyxl and raises a `DeprecationWarning` on every
single export call across every master (Company, Plant, KPA, KPI, Scoring Rules, everything).
Fixed by constructing a new `Font(bold=True)` explicitly instead of mutating a copy of the
existing one. Confirmed via `pytest -v`: the warning is gone and all export routes still produce
correctly-bolded headers.

## Setup

```sql
-- after 001-005 from M1-M4
:r sql/006_create_performance_masters.sql
:r sql/007_seed_sample_performance_data.sql
```

`007` seeds the real default Rating scale and global Scoring Rules (not sample data - these ship
in production and are reconfigured, never deleted, via the Scoring Rules / Rating Master screens),
plus a sample cycle/KPAs/KPIs/competencies tagged `SAMPLE-` for testing, matching Section 46.

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

44 tests total (17 carried over from M1-M4 + 27 new): pure validator unit tests for every business
rule above, DB-integration tests that replay the exact query+validate sequence the routes perform
(catching KPIID-scoping mistakes a pure unit test would miss), and **end-to-end ASGI route tests**
(`test_routes_smoke.py`) that drive the actual HTTP routes — create a cycle with bad dates and
confirm a 400, create two overlapping scoring rules for the same KPI and confirm the second gets
a 409, hit every export endpoint and confirm it isn't shadowed by a route registered earlier.

## What M11+ will build on top of this

KPA/KPI Assignment (M11) is where these masters get pulled into an actual employee's appraisal:
`Employee_KPA` and `Employee_KPI` reference `KPA_Master`/`KPI_Master` by ID and copy in a
per-employee weightage that must sum to exactly 100% across the whole assignment — the same
"validate before allowing the status to advance" pattern used here for scoring-rule bands, just
enforced at assignment-submission time instead of at master-creation time.
