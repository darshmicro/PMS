# M28 (System Configuration) — Setup & Verification

## What's new in this module

```text
app/models/system_config.py             SystemConfig (new table)
app/services/system_config_service.py   NON_SECRET_KEYS allowlist, validate_key, upsert_config
app/schemas/system_config.py            SystemConfigOut, SystemConfigUpsertIn
app/api/routes/system_config.py         4 endpoints: list, get, create, update
sql/038_create_system_config_tables.sql New System_Config table
sql/039_seed_system_config_permissions.sql  New SYSTEM_CONFIG.VIEW/.EDIT codes
tests/test_system_config_service.py       11 unit tests
tests/test_system_config_routes_smoke.py  7 end-to-end ASGI tests
```

**This is the last module in the build-order table (Section 2).** The PMS build sequence M1-M28
is now complete.

## Design decisions

**The narrowest row in the entire RBAC matrix.** Section 5's last row — "System Configuration
(SMTP, AD server, storage path)" — is `X` for all seven business roles (Employee through HR
Administrator, including MD and HR Administrator, who otherwise get near-org-wide reach
everywhere else in this codebase) and `C,V,E` for System Administrator alone. This is the mirror
image of the principle repeated since M2 ("System Administrator has no business approval
rights"): no business role, however senior, has system-configuration rights either. Every route in
this module is gated by `require_any_role("SYS_ADMIN")` rather than a permission code shared with
any other role.

**The central design tension: the matrix names real secrets, but the spec's own Section 33/42
principle forbids storing them in the database.** Taken literally, "SMTP, AD server, storage path"
could be read as "make every `Settings` field in `app/core/config.py` editable from a DB-backed
admin screen" — which would include `DB_PASSWORD`, `AD_BIND_PASSWORD` and `SESSION_SECRET_KEY`.
That directly contradicts the principle already documented on `config.py` itself since M1: "All
environment-specific values (DB, AD, secrets) come from environment variables / .env - never
hard-coded." Storing credentials in a table any System Administrator with database access can read
in plaintext would be a real security regression, not a faithful reading of the matrix row.

Resolved by scoping `System_Config` to exactly the **non-secret** subset the row names by example:
`SMTP_SERVER`, `SMTP_PORT`, `SMTP_FROM`, `AD_SERVER`, `AD_DOMAIN`, `FILE_STORAGE_PATH`,
`MAX_UPLOAD_SIZE_MB` — connection parameters and operational settings, not credentials. This is
enforced two ways, not just documented: `NON_SECRET_KEYS` is a strict allowlist (an unrecognised
key is rejected, not silently accepted), and `is_secret_like()` additionally pattern-matches
`PASSWORD`/`SECRET`/`TOKEN`/`BIND_DN`/`API_KEY` as defence in depth, so even a key that could later
be added to the allowlist by mistake is still caught. `DB_SERVER`, `DB_NAME`, `DB_USER` are also
left out deliberately — the matrix names only SMTP/AD/storage, and changing the database connection
itself from a running app talking to that same database is a bootstrapping problem this module
does not attempt to solve.

**Key/value rows, not one column per setting.** `System_Config` has `ConfigKey`/`ConfigValue`
rather than a fixed-column schema, so a new non-secret setting can be added to `NON_SECRET_KEYS`
and used immediately without a migration — the same "extensibility over rigid schema" preference
already used for `Attachment`'s dual-nullable-FK design (M22).

**An empty table is the correct starting state, not a bug.** No default rows are seeded by
`039_seed_system_config_permissions.sql` or the DDL script. Every operational setting falls back to
its environment-variable default (`app/core/config.py`'s `Settings` class) until a System
Administrator explicitly creates an override row through this screen — consistent with "never
hard-coded," and avoiding a DB row silently shadowing an intentional env-var change during a future
deployment.

**Every write is audited**, via the same `write_audit()` every other module's mutating endpoints
call (Section 32) — arguably more warranted here than almost anywhere else in the system, given
what this screen controls.

**POST for create / PUT for edit, not a single upsert endpoint** — matches the convention already
established by `app/api/routes/users.py`'s admin-mapping screen (the other narrowly-scoped admin
surface in this codebase) rather than inventing a new REST shape for this one module: `POST
/system-config/{config_key}` 409s if the key already exists, `PUT /system-config/{config_key}` 404s
if it doesn't.

## Business rules enforced (beyond plain filtering)

| Rule | Where | HTTP result |
|---|---|---|
| Every role except System Administrator is refused, on every endpoint | `require_any_role("SYS_ADMIN")` | 403 |
| A key that looks like a credential (`PASSWORD`, `SECRET`, `TOKEN`, `BIND_DN`, `API_KEY`) is never stored, even by System Administrator | `system_config_service.validate_key` | 400 |
| A key outside the non-secret allowlist is rejected, not silently created | `system_config_service.validate_key` | 400 |
| Creating a key that already exists fails instead of silently overwriting it | `create_system_config` | 409 |
| Editing a key that doesn't exist fails instead of silently creating it | `update_system_config` | 404 |

## Setup

```sql
-- after 001-037 from M1-M27
:r sql/038_create_system_config_tables.sql
:r sql/039_seed_system_config_permissions.sql
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**321 tests total (304 carried over from M1-M27 + 17 new)**, all passing with zero regressions:
unit tests for the allowlist/secret-pattern rejection logic and upsert create-then-update behaviour
in `test_system_config_service.py`, plus **end-to-end ASGI tests**
(`test_system_config_routes_smoke.py`) covering create → list → get, duplicate-create conflict,
update-missing-key 404, update-existing-key, secret-like-key rejection, every non-SYS_ADMIN role
getting 403, and get-missing-key 404.

Route registration was also verified via `app.openapi()`: **145 total paths** across 28 routers (up
from 143 paths / 27 routers in M27), **173 path+method combinations, zero collisions**.

## Project status: M1-M28 complete

Every module in the Section 2 build-order table has now been built to the same standard: real
SQLAlchemy models, service-layer validation, FastAPI routes, SQL DDL/permission scripts, unit and
end-to-end ASGI tests, and a per-module README documenting design decisions and spec-gap
resolutions. The full test suite stands at 321 tests across 28 routers and 145 API paths, with zero
route collisions and zero regressions carried across all 28 modules.

Two categories of intentionally-deferred work remain outside this build's scope, both flagged
in-place rather than silently stubbed:
- **Real AD/LDAP bind and real SMTP delivery** — `AuthenticationBackend`'s AD bind (M1) and
  `notification_service.send_email_hook()` (M23) are both fully wired no-ops, documented as the
  exact point a future integration plugs into, since this sandbox has no AD server or SMTP relay
  reachable to test against.
- **Real virus-scanning of uploaded attachments** — `attachment_service.virus_scan_hook()` (M22) is
  the equivalent no-op wiring point for a future AV engine integration.

All three hook points are exercised by their modules' own tests as no-ops, and are the natural
starting points for a production hardening pass once this system is deployed against real AD/SMTP/
AV infrastructure.
