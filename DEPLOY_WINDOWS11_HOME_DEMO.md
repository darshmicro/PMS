# PMS — Windows 11 Home Local Demo Setup

This is a **separate, demo-only path** alongside `DEPLOYMENT.md` (the real production guide for
Windows Server + IIS + Active Directory). Windows 11 Home cannot join an AD domain and has no
Windows-Integrated-Auth/Kerberos story of its own, so the production design (`AUTH_MODE=
iis_forwarded`, users authenticated by IIS against a domain) doesn't apply here at all. This guide
runs the exact same application code, against the exact same SQL Server schema, with two things
swapped for a local machine with no domain:

| | Production (`DEPLOYMENT.md`) | This demo |
|---|---|---|
| Authentication | IIS + Windows/AD domain accounts | The app's own local username/password login (`AUTH_MODE=demo_local`) |
| Web server in front | IIS (HttpPlatformHandler) | None — uvicorn runs directly, browsed at `http://127.0.0.1:8000` |
| Database | SQL Server (any edition) | SQL Server **Express** (free), installed locally |

Everything else — the RBAC model, the 8 roles, the full appraisal workflow, scoring, dashboards,
reports, audit trail — is identical; only how you log in and how the server is reached differ.

**This mode must never be used in production** — see §7. The application itself refuses to start
a `demo_local` login when `ENVIRONMENT=production`, as a safety net on top of this guide.

---

## 1. Prerequisites

| Component | Where to get it |
|---|---|
| Windows 11 Home | Your machine |
| Python 3.11+ | [python.org/downloads](https://www.python.org/downloads/) — check "Add python.exe to PATH" during install |
| SQL Server 2022 Express | [Microsoft's SQL Server downloads page](https://www.microsoft.com/en-us/sql-server/sql-server-downloads) — choose the free "Express" edition |
| ODBC Driver 18 for SQL Server | [Microsoft's ODBC driver download page](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) |
| SQL Server Management Studio (SSMS) *(optional but recommended)* | Same Microsoft downloads page — makes running the `sql/*.sql` scripts point-and-click instead of command-line |

---

## 2. Install SQL Server Express

1. Run the SQL Server Express installer → choose **Basic** install type (simplest — it sets up a
   default instance and starts the service for you).
2. When it finishes, note the **instance name** it created (commonly `SQLEXPRESS` — so the server
   address to connect to is `localhost\SQLEXPRESS`).
3. SQL Server Express installs in **Windows Authentication mode** by default — this works fine
   with a **local (non-domain) Windows user account** too, since it's your own machine's account,
   not a domain principal. This is the simplest option: your app will connect using the identity
   of whichever Windows account runs it, with no SQL password to manage at all.
   - If you'd rather use a SQL login/password instead, re-run the installer's configuration tool
     to enable **Mixed Mode** and set an `sa` password, then create a dedicated SQL login for the
     app (see §4's `DB_AUTH_MODE=sql` option).
4. Open SSMS (or `sqlcmd`), connect to `localhost\SQLEXPRESS`, and create the database:
   ```sql
   CREATE DATABASE PMS_DB;
   ```

---

## 3. Get the application onto your machine

Extract the delivered zip to a working folder, e.g. `C:\PMS\pms_app`.

```powershell
cd C:\PMS\pms_app
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` includes `bcrypt` (pinned to `4.0.1` — a newer `bcrypt` has a known
incompatibility with the `passlib` version this app uses, causing a cryptic "password cannot be
longer than 72 bytes" error; the pin avoids that entirely). It also needs the ODBC Driver 18
installed in §1 for `pyodbc` to actually reach SQL Server.

---

## 4. Configure `.env`

```powershell
copy .env.example .env
notepad .env
```

Set (differences from the production template are called out):

```ini
SESSION_SECRET_KEY=<generate one - see below>
ENVIRONMENT=development

DB_SERVER=localhost\SQLEXPRESS
DB_NAME=PMS_DB
DB_AUTH_MODE=windows
# DB_USER / DB_PASSWORD only needed if you set up Mixed Mode + a SQL login instead
DB_DRIVER=ODBC Driver 18 for SQL Server
# ODBC Driver 18 validates the server's TLS certificate by default, and SQL
# Server Express only has a self-signed one - "yes" here tells the driver to
# trust it anyway. Fine for a local/loopback demo; never set this to "yes"
# against a real network-reachable production SQL Server.
DB_TRUST_SERVER_CERTIFICATE=yes

AUTH_MODE=demo_local
```

**If you get `SSL Provider: The certificate chain was issued by an authority
that is not trusted`** when the app tries to connect, it's this same cause -
make sure `DB_TRUST_SERVER_CERTIFICATE=yes` is set in `.env` (not just enabled
in a shell session) and restart uvicorn.

**If you get `TCP Provider: ... actively refused it`**, SQL Server's TCP/IP
protocol isn't enabled or the service isn't listening on the port you
configured. Open **SQL Server Configuration Manager** (the `.msc` file name
depends on your SQL Server version - e.g. `SQLServerManager17.msc` for
SQL Server 2025, `16.msc` for 2022, `15.msc` for 2019) → **SQL Server Network
Configuration → Protocols for SQLEXPRESS** → enable **TCP/IP** → restart the
**SQL Server (SQLEXPRESS)** service. If Configuration Manager doesn't show
your instance (can happen on a version newer than your installed snap-in),
enable it via PowerShell instead - **run as Administrator**:

```powershell
$instanceId = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL").SQLEXPRESS
$tcpPath = "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\$instanceId\MSSQLServer\SuperSocketNetLib\Tcp"
Set-ItemProperty -Path $tcpPath -Name "Enabled" -Value 1 -Type DWord
Set-ItemProperty -Path "$tcpPath\IPAll" -Name "TcpDynamicPorts" -Value "" -Type String
Set-ItemProperty -Path "$tcpPath\IPAll" -Name "TcpPort" -Value "1433" -Type String
Restart-Service -Name "MSSQL`$SQLEXPRESS" -Force
```

Generate a session secret the same way as production:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Leave `AD_SERVER`/`AD_DOMAIN`/`AD_BASE_DN` at any placeholder value — they're required fields on
the `Settings` model but are never read in `demo_local` mode, since no AD is involved.

Set `FILE_STORAGE_PATH` to a real local folder, e.g. `C:\PMS\storage\attachments` (create it if it
doesn't exist — the app writes uploaded evidence files there).

---

## 5. Set up the database

Run every script in `sql\` **in numeric order** (001 through 039 — the same production schema and
permission seed used in `DEPLOYMENT.md`), then the two demo-only scripts:

```powershell
$server = "localhost\SQLEXPRESS"
$db = "PMS_DB"
Get-ChildItem sql\*.sql | Sort-Object Name | ForEach-Object {
    Write-Host "Running $($_.Name)..."
    sqlcmd -S $server -d $db -E -i $_.FullName
}
# Then the demo-only scripts, in order:
sqlcmd -S $server -d $db -E -i sql\demo_only\041_create_demo_login_table.sql
sqlcmd -S $server -d $db -E -i sql\demo_only\042_bootstrap_first_admin_demo_local.sql
```

(`-E` uses your current Windows account for the connection — matching `DB_AUTH_MODE=windows` in
`.env`. If you set up Mixed Mode instead, use `-U <login> -P <password>`.)

Skip `sql\004_seed_sample_master_data.sql` and `sql\007_seed_sample_performance_data.sql` if you'd
rather start from an empty org structure and build it yourself through the admin screens; include
them if you want realistic-looking demo data (sample companies/plants/departments/KPAs/KPIs)
already in place to click through.

`042_bootstrap_first_admin_demo_local.sql` creates your first login:

- **Username:** `demoadmin`
- **Password:** `Demo@12345`
- **Role:** `SYS_ADMIN`

Change this password immediately after your first login (§6, step 3) — don't leave the
well-known default active.

---

## 6. Run it

```powershell
.\venv\Scripts\activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

1. Open **http://127.0.0.1:8000/health** — confirms the app and DB connection are both up.
2. Open **http://127.0.0.1:8000/app/login.html** — the actual PMS web frontend (same dark-theme
   UI as production, served statically by this same `uvicorn` process, no extra setup). Click the
   **Local demo** tab, sign in as `demoadmin` / `Demo@12345`, and you land on a real Dashboard and
   My Performance page driven by the live API. Browsing to `http://127.0.0.1:8000/` on its own
   redirects here automatically.
3. Prefer to drive the API directly instead? Open **http://127.0.0.1:8000/docs** — FastAPI's
   interactive Swagger UI. Log in the same way: `POST /auth/login` with body
   `{"username": "demoadmin", "password": "Demo@12345"}`; Swagger UI carries the returned session
   cookie automatically for subsequent calls in the same browser tab. (The `/app` frontend and
   `/docs` share the same session cookie, so you can freely switch between the two.)
4. **Change the demo admin's password right away:**
   `PUT /auth/demo/change-password` with
   `{"current_password": "Demo@12345", "new_password": "<something only you know>"}` (via `/docs`,
   or an equivalent screen once your rollout adds one to `/app`).
5. Create more demo users for other roles to click through the workflow as different people:
   - `POST /admin/users` — maps a username to an Employee record and one or more roles (same
     screen as production — see `README_M1_M2.md`/`DEPLOYMENT.md §11` for its shape).
   - `POST /auth/demo/set-password/{user_id}` (as `demoadmin`, or any `HR_ADMIN`/`SYS_ADMIN`) —
     sets that new user's demo login password, since `POST /admin/users` only creates the identity/
     role mapping, not a password.
   - Log out (from `/app`, the sidebar's **Log out** button; from `/docs`, `POST /auth/logout`) and
     log back in as each demo user to see their role's own dashboard and permissions.

Leave this `uvicorn` window open while demoing; `Ctrl+C` stops the server.

**To demo from another device on your home network** (e.g. a phone or laptop on the same Wi-Fi),
start uvicorn with `--host 0.0.0.0` instead of `127.0.0.1` and browse to
`http://<this-PC's-LAN-IP>:8000/app/login.html` from the other device. Windows may prompt to allow
Python through the firewall the first time — allow it only for **Private networks**.

---

## 7. This is a demo, not a deployment — what's different from production, on purpose

- **No IIS, no TLS.** Traffic between your browser and `uvicorn` is plain HTTP on `127.0.0.1` (or
  your home LAN if you used `--host 0.0.0.0`) — fine for a local demo, never acceptable once real
  employee data or a real network is involved.
- **No AD-grade account protections.** `demo_local` passwords are bcrypt-hashed (never stored in
  plaintext, never logged) but this path has none of AD's account-lockout policy, password
  complexity enforcement, centralized deactivation, or Kerberos single sign-on.
- **The app refuses to run `demo_local` logins when `ENVIRONMENT=production`** — a deliberate
  guard in `app/api/routes/auth.py` and `app/api/routes/demo_auth.py`, so this mode can't
  accidentally end up reachable on a real deployment even if `AUTH_MODE` were left misconfigured.
- **When you're ready to go to a real deployment** — a Windows Server on your company's domain —
  follow `DEPLOYMENT.md` instead: set `AUTH_MODE=iis_forwarded`, put IIS with Windows Integrated
  Auth in front, and run the same `sql/001-039` scripts (skip the whole `sql/demo_only/` folder
  entirely; nothing in production ever creates the `Demo_Login` table).
