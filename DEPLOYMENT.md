# PMS — Installation, Configuration & Production Deployment Guide

This covers the complete Performance Management System (M1-M28): a FastAPI/SQLAlchemy backend
served over SQL Server, intended to run on your intranet behind IIS with Windows/AD
authentication. It assumes a Windows Server target (the spec's stated production environment);
notes for a Linux/reverse-proxy alternative are called out where they differ.

---

## 1. Architecture recap

```
Browser (intranet) --HTTPS--> IIS (Windows Integrated Auth, TLS termination)
                                  |  HttpPlatformHandler reverse-proxies to
                                  v
                        uvicorn (FastAPI app, 127.0.0.1:<dynamic port>)
                                  |
                                  v
                        SQL Server (PMS_DB) <--windows or sql auth-->
                                  |
                        File storage path (attachments) + SMTP relay (notifications)
```

IIS does the authentication (Windows Integrated Auth against AD) and TLS; the Python app trusts
the identity IIS forwards and never talks to AD directly in the default configuration
(`AUTH_MODE=iis_forwarded`). Everything else — RBAC, workflow, scoring, audit — runs inside the
app against SQL Server.

---

## 2. Prerequisites

| Component | Version / notes |
|---|---|
| OS | Windows Server 2019+ (IIS 10+), joined to the company AD domain |
| IIS | Web Server role + **URL Rewrite** + **HttpPlatformHandler** modules installed |
| SQL Server | 2017+ (on this server or reachable over the network); a database named e.g. `PMS_DB` already created, with a login the app can use |
| Python | 3.11+ installed on the app server (or bundled as a venv you deploy — see step 4) |
| ODBC Driver | **ODBC Driver 18 for SQL Server** installed on the app server (`DB_DRIVER` in `.env` must match exactly) |
| Service account | A low-privilege AD account or SQL login for the app pool / DB connection — never a domain admin |
| Network | App server can reach SQL Server (1433) and, if used, the SMTP relay and AD/LDAP (636/389) |

---

## 3. Get the application onto the server

1. Extract the delivered `pms_app_M1_M28.zip` to the target path, e.g. `D:\PMS\pms_app`.
2. Everything under `app/` is the application; `sql/` holds every migration in run order;
   `tests/` and the per-module `README_M*.md` files are development artifacts you can leave in
   place or remove — they are not imported by the running app.

---

## 4. Python environment

```powershell
cd D:\PMS\pms_app
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

`pyodbc` requires the ODBC Driver installed in step 2's prerequisites — `pip install` alone does
not install the driver itself.

---

## 5. Configure `.env`

Copy the template and fill in every value for this environment:

```powershell
copy .env.example .env
notepad .env
```

Key decisions to make here (see the inline comments in `.env.example` for the full field list):

- **`SESSION_SECRET_KEY`** — generate a fresh one per environment, never reuse the one from dev/UAT:
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`. This signs the session cookie
  (`app/core/session.py`) — treat it like any other credential.
- **`DB_AUTH_MODE`** — `windows` lets the app pool's own Windows identity authenticate to SQL
  Server (no password in `.env` at all — the cleanest option if your app pool identity has a SQL
  login); `sql` uses `DB_USER`/`DB_PASSWORD` (a SQL login) if Windows auth isn't available.
- **`AUTH_MODE`** — `iis_forwarded` (default) for production behind IIS, AD users only.
  `ldap_bind` is for running/testing the app without IIS in front of it — the app itself binds to
  AD with a username/password submitted to `POST /auth/login`, AD users only. **`hybrid`** serves
  AD users and a handful of local (non-AD) accounts from the same login screen, and is permitted in
  production — see §9a below if you need that. `demo_local` is local-accounts-only and is refused
  outright whenever `ENVIRONMENT=production`; use `hybrid` instead for any real deployment that
  needs local accounts.
- **`FILE_STORAGE_PATH`** — an absolute path the app pool identity can write to. Point it at a
  path with real backups (see §14), not a scratch/temp drive.
- **`SMTP_SERVER`/`SMTP_PORT`/`SMTP_FROM`** — your internal relay. (Note: as shipped,
  `notification_service.send_email_hook()` is a documented no-op — see §16 if you want to wire
  real SMTP delivery; in-app notifications work regardless.)
- **Never** put `.env` under version control or copy it into `web.config` (see `deploy/web.config`'s
  own comment on this).

---

## 6. Set up the database

Run every script in `sql/` **in numeric order** against `PMS_DB`, using `sqlcmd` or SQL Server
Management Studio. All scripts are idempotent (`IF NOT EXISTS` / `WHERE NOT EXISTS` guards), so
re-running the whole sequence on an already-provisioned database is safe.

```powershell
# From an elevated prompt with sqlcmd on PATH, or run each file in SSMS in order:
$server = "sqlserver.company.local"
$db = "PMS_DB"
Get-ChildItem sql\*.sql | Sort-Object Name | ForEach-Object {
    Write-Host "Running $($_.Name)..."
    sqlcmd -S $server -d $db -E -i $_.FullName   # -E = Windows auth; use -U/-P for SQL auth
}
```

This runs 001 through 039 (schema + seed permissions for every module) plus the optional sample
data scripts (`004`, `007` — **skip or delete these two before running against a real production
database**; they seed demo Companies/Plants/Departments/KPAs/KPIs for local development only).

**Creating the first admin is not part of the automatic sequence — do it manually, once, after
everything else.** This exists because every other user/role mapping is created through the app's
own Users & Roles screen (`POST /admin/users`), which itself requires the caller to already hold
`HR_ADMIN` or `SYS_ADMIN` — on a brand-new database nobody can reach that screen without one
manually-seeded account.

**Recommended: `scripts/bootstrap_admin.py`** — an interactive CLI that works for both an
AD-mapped admin and a local (non-AD) admin, never hardcodes or stores a well-known password, and
is safe to re-run:

```powershell
python scripts\bootstrap_admin.py
```

It asks whether the first admin logs in via AD or a local account, prompts for whatever it needs
(an AD username, or a local username + a password entered via a masked prompt), and grants
`SYS_ADMIN`. See §11 for what to do right after it finishes.

(The older alternative, `sql/040_bootstrap_first_admin.sql` — hand-edit the file to replace
`'COMPANY\firstadmin'` with a real `DOMAIN\username`, then run it once against `PMS_DB` — still
works for an AD-only admin and is kept for reference, but has no local-account option and requires
editing a SQL file by hand. Prefer the script above.)

---

## 7. Smoke-test locally before wiring up IIS

From the app directory, with `.env` configured and the venv active:

```powershell
$env:AUTH_MODE = "ldap_bind"   # temporarily, to test without IIS in front
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then, from another shell:

```powershell
curl http://127.0.0.1:8000/health
# {"status":"ok","app":"Performance Management System"}
```

Confirm the database connection and the bootstrap admin work end-to-end:

```powershell
curl -X POST http://127.0.0.1:8000/auth/login -H "Content-Type: application/json" `
     -d '{"username":"COMPANY\\firstadmin","password":"<their AD password>"}'
```

A successful response returns `role_codes: ["SYS_ADMIN"]` and sets the session cookie. Stop this
process once confirmed — it was only for the pre-IIS smoke test. Switch `AUTH_MODE` back to
`iis_forwarded` in `.env` before continuing.

---

## 8. Deploy under IIS (production)

The recommended approach is **HttpPlatformHandler**: IIS starts, monitors, and reverse-proxies to
the uvicorn process itself, so you get IIS's process lifecycle management, logging, and
authentication integration for free, without running a separate Windows Service.

1. **Install IIS features** (if not already present): Server Manager → Add Roles and Features →
   Web Server (IIS) role, plus the **URL Rewrite** and **HttpPlatformHandler** modules (both are
   separate Microsoft downloads — `URLRewrite2.msi` and `httpPlatformHandler_amd64.msi`).
2. **Create the site** in IIS Manager: point its physical path at `D:\PMS\pms_app`.
3. **Copy `deploy/web.config`** to the site root (`D:\PMS\pms_app\web.config`) and edit the
   `processPath`/`workingDirectory` paths to match your actual install location.
4. **Set the app pool identity**: create a dedicated app pool (.NET CLR version "No Managed
   Code" — this is a pure reverse proxy, IIS runs no managed code itself), running as either a
   dedicated service account (needs write access to `FILE_STORAGE_PATH` and the log folder, plus
   a SQL login if `DB_AUTH_MODE=windows`) or `ApplicationPoolIdentity` with explicit NTFS grants
   to those same folders.
5. **Start the site.** IIS launches `python.exe -m uvicorn app.main:app --port %HTTP_PLATFORM_PORT%`
   itself on first request and keeps it running; check
   `D:\PMS\logs\pms-stdout.log` (the path set in `web.config`) if it fails to start — almost
   always a missing `.env` value, an unreachable SQL Server, or a missing ODBC driver.

### Alternative: reverse proxy without HttpPlatformHandler

If your environment prefers a persistent Windows Service instead of IIS-managed process
lifecycle: run `uvicorn app.main:app --host 127.0.0.1 --port 8000` as a Windows Service (via
[NSSM](https://nssm.cc/) or `pywin32`'s service wrapper), then use IIS's **Application Request
Routing (ARR)** module with a reverse-proxy rule forwarding `/*` to `http://127.0.0.1:8000`. This
adds one more moving part (the service) but decouples the app's uptime from IIS site
recycling — a reasonable choice if you already manage other Windows Services this way. The
`.env`/database/AD configuration in every other step is identical either way.

---

## 9. Configure Windows/AD authentication in IIS

1. In IIS Manager, select the site → **Authentication** → disable **Anonymous Authentication**,
   enable **Windows Authentication**.
2. Confirm your IIS/AD setup actually forwards the authenticated identity as an HTTP header named
   by `IIS_FORWARDED_USER_HEADER` (`X-Remote-User` by default) to the backend. Native IIS Windows
   Auth surfaces the identity as the `LOGON_USER`/`AUTH_USER` server variable, not an inbound HTTP
   header by default — add a **URL Rewrite → Inbound Rule** ("Set Server Variable" won't reach a
   reverse-proxied backend process; use an **Outbound custom header rewrite** or a small helper
   module per your IIS version) that copies the authenticated identity into that header before the
   request reaches `httpPlatformHandler`. This is an IIS-version-specific step — test it with
   `GET /auth/me` after logging in from a domain-joined browser and confirm `ad_username` matches
   the real logged-in user before going further.
3. `ad_service.authenticate_via_iis_header()` (in `app/services/ad_service.py`) is what reads that
   header on the backend — it does not re-validate against AD itself in `iis_forwarded` mode,
   since IIS has already done that; it only checks the forwarded identity resolves to an active
   `Users` row. **Because of this, the header must not be spoofable from outside IIS** — confirm
   your IIS/ARR configuration strips any client-supplied `X-Remote-User` header before Windows
   Auth sets its own, so a client cannot forge it.

---

## 9a. Hybrid (AD + local users)

Skip this section entirely if every user in your company network has an AD account and you're
using `iis_forwarded` or `ldap_bind` — those handle that case already.

Use `AUTH_MODE=hybrid` when you need the *same* login screen to accept both real AD accounts and a
smaller set of local, non-AD accounts — contractors without a domain login, service/integration
accounts, or a handful of users on a machine that can't reach a domain controller. Unlike
`demo_local`, `hybrid` is fully supported with `ENVIRONMENT=production`.

**How it decides, per login attempt:**

1. The app first checks its own local account table (`Demo_Login`, joined to `Users` by
   `ADUsername`) for the *exact* username string submitted.
2. If a local account matches, the submitted password is checked against that account's stored
   hash — full stop, no AD fallback for a recognized local username, whether the password was
   right or wrong.
3. If no local account matches that exact username string, the app falls through to the same AD
   bind `ldap_bind` mode uses (`app/services/ad_service.py`'s `authenticate_via_ldap_bind()`).

**The exact-string matching in step 1 matters for how you name local accounts.** The app also
tries the AD-normalized form of what was typed (e.g. typing `jdoe` normalizes to
`YOURDOMAIN\jdoe` using your configured `AD_DOMAIN`) — so if a local account happens to be stored
as `YOURDOMAIN\jdoe`, typing the bare `jdoe` will find it too. But a local account is more clearly
non-AD, and less likely to accidentally collide with a future real AD user of the same name, if
you give it a visually distinct prefix that will never match your AD normalization, e.g.
`LOCAL\contractor1` or `SVC\reporting-bot` — and then always log in with that exact string.

**Setup:**

1. In `.env`, set `AUTH_MODE=hybrid` (in addition to the `AD_SERVER`/`AD_DOMAIN`/`AD_BASE_DN` etc.
   values §5/§9 already have you fill in — hybrid mode still needs those for the AD side).
2. Make sure `sql/041_create_demo_login_table.sql` has been run (it's included if you ran the full
   numbered `sql/` sequence in §6, or run `sql/000_FULL_DATABASE_SETUP.sql` for a from-scratch
   install — both already create the `Demo_Login` table this needs).
3. Create the first admin with `scripts/bootstrap_admin.py` (§6) — choose either the AD or the
   local option there; both work under `hybrid`.
4. Create every other local account the same way `POST /admin/users` creates AD mappings, then set
   its password via `POST /auth/demo/set-password` (System Administrator/HR Administrator only) —
   or have that person set it themselves after their first login via **My Profile**.
5. Tell each local-account holder their exact username string (with its distinguishing prefix) —
   that's what they must type at `/app/login.html`, not just their name.

---

## 10. TLS/HTTPS

Terminate TLS at IIS (a certificate bound to the site's HTTPS binding, from your internal CA or a
public one if this intranet is externally reachable). The backend (`uvicorn`) only ever listens
on `127.0.0.1` and is never exposed directly — no certificate configuration is needed at the
Python layer. Confirm `ENVIRONMENT=production` in `.env`: this sets the session cookie's `Secure`
flag (`app/core/session.py`), which requires HTTPS to be in place, or browsers will silently drop
the cookie and every request will look unauthenticated.

---

## 10a. Using the built-in web frontend

Alongside the JSON API and the `/docs` Swagger UI, the app ships a small static HTML/CSS/JS
frontend under `app/static/`, served same-origin by the same `uvicorn` process (no separate web
server or build step required):

- It is mounted at **`/app`** — e.g. `https://<your-intranet-host>/app/login.html`.
- Browsing to the site root (`/`) redirects to `/app/login.html` automatically.
- It uses the exact same signed session cookie as the API (`app/core/session.py`), so a session
  started in the frontend also works against `/docs` and vice versa, and no CORS configuration is
  needed since everything is same-origin.
- The login page offers both the "Windows / AD" flow (relies on IIS Windows Integrated
  Authentication having already resolved identity — see §9) and, only when `AUTH_MODE=demo_local`
  is configured (never in `ENVIRONMENT=production` — see `DEPLOY_WINDOWS11_HOME_DEMO.md`), a local
  demo-login form.
- Pages included: a role-adaptive Dashboard (org summary for HR/Plant Head/MD/HR Administrator,
  system health for System Administrator, personal scope for Employee/Manager/HOD) and My
  Performance (the signed-in employee's own appraisal history, scores and approval timeline).
- Everything else (KPA/KPI masters, approvals, reports, user administration, etc.) is reached
  today through `/docs` or a future extension of this same static frontend — the pages shipped
  here cover sign-in and the two views every role needs first.

## 11. First login & initial configuration

1. Browse to `/app/login.html` (or `/docs`) over HTTPS as the bootstrap admin (§6). Confirm
   `GET /auth/me` shows `SYS_ADMIN`.
2. Use `POST /admin/users` to create real user/role mappings for HR Administrator, HR, Plant
   Head(s), MD, and department HODs/Managers as your rollout needs — every mapping from here on
   should go through this screen (it audits every change; §6's script does not).
3. Use `POST /system-config/{key}` (M28, System Administrator only) to record the operational
   settings the matrix names — `SMTP_SERVER`, `SMTP_PORT`, `SMTP_FROM`, `AD_SERVER`, `AD_DOMAIN`,
   `FILE_STORAGE_PATH`, `MAX_UPLOAD_SIZE_MB` — as a visible, audited record of what's running,
   alongside (not instead of) the actual `.env` values the app reads at startup.
4. Populate the org masters (Companies/Plants/Departments/Sections/Designations/Grades — M3),
   Employee Master (M4) and Performance Cycle (M5) through their own admin screens before opening
   the system to end users. `sql/004`/`007`'s sample data is for dev/UAT only — do not run those
   two files against production.

---

## 12. Security hardening checklist

- [ ] `.env` file permissions restricted to the app pool identity only (NTFS ACL — not readable by
      "Users" or "Everyone").
- [ ] `SESSION_SECRET_KEY` is unique to this environment, generated with a CSPRNG, never checked
      into source control.
- [ ] `ENVIRONMENT=production` (enables the `Secure` cookie flag — see §10).
- [ ] DB/AD service accounts follow least privilege: the DB login only needs rights on `PMS_DB`;
      the AD bind account (if used) is read-only.
- [ ] IIS Anonymous Authentication is disabled on the site (§9).
- [ ] The `X-Remote-User` (or whichever) forwarded-identity header cannot be set by a client
      directly — verified per §9 step 3.
- [ ] TLS is enforced (HTTP→HTTPS redirect at the IIS binding level); no plaintext HTTP endpoint
      is reachable from end-user network segments.
- [ ] `FILE_STORAGE_PATH` is outside the IIS-served web root (so uploaded files are never directly
      web-accessible by guessing a path — all downloads go through `GET /attachments/{id}/download`,
      which enforces RBAC scope).
- [ ] CORS is left at its default (disabled in `ENVIRONMENT=production` — see `app/main.py`); do
      not enable it for a same-origin intranet deployment.
- [ ] Run `pip list --outdated` periodically and review `requirements.txt` pins against current
      CVEs, particularly `fastapi`, `sqlalchemy`, `pyodbc`, `ldap3`.

---

## 13. Post-deployment verification

Run through this checklist after every deploy (initial or upgrade):

1. `GET /health` returns `{"status":"ok", ...}`.
2. Log in as a real (non-bootstrap) user of each of the 8 roles and confirm
   `GET /auth/me` returns the expected `role_codes` and `dashboard_route`.
3. Walk one appraisal record through the full workflow end-to-end in a UAT cycle: Self-Assessment
   → Manager Review → HOD Review → HR Review → Plant Head Approval → MD Final Approval, confirming
   the final score/rating computed by the Scoring Engine (M18) and that `GET
   /performance-history/{employee_id}` shows the completed record with its full score breakdown
   and transition timeline.
4. Confirm notifications appear (`GET /notifications`) at each stage transition.
5. Confirm an export (`GET /reports/appraisal-status?format=xlsx`) downloads and opens correctly.
6. Confirm `GET /audit-log` (as HR/MD/HR Administrator) shows entries for everything done in steps
   2-5.
7. Confirm `GET /system-config` is reachable only as System Administrator and refused (403) for
   every other role.

---

## 14. Backups & monitoring

- **Database**: `PMS_DB` is the single source of truth for everything except uploaded file
  contents — put it on your standard SQL Server backup schedule (full + transaction log, per your
  RPO/RTO requirements). This is the highest-priority backup target in the system.
- **File storage**: back up the directory at `FILE_STORAGE_PATH` on the same or a compatible
  schedule — `Attachment.StoredPath` rows in the database reference files there by generated
  filename; losing the directory without the DB (or vice versa) orphans one side.
- **Application logs**: `stdout`/`stderr` from the uvicorn process are captured at the path set in
  `deploy/web.config`'s `stdoutLogFile`. Rotate/archive per your log retention policy.
- **Audit trail**: `Audit_Log` (M26) is insert-only at the DB grant level and is itself a
  compliance record — include it in the same backup cadence as the rest of `PMS_DB`, and consider
  a longer retention policy for it specifically than for operational data.

---

## 15. Upgrading to a future change

1. Take a full database backup before every deploy.
2. Deploy the new application code (replace the `app/` directory contents; `.env` and
   `FILE_STORAGE_PATH` are untouched).
3. Run any new `sql/0XX_*.sql` files added since your last deploy, in numeric order — every script
   in this codebase is written idempotently, so re-running the full sequence from `001` is always
   safe if you're unsure which ones you already applied.
4. Restart the app pool / IIS site (or the Windows Service, if using the ARR alternative from §8)
   to pick up the new code.
5. Re-run the §13 verification checklist.

---

## 16. Known gaps intentionally left as documented no-ops (see each module's own README)

These are fully wired to their call sites but do nothing by default, since this build environment
had no AD server, SMTP relay, or AV engine reachable to integrate against for real:

- **Real SMTP delivery** — `notification_service.send_email_hook()` (M23). In-app notifications
  work regardless; wiring this to your real SMTP relay (already configured in `.env`/System
  Configuration) is a small, isolated change at that one function.
- **Real AD LDAP bind for `ldap_bind` mode** — `ad_service.authenticate_via_ldap_bind()` (M1) uses
  `ldap3` against the `AD_SERVER`/`AD_BASE_DN` settings; confirm this against your real AD schema
  in a UAT environment before relying on it (production should default to `iis_forwarded`, which
  does not need this path at all).
- **Real virus-scanning of uploads** — `attachment_service.virus_scan_hook()` (M22) is a no-op;
  wire it to your AV engine's scan API before accepting uploads from untrusted users, if your
  security policy requires it.

None of these block a production deployment on the `iis_forwarded` (default) authentication path;
they are the natural next integration points once real AD/SMTP/AV infrastructure is available to
test against.
