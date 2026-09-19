# Demo-Only Addition: `AUTH_MODE=demo_local` — Setup & Verification

This is not one of the M1-M28 build-order modules — it's a small, isolated addition made
specifically to support running the system on a **Windows 11 Home** machine for a local demo,
where there is no Active Directory domain to join and no IIS Windows-Integrated-Auth/Kerberos
available at all. See `DEPLOY_WINDOWS11_HOME_DEMO.md` for the full setup walkthrough; this document
covers what changed in the codebase and why.

## What's new

```text
app/models/demo_credential.py           DemoCredential (new table: Demo_Login)
app/services/demo_auth_service.py       hash/verify/authenticate/set_password/change_own_password
app/schemas/demo_auth.py                DemoSetPasswordRequest, DemoChangePasswordRequest
app/api/routes/demo_auth.py             2 endpoints: admin set-password, self change-password
app/api/routes/auth.py                  +1 branch in POST /auth/login for AUTH_MODE=demo_local
app/core/config.py                      AUTH_MODE comment updated (still just a string field)
requirements.txt                        +bcrypt==4.0.1 (passlib's bcrypt backend, pinned for compatibility)
sql/demo_only/041_create_demo_login_table.sql        New Demo_Login table (demo-only, not in the 001-039 sequence)
sql/demo_only/042_bootstrap_first_admin_demo_local.sql  One-time bootstrap: demoadmin / Demo@12345
tests/test_demo_auth_service.py           9 unit tests
tests/test_demo_auth_routes_smoke.py      6 end-to-end ASGI tests
```

## Design decisions

**Why a third auth mode instead of stretching `ldap_bind`.** `ad_service.py`'s two existing modes
both ultimately verify an identity *against a real AD server*. Windows 11 Home cannot join a
domain, so there is no AD to point `ldap_bind` at — bending it to "work" without one isn't
possible, and pretending otherwise would be misleading. `demo_local` is a genuinely separate path:
it authenticates directly against a new, app-owned `Demo_Login` table (bcrypt-hashed passwords via
`passlib`, which was already listed in `requirements.txt` since M1 but never used until now).

**Reuses `ad_service.ADAuthError` as its own exception type** — purely so `app/api/routes/auth.py`'s
existing `try/except` around the three modes needs no structural change, not because this has
anything to do with AD. The rest of the login flow (`resolve_user_context`, session cookie
issuance, audit logging, dashboard routing) is completely mode-agnostic and required zero changes.

**The production guard is the single most important design decision here.** `demo_local` provides
none of AD's protections — no account lockout, no centrally enforced password policy, no
deactivation propagation, no Kerberos SSO. Both `POST /auth/login` (in `demo_local` mode) and every
endpoint in `app/api/routes/demo_auth.py` refuse outright (`500`/`400`) whenever
`settings.ENVIRONMENT == "production"`, regardless of what `AUTH_MODE` happens to be set to. This
is enforced in code, not just documentation, specifically so a misconfiguration can't silently
carry this demo-only path into a real deployment.

**`Demo_Login` is a separate table, not a password column bolted onto `Users`.** Keeps the
production schema (`sql/001-039`) completely untouched — a production database that never runs
`sql/demo_only/*.sql` never has this table at all, and the production `Users` table gains no
demo-only column it doesn't need. `UserID` is unique on `Demo_Login`, mirroring how AD-mode users
have exactly zero or one active identity source.

**Two endpoints, matching two real needs**, following the same admin-vs-self-service split already
used elsewhere in this codebase (compare `POST /admin/users` vs. a hypothetical self-service
profile edit): `POST /auth/demo/set-password/{user_id}` (HR_ADMIN/SYS_ADMIN only, no current-password
check — for onboarding a new demo user or resetting a forgotten one) and
`PUT /auth/demo/change-password` (self-service, requires the current password — for the "change
the well-known bootstrap password" step every setup guide should ask for).

**The bootstrap script mirrors `sql/040_bootstrap_first_admin.sql`'s own reasoning exactly** — every
subsequent user/role mapping and demo password is created through the app's own admin endpoints,
which themselves require an existing `HR_ADMIN`/`SYS_ADMIN`. `sql/demo_only/042_...sql` seeds
exactly one account (`demoadmin` / `Demo@12345`, bcrypt-hashed) by hand to break that circularity,
with an explicit instruction to change the password immediately after first login.

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

**335 tests total (321 carried over from M1-M28 + 14 new)**, all passing with zero regressions: unit
tests for hashing/verification, successful and failing authentication, and password set/change in
`test_demo_auth_service.py`; end-to-end ASGI tests in `test_demo_auth_routes_smoke.py` covering a
successful demo login, a rejected wrong password, the `ENVIRONMENT=production` refusal, self-service
password change (old password verified, new one usable immediately), admin-set-password's role
gate, and a successful admin reset.

Route registration verified via `app.openapi()`: **147 total paths** across 29 routers (up from 145
paths / 28 routers before this addition), **175 path+method combinations, zero collisions**.
