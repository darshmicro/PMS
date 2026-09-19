# M3 (Org Masters) + M4 (Employee Master) — Setup & Verification

## What's new in this module

```text
app/models/masters.py          Company, Plant, Department, Section, Designation, Grade, EmployeeCategory
app/models/employee.py         EXTENDED (additive): +Department/Section/Designation/Grade/Plant/
                                 EmployeeCategory FKs, +DateOfJoining, +HRID
app/services/master_service.py Generic Add/Edit/View/Activate/Deactivate/Search, fully audited
app/services/export_service.py Shared Excel builder (header block + freeze/filter/autosize), used by
                                 every master export now and by M25's stage-wise exports later
app/schemas/masters.py         Pydantic schemas for the 7 org masters
app/schemas/employee.py        Pydantic schemas for the Employee Master
app/api/routes/masters.py      36 endpoints: 7 masters x {list, create, update, activate, deactivate, export}
app/api/routes/employees.py    Employee Master CRUD with ROLE-SCOPED visibility (see below)
sql/003_..._extend_employees.sql   DDL: 7 master tables + additive ALTER TABLE on Employees
sql/004_seed_sample_master_data.sql  Sample departments/designations/grades, tagged 'SAMPLE-' (Sec 46)
sql/005_seed_m3_m4_permissions.sql   EMPLOYEE_MASTER.* permissions + full RBAC wiring per the matrix
tests/test_master_service.py       Generic master CRUD lifecycle + audit trail
tests/test_employee_scoping.py     Manager/HOD/broad-role/self-only visibility rules
```

## Employee Master record-level scoping

Unlike the org masters (where `MASTERS.VIEW` either grants access or doesn't), the
Employee Master narrows what you see based on role, enforced in the SQL query itself
(`app/api/routes/employees.py::_apply_scope`), not just hidden in the UI:

| Role | Sees |
|---|---|
| Employee | Self only |
| Manager | Direct reports (`ManagerID = you`) |
| HOD | Department employees (`HODID = you`) |
| HR / Plant Head / MD / HR Admin | Everyone |

Export (`GET /employees/export`) applies the exact same scope — a Manager exporting
gets only their own reports, per spec Section 36A's role-based export scoping.

## ⚠️ Two real bugs caught during verification (both fixed, both worth knowing about)

1. **Route ordering collision.** `GET /employees/{employee_id}` and `GET /employees/export`
   both matched on `/employees/export` at the Starlette routing layer (plain `{employee_id}`
   has no `:int` convertor, so it's string-matched before FastAPI validates the type).
   Because `{employee_id}` was registered first, `/employees/export` was silently
   unreachable (422). Fixed by moving the literal `/export` route before the
   parameterized route — verified with a direct ASGI call. **If you add more
   literal-path routes under a resource that also has a `/{id}` route, register the
   literal path first.**
2. **SQLite PK autoincrement quirk.** `Audit_Log.AuditID` is `BIGINT IDENTITY` in SQL
   Server (correct for a high-volume audit table), but SQLite only auto-increments a
   primary key declared as exactly `INTEGER`. Fixed with
   `BigInteger().with_variant(Integer, "sqlite")` so production keeps `BIGINT` and the
   test suite (which runs against SQLite) still works. This only affects test storage,
   never the SQL Server schema.

## Setup

```sql
-- after 001/002 from M1/M2
:r sql/003_create_org_masters_and_extend_employees.sql
:r sql/004_seed_sample_master_data.sql     -- optional, remove before go-live
:r sql/005_seed_m3_m4_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

17 tests total (9 carried over from M1/M2 + 8 new): master CRUD lifecycle (create,
duplicate rejection, update with audit diff, deactivate with reason, 404 on missing
record) and employee visibility scoping for all four access patterns.

## What M5+ will build on top of this

Performance Cycle, KPA/KPI, Scoring Rules, Rating, and Competency masters (M5–M10)
follow the exact same `master_service.MasterFieldConfig` pattern established here —
new masters are a model + a `MasterFieldConfig` + a thin router, not new CRUD logic.
