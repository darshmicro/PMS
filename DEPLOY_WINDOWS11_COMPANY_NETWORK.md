# PMS — Windows 11 Company Network Installation & Setup Guide

This is the guide to follow if you're installing the Performance Management System on a
**Windows 11 machine that sits on your company network**, want it reachable by everyone's
browser on that network, and want the app to accept **both real Active Directory logins and a
few local (non-AD) accounts** — all from the same login screen. It supersedes the other two guides
for this situation:

| | This guide | `DEPLOYMENT.md` | `DEPLOY_WINDOWS11_HOME_DEMO.md` |
|---|---|---|---|
| OS | Windows 11 (Pro/Enterprise, domain-joined or not) | Windows **Server** + IIS | Windows 11 **Home**, standalone |
| Auth | **Hybrid** — AD *and* local accounts together | AD only, via IIS | Local accounts only, demo-only, never production |
| Web server in front | None required — uvicorn runs directly (optionally as a Windows Service) | IIS (HttpPlatformHandler) | None — uvicorn, localhost only |
| Reachable from | Other machines on the company network | Other machines on the company network | Only the machine it runs on |
| Production-safe | **Yes** | Yes | **No — refuses to start in `ENVIRONMENT=production`** |

Everything else — the RBAC model, the 8 roles, the full appraisal workflow, scoring, approvals,
reports, employee/company profile photos, audit trail — is identical to the other two guides; only
how the app is reached and how people log in differ.

---

## 1. Prerequisites

| Component | Where to get it | Notes |
|---|---|---|
| Windows 11 (Pro or Enterprise recommended) | Your machine | Domain-joined is *not* required — AD is reached over the network (LDAP), not through domain membership, though domain-joining is the simpler way to guarantee network/DNS reachability to your domain controller |
| Python 3.11+ | [python.org/downloads](https://www.python.org/downloads/) — check "Add python.exe to PATH" during install | |
| SQL Server (Express, Standard, or an existing company SQL Server) | [Microsoft's SQL Server downloads page](https://www.microsoft.com/en-us/sql-server/sql-server-downloads) | Express is free and sufficient for most single-company deployments; use your existing DBA-managed SQL Server instead if your IT team already runs one |
| ODBC Driver 18 for SQL Server | [Microsoft's ODBC driver download page](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) | |
| SQL Server Management Studio (SSMS) *(optional but recommended)* | Same Microsoft downloads page | Makes running the `sql/*.sql` scripts point-and-click |
| Network reachability to a domain controller | Ask your IT/network team | Needed only if you intend to support AD logins — ports 389 (LDAP) or 636 (LDAPS, recommended) must be reachable from this machine to a DC. Not needed at all if you only plan to use local accounts, though `hybrid` mode still expects `AD_SERVER`/`AD_DOMAIN` to be filled in (see §5) |
| A fixed IP address or a stable hostname for this machine | Your network/DHCP settings | So the URL you give people (`http://<this-machine>:8000/app/login.html`) doesn't change after a reboot — see §9 |

---

## 2. Set up SQL Server

### Option A — install SQL Server Express locally on this machine

1. Run the installer → **Basic** install type is simplest.
2. Note the **instance name** it creates (commonly `SQLEXPRESS`, so the server address is
   `localhost\SQLEXPRESS`).
3. Decide the authentication mode for the *database* connection (this is separate from the app's
   own `AUTH_MODE` for end users, covered in §5):
   - **Windows Authentication** (default) — the app connects to SQL Server using the identity of
     whichever Windows account runs it. Simplest, no SQL password to manage. Use
     `DB_AUTH_MODE=windows` in `.env`.
   - **SQL Authentication (Mixed Mode)** — re-run the installer's configuration tool to enable
     Mixed Mode, set an `sa` password, then create a dedicated SQL login for the app. Use
     `DB_AUTH_MODE=sql` with `DB_USER`/`DB_PASSWORD` in `.env`. This is the better choice if the
     app will run under a different Windows account than the one that created the database, or if
     your IT policy requires named service accounts over Windows-identity trust.
4. Open SSMS (or `sqlcmd`), connect, and create the database:
   ```sql
   CREATE DATABASE PMS_DB;
   ```

### Option B — use an existing company SQL Server

Ask your DBA/IT team for: the server address (and instance name/port if non-default), whether to
use Windows or SQL authentication, and to create an empty `PMS_DB` database plus (for SQL auth) a
login with `db_owner` on it. Everything else in this guide is identical either way — only
`DB_SERVER`/`DB_PORT`/`DB_AUTH_MODE`/`DB_USER`/`DB_PASSWORD` in `.env` (§5) change.

---

## 3. Get the application onto the machine

Extract the delivered zip to a working folder, e.g. `C:\PMS\pms_app`.

```powershell
cd C:\PMS\pms_app
dir
```

You should see `app\`, `sql\`, `scripts\`, `deploy\`, `requirements.txt`, `.env.example`, and this
guide alongside `DEPLOYMENT.md` and `DEPLOY_WINDOWS11_HOME_DEMO.md`.

---

## 4. Python environment

```powershell
cd C:\PMS\pms_app
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Leave the virtual environment activated (`venv\Scripts\activate`) for every command below in this
guide, including the database setup and the first-admin script — they import the app's own code
and need the same dependencies.

---

## 5. Configure `.env`

```powershell
copy .env.example .env
notepad .env
```

Fill in every value — see the inline comments in `.env.example` for the full field list — with
these choices for this guide specifically:

- **`SESSION_SECRET_KEY`** — generate a fresh one:
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- **`ENVIRONMENT=production`** — this is a real company-network install, not a demo. (This also
  means `AUTH_MODE=demo_local` will be refused if you accidentally set it — use `hybrid` below.)
- **`DB_SERVER`/`DB_PORT`/`DB_NAME`/`DB_AUTH_MODE`/`DB_USER`/`DB_PASSWORD`** — from §2.
- **`AUTH_MODE=hybrid`** — this is the setting that makes the app accept both AD and local logins
  from the same screen. See "How hybrid authentication works" below for the mechanics.
- **`AD_SERVER`** — your domain controller's hostname or IP (e.g. `dc01.company.local`).
- **`AD_DOMAIN`** — your NetBIOS or DNS domain name (e.g. `COMPANY`), used to normalize a bare
  username like `jdoe` into `COMPANY\jdoe` when someone doesn't type the domain prefix themselves.
- **`AD_USE_SSL`/`AD_PORT`** — leave `AD_USE_SSL=true`/`AD_PORT=636` (LDAPS) unless your domain
  controller doesn't offer LDAPS, in which case use `AD_PORT=389` and confirm with your network
  team whether that's acceptable on your network.
- **`AD_BASE_DN`** — the distinguished name AD searches start from, e.g.
  `DC=company,DC=local`. Ask your AD admin if you're not sure.
- **`AD_BIND_DN`/`AD_BIND_PASSWORD`** — only needed if your AD environment requires an
  authenticated service account to perform lookups (rather than binding as the user directly);
  leave blank if unsure and add them later if AD logins fail with a bind error.
- **`FILE_STORAGE_PATH`** — an absolute path this machine can write to, e.g.
  `C:\PMS\storage\attachments` — used for uploaded evidence files, employee profile photos, and
  the company logo.
- **`SMTP_SERVER`/`SMTP_PORT`/`SMTP_FROM`** — your internal mail relay, if you have one (email
  sending is a documented no-op as shipped — see `README_M22.md`/`README_M23.md` — in-app
  notifications work regardless of this).
- **Never** commit `.env` to version control or copy it verbatim into any config file you might
  share — it holds credentials.

### How hybrid authentication works

Every login attempt is checked in this order:

1. The app first checks its own local account table for the *exact* username string submitted.
2. If a local account matches, the password is checked against that account's own stored password
   — there is no AD fallback for a recognized local username, right or wrong password.
3. If no local account matches that exact string, the app falls through to a live AD bind — the
   same check `ldap_bind` mode does — using your `AD_SERVER`/`AD_DOMAIN`/`AD_BASE_DN` settings
   above.

Because step 1 matches the *exact* string typed, give local accounts a prefix that will never
collide with how AD usernames get normalized — e.g. `LOCAL\contractor1` or
`SVC\reporting-bot` — rather than a bare name that might one day also belong to a real AD user.
Tell each local-account holder their exact username string; that's what they type to sign in.

---

## 6. Set up the database

Run every script in `sql\` in numeric order — or, simpler, run the single consolidated script:

```powershell
sqlcmd -S <your DB_SERVER value, e.g. localhost\SQLEXPRESS> -d PMS_DB -E -i sql\000_FULL_DATABASE_SETUP.sql
```

(`-E` uses your current Windows identity; swap in `-U <user> -P <password>` for SQL authentication.
If you'd rather click through SSMS instead of `sqlcmd`, open and execute the file there.)

`000_FULL_DATABASE_SETUP.sql` is a single, from-scratch, idempotent script kept in sync with every
individual numbered migration (`001`–`048` as of this build) — it creates every table this build
needs, including the `Demo_Login` table hybrid mode's local accounts are stored in. Safe to re-run.

Do **not** run `sql\004_*` or `sql\007_*` (or anything under `sql\demo_only\`) against this
database — those seed sample/demo data for local development only.

---

## 7. Create the first admin

Every user/role mapping after the first one is created through the app's own **Users & Roles**
screen, which itself requires the caller to already hold `HR_ADMIN` or `SYS_ADMIN` — so on a
brand-new database, nobody can reach that screen yet. `scripts\bootstrap_admin.py` creates exactly
one System Administrator account by hand so you have a way in:

```powershell
python scripts\bootstrap_admin.py
```

It asks how this first admin will log in:

- **Option 1 — an AD account.** You type the AD username (e.g. `COMPANY\jdoe`); the script never
  touches or asks for a password — that person's real AD password is what verifies them at login,
  exactly like any other AD user under `hybrid` mode.
- **Option 2 — a local account.** You type a username (use a distinct prefix as noted in §5, e.g.
  `LOCAL\sysadmin`) and set a password at a masked prompt (never echoed to the screen, never
  written to disk by this script, never logged) — hashed with the same bcrypt scheme the app uses
  for every local account's login.

Either way it grants that account the `SYS_ADMIN` role and is safe to re-run (it recognizes an
existing username and offers to just reconfirm the role grant, or reset the password for a local
account, rather than creating a duplicate).

---

## 8. Smoke-test locally before opening it up to the network

```powershell
venv\Scripts\activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Browse to `http://127.0.0.1:8000/app/login.html` on this machine and:

1. Log in as the admin account §7 created (AD password or local password, whichever you chose).
   `GET /auth/me` (or the app's own account display) should show `SYS_ADMIN`.
2. From **Users & Roles**, create a couple of real user/role mappings — try creating one AD
   mapping and one local account, to confirm both paths work end-to-end (for a local account, set
   its password via the same screen or have that person set it themselves after first login via
   **My Profile**).
3. Log out and log back in as each of those to confirm hybrid login works both ways.
4. Populate org masters (Companies/Plants/Departments/Sections/Designations/Grades), the Employee
   Master, and a Performance Cycle from their admin screens — the app is otherwise empty on a
   fresh database.

Stop the server (`Ctrl+C`) once this all checks out, before moving to §9.

---

## 9. Make it reachable on the company network

Everything so far has only been reachable from this machine itself (`127.0.0.1`). To let other
machines on the network reach it, bind to all interfaces instead and open the firewall:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```powershell
# Run once, from an elevated PowerShell prompt, to allow inbound connections on port 8000:
New-NetFirewallRule -DisplayName "PMS App (port 8000)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

Other machines on the network can now reach `http://<this-machine's-hostname-or-IP>:8000/app/login.html`.

### Keep it running (Windows Service) instead of a manual console window

Running `uvicorn` directly in a console window works, but it stops if that window closes or the
person logs out, and doesn't restart automatically after a reboot. For anything beyond a quick
trial, run it as a Windows Service instead using **NSSM** (Non-Sucking Service Manager, a small
free tool — [nssm.cc](https://nssm.cc/)):

```powershell
# Download nssm, then from an elevated prompt:
nssm install PMSApp "C:\PMS\pms_app\venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"
nssm set PMSApp AppDirectory "C:\PMS\pms_app"
nssm set PMSApp Start SERVICE_AUTO_START
nssm start PMSApp
```

This makes the app start automatically on boot and restart if it crashes, without anyone needing
to stay logged in or keep a console window open. Use `nssm stop PMSApp`, `nssm restart PMSApp`, and
`nssm remove PMSApp confirm` to manage it later, and `Get-Service PMSApp` to check its status.

### TLS/HTTPS

Browsers will send login credentials over this connection, so plain HTTP is only acceptable for a
quick trial on a trusted, isolated network segment. For a real rollout, put a TLS-terminating
reverse proxy in front of `uvicorn` (still bound to `127.0.0.1` behind it) — IIS with
`httpPlatformHandler` (see `DEPLOYMENT.md` §8–§10 for the IIS-specific steps, which still apply
here even outside a full IIS/AD setup) or another reverse proxy your IT team already standardizes
on both work. Whichever you use, confirm `ENVIRONMENT=production` is set in `.env` — this makes
the session cookie require HTTPS, so if TLS isn't actually in place yet, sign-in will appear to
silently fail (the cookie gets dropped) rather than working insecurely.

### DNS

If you don't already have one, ask your network team for a stable internal DNS name for this
machine (e.g. `pms.company.local`) rather than distributing a raw IP address, so the URL keeps
working if the machine's IP changes later.

---

## 10. Post-install verification

- [ ] `GET /auth/me` (or the account panel in the app) shows the correct role for a freshly logged
      in AD user.
- [ ] The same, for a freshly logged in local user.
- [ ] A wrong password for a local account is rejected (401) with no AD attempt made.
- [ ] A local account whose username happens to also be a bare AD-style name (e.g. plain `jdoe`
      with no distinguishing prefix) is *not* accidentally shadowing a real AD user of the same
      name — confirm this if you didn't follow the distinct-prefix advice in §5.
- [ ] From another machine on the network (not this one), reach
      `http://<hostname>:8000/app/login.html` (or your TLS URL) and log in successfully.
- [ ] Profile photo upload (**My Profile**) and company logo upload (**Company** master, HR/Plant
      Head only) both work and the image appears in the top bar / sidebar afterward.
- [ ] The Windows Service (if configured per §9) restarts the app automatically after a machine
      reboot — reboot once and confirm the login page is reachable again without manual steps.
- [ ] Confirm nightly/regular backups are in place for `PMS_DB` and for `FILE_STORAGE_PATH` (ask
      your DBA/IT team if these aren't already covered by existing backup policy) — this guide
      doesn't set up backups itself.

---

## 11. Day-to-day administration afterward

- Every subsequent user (AD or local) is created from **Users & Roles** in the app itself, not by
  re-running `scripts\bootstrap_admin.py` — that script is only for the very first account.
- HR, HR Administrator, and Plant Head can create employees and assign roles; System Administrator
  and HR Administrator can manage local account passwords via `POST /auth/demo/set-password`;
  anyone can update their own password via **My Profile**.
- To upgrade to a later delivery of this application, see `DEPLOYMENT.md` §15 ("Upgrading") — the
  same steps apply regardless of which guide you used to install it.
