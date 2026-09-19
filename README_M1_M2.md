# M1 (AD Auth) + M2 (RBAC / User Management) — Setup & Verification

## What's in this module

```text
app/core/config.py          Environment-driven settings (never hard-coded)
app/core/session.py         Signed session cookie (identity only, no cached permissions)
app/core/dependencies.py    get_current_context, require_permission, require_any_role
app/db/base.py              Lazy SQLAlchemy engine/session (SQL Server in prod, swappable in tests)
app/models/employee.py      Minimal Employee (extended with org FKs in M3/M4)
app/models/rbac.py          Role, Permission, RolePermission, User, UserRole
app/models/audit.py         AuditLog (insert-only)
app/services/ad_service.py  AD integration: iis_forwarded (prod) + ldap_bind (dev/test) modes
app/services/auth_service.py  Maps verified AD identity -> Employee -> Roles -> dashboard route
app/services/audit_service.py Shared audit-write helper used by every module
app/api/routes/auth.py      POST /auth/login, POST /auth/logout, GET /auth/me
app/api/routes/users.py     Admin AD-username <-> Employee <-> Role mapping screen backend
app/api/routes/roles.py     Admin role/permission management backend
sql/001_..._tables.sql      DDL: Employees (minimal), Roles, Permissions, Role_Permissions,
                             Users, User_Roles, Audit_Log + least-privilege grant template
sql/002_..._permissions.sql Seed: 8 roles + initial permission set matching the RBAC matrix
tests/                      Unit tests against in-memory SQLite (no AD/SQL Server needed)
```

## 1. Choose your AD integration mode

- **`AUTH_MODE=iis_forwarded`** (recommended for the production intranet deployment):
  IIS sits in front of this app with Windows Authentication + Kerberos enabled for the
  intranet zone, and an IIS URL Rewrite/ARR rule forwards the authenticated Windows
  identity to the app as an HTTP header (default `X-Remote-User`). The app never
  receives or handles a password in this mode.
- **`AUTH_MODE=ldap_bind`** (dev/testing, or LAN segments not fronted by IIS): the
  `/auth/login` endpoint accepts `DOMAIN\username` + password and validates them
  directly against AD over LDAPS. The password is used only for the LDAP bind call
  and is never stored or logged.

Set this in `.env` (copy from `.env.example`).

## 2. Create the database objects

```sql
-- against PMS_DB
:r sql/001_create_auth_rbac_tables.sql
:r sql/002_seed_roles_and_permissions.sql
```

Then, following the commented-out block at the bottom of `001_...`, create the
`svc_pms_app` SQL login with `db_datareader` + `db_datawriter`, and explicitly
`DENY UPDATE, DELETE` on `Audit_Log` so no code path can alter history.

## 3. Map your first System Administrator

Before the admin UI exists to bootstrap itself, insert the first mapping directly:

```sql
INSERT INTO Employees (EmployeeCode, ADUsername, FullName, Email, EmploymentStatus, IsActive)
VALUES ('EMP00001', 'COMPANY\svcadmin', 'Initial Administrator', 'admin@company.local', 'ACTIVE', 1);

INSERT INTO Users (ADUsername, EmployeeID, IsActive)
VALUES ('COMPANY\svcadmin', SCOPE_IDENTITY(), 1);

INSERT INTO User_Roles (UserID, RoleID)
SELECT u.UserID, r.RoleID FROM Users u, Roles r
WHERE u.ADUsername = 'COMPANY\svcadmin' AND r.RoleCode = 'SYS_ADMIN';
```

From here, that account uses `POST /admin/users` and `PUT /admin/roles/{id}/permissions`
to onboard everyone else — no more direct SQL needed.

## 4. Install and run

```bash
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env           # then edit with real values
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verify: `GET http://127.0.0.1:8000/health` → `{"status": "ok", ...}`

## 5. Run the test suite

Tests use an in-memory SQLite DB and never touch AD or SQL Server:

```bash
pip install pytest
pytest tests/ -v
```

Covers (per spec Section 47's Authentication test list): valid AD user with active
employee + role resolves correctly; unmapped AD username rejected; deactivated user
account rejected; inactive employee rejected even if the user account is active;
user with no active role rejected; dashboard routing by highest-privilege role;
permission resolution from role assignment.

## 6. What M3/M4 will add on top of this

`Employees` currently has only the columns M1/M2 need. M3 (Org Masters) creates
Departments/Plants/Sections/Designations/Grades; M4 (Employee Master) then runs an
additive migration adding `DepartmentID`, `SectionID`, `DesignationID`, `GradeID`,
`PlantID` foreign keys to `Employees` and extends the admin screen accordingly — no
existing column is renamed or removed, so this module's code keeps working unchanged.
