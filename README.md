# Rumi Dental Care — Phase 1

Private, offline-first patient management for one dental clinic and one dentist in Lahore. The main workflow is phone → matching patients → individual profile → edit demographics and medical alerts. No online deployment, paid services, CDN assets or internet calls are used during everyday operation.

**Trial build: use fictional data only. Do not enter real patient information until backup/restore and the clinic trial requirements in Phases 5–6 have passed.** This is not the final clinic installation.

## Windows setup

### Double-click startup (existing Phase 1 trial)

Double-click **`Start Rumi Dental Care.cmd`** in the project folder. It uses the Python and data directory relative to that file, even when invoked from another folder or a path containing spaces. No activation, administrator rights, global environment changes or internet connection are required.

It checks the existing virtual-environment Python, nonempty `runtime\development\clinic.sqlite3`, matching secret and required migrations without applying changes. It never installs packages, initializes a database, creates accounts or resets passwords. A failed check displays instructions and keeps the error window open until you press a key.

The browser opens at **http://127.0.0.1:8000/** only after a bounded readiness check verifies a signed response for this checkout, Python and database. If the same verified server already runs, it is reused. An unknown service, another checkout/data directory or an older server without readiness support produces a conflict message; nothing is killed and no alternative port is chosen. Stop an identified old Rumi server from its own console before retrying.

**Keep the server console open while using the application. Press Ctrl+C there to stop. Closing only the browser does not stop the server.** When reusing a server, keep its original console open. This is a **Phase 1 trial launcher**; final operational installation/service packaging remains Phase 6.

### Desktop shortcut

The **Rumi Dental Care** desktop shortcut targets `Start Rumi Dental Care.cmd`, with this project as its working directory and a normal visible console. Double-click it to start or reuse the verified local application, open the browser and sign in with your existing account. It stores no credentials and does not request administrator privileges.

To recreate it, open PowerShell in the project folder and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Setup Desktop Shortcut.ps1"
```

The execution policy applies only to that PowerShell process; it does not change global settings. The script derives the project directory from its own file and asks Windows for the current user's actual Desktop directory, including OneDrive/redirected Desktops. It verifies the shortcut target, working directory, empty arguments, visible window and absence of an elevation flag. Repeating setup for this same installation is safe.

No suitable clinic icon is supplied yet, so the shortcut uses the built-in blue Windows console icon, not an invented clinic logo. If an approved local ICO is later supplied as `static\rumi-dental-care.ico` or `static\clinic.ico`, setup uses it without downloading anything.

After moving the project, run setup from its new folder. If an existing same-name shortcut targets another location or has custom arguments, setup **preserves it and reports the conflict**. Confirm whether it belongs to the moved installation, then rename/remove that old shortcut yourself before rerunning setup. The script never replaces another installation's shortcut automatically. Generated `.lnk` files are ignored by Git.

Optional Windows verification of shortcut setup, using only temporary fixtures under ignored `runtime/`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_desktop_shortcut.ps1
```

### Account-management shell

Double-click **`clinic-shell.cmd`**. It opens PowerShell in this project with `DJANGO_SETTINGS_MODULE=config.settings` and `RUMI_DATA_DIR` set to this project's `runtime\development`. Its preflight uses the same non-mutating checks. Use the project's Python directly:

```powershell
.\.venv\Scripts\python.exe manage.py shell -c "from django.contrib.auth import get_user_model; print(list(get_user_model().objects.values('username','is_superuser','is_active')))"
.\.venv\Scripts\python.exe manage.py showmigrations --plan
```

Existing logins are `owner` and `doctor`; use your existing passwords. If the owner actually needs a password reset, run `manage.py changepassword owner` or `manage.py changepassword doctor` with the same `.venv` Python in this shell, entering the password only at the local hidden prompts. Closing the clinic shell does not stop a server running in another window.

### Resume this checkout's existing trial

The Phase 1 handoff used **`runtime\development`**, not the default AppData directory. The existing `owner` and `doctor` accounts are in that trial database. Reuse the virtual environment and select the same directory in every new PowerShell window:

```powershell
$env:RUMI_DATA_DIR = Join-Path (Get-Location) 'runtime\development'
$env:DJANGO_SETTINGS_MODULE = 'config.settings'
.\.venv\Scripts\python.exe manage.py showmigrations --plan
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
$env:DJANGO_SETTINGS_MODULE = 'config.settings'
$env:RUMI_DATA_DIR = Join-Path (Get-Location) 'runtime\development'
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

**Both launchers select the existing ignored `runtime\development` directory**, containing `clinic.sqlite3` and `secret.key`. Never move only the database and leave its matching secret behind. Direct `manage.py` commands without an explicit `RUMI_DATA_DIR` still fall back to **`$env:LOCALAPPDATA\RumiDentalCare`**; that is a different directory and must not be used for this trial. Use `clinic-shell.cmd` to prevent that mismatch. Keep the secret private and retain it across restarts. Use a Windows account with a password, disk encryption where available, and private filesystem permissions; application roles do not protect against someone who can read the database file.

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

Launcher preflight without starting a server or browser:

```powershell
& '.\Start Rumi Dental Care.cmd' --check
```

Windows integration verification (stop your known trial server in its own console first to free port 8000):

```powershell
.\.venv\Scripts\python.exe scripts\check_windows_launchers.py
```

This opt-in check creates and migrates only a temporary fictional fixture under ignored `runtime/`, with a path containing spaces and a junction to the existing `.venv`. It tests the real CMD/PowerShell launchers from another directory, missing prerequisites, pending migrations, readiness, verified reuse, other-checkout rejection and an unrelated occupied port. It cleans up only its own test server/process tree and fixture; it never stops an arbitrary listener. It verifies that the actual clinic database/secret and the unintended AppData database/secret remain byte-for-byte unchanged. No browser is opened by this integration check.

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
                     Trial launcher helper and Windows integration checks
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
