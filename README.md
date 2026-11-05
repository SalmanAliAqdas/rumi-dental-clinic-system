# Rumi Dental Care — Phase 1

Private, offline-first patient management for one dental clinic and one dentist in Lahore. The main workflow is phone → matching patients → individual profile → edit demographics and medical alerts. No online deployment, paid services, CDN assets or internet calls are used during everyday operation.

**Trial build: use fictional data only. Do not enter real patient information until backup/restore and the clinic trial requirements in Phases 5–6 have passed.** This is not the final clinic installation.

## Windows setup

### Resume this checkout's existing trial

The Phase 1 handoff used **`runtime\development`**, not the default AppData directory. The existing `owner` and `doctor` accounts are in that trial database. Reuse the virtual environment and select the same directory in every new PowerShell window:

```powershell
$env:RUMI_DATA_DIR = Join-Path (Get-Location) 'runtime\development'
.\.venv\Scripts\python.exe manage.py showmigrations --plan
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --insecure --noreload
```

Keep just one trial server running. If port 8000 is occupied, use the existing server or stop that project's old server before restarting. Do not recreate accounts or reset a database to solve a login error. Password resets, if actually needed, must use this same `RUMI_DATA_DIR`.

The guarded `runserver` now refuses to serve a missing, empty or unmigrated database and prints the selected database path and setup instructions in the local console. Windows sockets use exclusive binding to prevent two Django servers from sharing the same address. It does not automatically migrate, copy or replace any database.

### First installation on a new computer

Use supported Python 3.13 (latest security patch recommended). Django 5.2.19 LTS was verified against Python 3.13.5 here. Django's [download page](https://www.djangoproject.com/download/) listed 5.2.19 and the [5.2 compatibility notes](https://docs.djangoproject.com/en/5.2/releases/5.2/) include Python 3.13, checked 6 November 2026. All runtime dependencies, including transitive dependencies, are pinned in `requirements.txt`.

Open PowerShell in this project folder:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser --username owner
```

Enter your own strong password at the hidden prompts. No accounts or default passwords ship with this project. The owner is a Django superuser; there is deliberately no general Django admin route. One-time dependency installation requires internet or a separately prepared offline wheel folder. Once installed, application use needs no internet.

Create the Doctor using either the owner's **Accounts → Create Doctor login** page, or this local command:

```powershell
.\.venv\Scripts\python.exe manage.py create_doctor doctor
```

The command asks for and validates a hidden password. It assigns only patient view/add/change permissions and never staff, superuser, audit-write, export or deletion permissions. Local management commands are trusted workstation maintenance: restrict Windows access to the clinic owner. They are not public web endpoints.

Start the local trial:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --insecure --noreload
```

Open **http://127.0.0.1:8000/**. `--insecure` is Django's flag for serving this project's local CSS when `DEBUG=False`; patient views still require authentication. Bind to loopback only. Do not bind to `0.0.0.0`, publish this server, or configure a router tunnel. Stop with Ctrl+C. `runserver` is for development/trials; a reliable Windows service/startup package is Phase 6.

You do not need to activate the virtual environment or change PowerShell execution policy.

## Data and account maintenance

Default data directory: **`$env:LOCALAPPDATA\RumiDentalCare`**, normally `C:\Users\<Windows user>\AppData\Local\RumiDentalCare`. It is separate from application source and contains `clinic.sqlite3` and a randomly generated persistent `secret.key`. Django creates these on first use. Keep the secret private and retain it across restarts. Use a Windows account with a password, disk encryption where available, and private filesystem permissions; application roles do not protect against someone who can read the database file.

To choose another writable directory, set this before **every** management/start command, including migrations:

```powershell
$env:RUMI_DATA_DIR = 'C:\ClinicData\RumiDentalCare'
```

Do not switch directories accidentally: doing so opens a different clinic database. Current implementation verification used ignored `runtime\development` and isolated temporary browser data, so your default data directory has not been seeded with demo accounts.

The owner can enable/disable Doctor accounts on Accounts; disabling blocks their existing sessions on the next request. Password reset (owner at the Windows console):

```powershell
.\.venv\Scripts\python.exe manage.py changepassword doctor
```

Resetting a password invalidates existing sessions. Owner credentials use the same `changepassword owner` command. There is no public password reset or registration. The owner can inspect read-only patient events at `/audit/`; the Doctor is denied this route. Fixed Doctor permissions are intentional in Phase 1. Arbitrary role editing is not exposed.

## Manual phone-search trial

1. Log in as Doctor and register **Fictional Patient**, phone **03001234567**, approximate age **35**. Only name and primary phone are required.
2. Open Find a patient and search separately for `0300 1234567`, `0300-1234567`, `+923001234567` and `00923001234567`. Each should return the same patient.
3. Open the result, check the permanent `RDC-…` number and approximate age recording date, edit occupation or allergies, and save. A blank medical field means **Not recorded**; enter **None confirmed** only when explicitly confirmed.
4. Register a second fictional family member using the same phone. The first submit warns and displays matches; review and tick the confirmation before submitting again. Search the phone and choose between both names, numbers and ages.
5. Try a name, patient number, or four or more phone digits. Try an international number such as `+44 20 7946 0958` (national numbers without a country code are interpreted as Pakistani).
6. Log out using the button. Opening a patient URL must require login. As Doctor, visiting `/accounts/` or `/audit/` must return access restricted.

## Tests

```powershell
.\.venv\Scripts\python.exe manage.py test -v 2
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
```

Tests use an isolated in-memory database; they do not register patients in your normal database. `check --deploy` is an additional future-hosting diagnostic; HTTPS/HSTS/secure-cookie warnings are expected for this deliberately loopback-only HTTP trial and must be resolved before any online stage.

Optional browser check, with development-only Playwright installed (`.\.venv\Scripts\python.exe -m pip install playwright==1.64.1`, then `.\.venv\Scripts\python.exe -m playwright install chromium`), run from a Python environment containing Playwright:

```powershell
.\.venv\Scripts\python.exe scripts\browser_check.py
```

It uses an isolated temporary database, random temporary password, loopback server and fictional data, then removes its database and stops the server. Screenshots go to ignored `runtime/`. It verifies both Owner and Doctor login, dashboard, patient search/edit and logout at desktop and narrow widths, checks account/audit permissions and blocks external asset requests. It does not use or change your existing account passwords. Playwright is not needed to run the clinic application. See `docs/PROGRESS.md` for checks actually executed.

## Structure

```text
config/              Settings, routes and WSGI entry point
clinic/              Patient model, forms, phone normalization, views, access
  migrations/        Database schema history
  management/        Secure Doctor-account command
  tests.py           Automated functional and security tests
templates/           Offline Django interface
static/clinic.css    Local responsive dark theme and white print foundation
scripts/             Optional isolated browser smoke check
docs/                Requirements, six-phase roadmap and verification record
runtime/             Ignored development/test artifacts only
```

The database uses Django's ORM and migrations, not SQLite-specific application SQL. A future PostgreSQL migration will need its own settings, data migration and verification; Phase 1 does not configure online hosting.

## Security and limitations

Every patient route checks authentication and the relevant Django permission on the server. Login uses Django password hashing, CSRF and sessions; logout is POST-only. Sessions expire after 30 idle minutes and at browser close. Persistent hashed-account and client login buckets allow five failed attempts per 15-minute window; shared loopback clients can temporarily lock each other out. Restarting the app does not reset throttling. Wait for the window to expire; do not weaken protection to troubleshoot a forgotten password.

Search uses same-origin POST, paginates at 20 results and requires four digits for partial phone queries (two characters for names/numbers). Canonical E.164 phone and WhatsApp columns have indexes for exact lookup. Substring searches can scan rows; realistic-volume performance must be evaluated during the clinic trial. Full phone matching searches both primary phone and WhatsApp. Numbers are not unique across patients. Patient numbers are immutable, unique opaque references; they are not an authorization mechanism.

Patient responses have private/no-store cache controls, a same-origin referrer policy and restrictive same-origin CSP headers. Ordinary Django request/access logs are suppressed to avoid retaining URLs or patient terms. The audit database stores actor, patient reference, action and timestamp, never copies of clinical text. It records create/update and individual profile reads; it does not preserve previous field values or cover every possible database maintenance operation. It is **not tamper-proof**, and neither SQLite nor the secret file is encrypted by this application. There are no deletion, upload, clinical visit, finance, prescription, appointment, backup, restore or export features in Phase 1. Future tabs are clearly pending.

## Git and private GitHub repository

Runtime files, virtual environments, secrets, SQLite sidecars, uploads and backups are ignored. Inspect `git status` and staged file names before each commit. Never include actual patient information in fixtures, screenshots, issues or Git.

No remote should be guessed. If one is not configured, sign into GitHub, choose **New repository**, name it **rumi-dental-care**, select **Private**, and leave README/.gitignore/license initialization unchecked. Then replace YOUR_USERNAME below with the exact account used:

If Git reports **dubious ownership** because this repository was initialized under the restricted Codex Windows account, run this once from the project folder in your normal PowerShell. It trusts only this specific folder, not other repositories:

```powershell
git config --global --add safe.directory (Get-Location).Path
```

```powershell
git remote add origin https://github.com/YOUR_USERNAME/rumi-dental-care.git
git branch -M main
git push -u origin main
```

Verify the repository is private before pushing. If you use GitHub CLI, an alternative from this folder is `gh repo create rumi-dental-care --private --source=. --remote=origin --push`. This creates a repository and uploads source; it does not deploy the clinic app.

Next: Phase 2 introduces visits, longitudinal medical history, dental chart, treatments and private attachments under each profile. See [requirements](docs/REQUIREMENTS.md), [roadmap](docs/ROADMAP.md) and [progress](docs/PROGRESS.md).
