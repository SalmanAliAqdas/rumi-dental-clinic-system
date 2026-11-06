# Rumi Dental Care - local Windows application

Private, offline-first dental clinic records for one branch and one dentist. Django 5.2 LTS, Python 3.13 and SQLite; no online hosting, external assets or paid services. Runtime dependencies are pinned in `requirements.txt`.

**v6.0 is a fictional-data trial. Software checks do not authorize real patient use. Complete the Owner/Doctor and off-device recovery checks in [CLINIC_TRIAL](docs/CLINIC_TRIAL.md).**

## Daily start and stop

Double-click **Rumi Dental Care** on the desktop. Wait for verified readiness, then sign in with your existing account. Waitress runs in the background on **127.0.0.1:8000** with DEBUG=False; WhiteNoise serves only bundled static assets. Closing the browser leaves the application and backup scheduler running. Repeated Start reuses only a signed matching checkout/runtime/interpreter instance.

Double-click **Stop Rumi Dental Care** before shutting down Windows or offline recovery. It closes admission to new work, waits for active requests/streams and backup jobs, then releases the runtime lease. A wait/failure displays a useful message; it never kills an unrelated process or trusts a PID. No administrator rights, service or login autostart are used.

Create/update both shortcuts:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Setup Desktop Shortcut.ps1"
```

The script resolves its own location, supports spaces and redirected Desktops, preserves another installation/custom shortcut, and upgrades the same installation's original CMD shortcut. Shortcuts use project `pythonw.exe`, so no black console remains open. **Diagnostic Start Rumi Dental Care.cmd** provides a visible troubleshooting server. `Start Rumi Dental Care.cmd --check` performs read-only preflight; `Stop Rumi Dental Care.cmd` provides visible shutdown diagnostics.

## Existing installation and updates

This checkout's original data is **runtime/development**, containing `clinic.sqlite3`, matching `secret.key`, attachments and local configuration. Desktop/root launchers always explicitly select it, overriding accidental terminal settings. They refuse missing/empty data, missing secret, pending migrations, interrupted restore and port identity conflicts. They never create accounts, migrate or reset passwords.

Stop first, then check/install pinned dependencies and verify the existing runtime:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Setup Local.ps1" -DataDirectory "$PWD\runtime\development"
```

For an update with migrations, add `-Update`. This makes and verifies a complete local safety snapshot before applying migrations under an exclusive server lease. Conflicting environment/data selections are refused. Patient data is not relocated. Dependency installation needs internet once, or a prebuilt compatible wheel folder via `-Wheelhouse`. See [BACKUP_AND_RECOVERY](docs/BACKUP_AND_RECOVERY.md) for offline installation and restoration without a running server.

Keep code and patient data separate: never put data into source folders, commit runtime, or synchronize the live database. Runtime is ignored by Git; future code updates must preserve it. Never move only the database without its secret and attachments. Local plaintext safety snapshots are private same-laptop protection only; keep encrypted off-device backups too.

`clinic-shell.cmd` opens the matching project/settings/runtime shell for trusted Owner maintenance. Existing accounts/passwords are retained. If actually required, use the project's Python with `manage.py changepassword owner` or `doctor` and hidden local prompts. No general Django admin endpoint exists.

For a deliberate alternate existing runtime, use explicit `RUMI_DATA_DIR` and `manage.py serve_clinic` after guarded maintenance checks. Root desktop shortcuts still select runtime/development. Never mistake one for the other.

## Genuinely new clinic only

Recovering an existing clinic: install Python/source/dependencies, then use standalone recovery; **do not initialize replacement records/accounts**. For a genuinely new clinic with no records, create `.venv` using Python 3.13, install requirements, explicitly select your intended runtime, then initialize:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DJANGO_SETTINGS_MODULE = 'config.settings'
$env:RUMI_DATA_DIR = Join-Path $PWD 'runtime\development'
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser --username owner
.\.venv\Scripts\python.exe manage.py create_doctor doctor
```

Choose your own passwords at hidden prompts. No default passwords ship. Owner can also create/enable/disable Doctor accounts in Accounts. Create shortcuts only after the existing-data preflight passes. Offline operation does not need internet once dependencies are installed.

## Features and permissions

Phone-first normalized Pakistani/international search with family-number selection, permanent patient IDs, medical alerts/reviews, dated clinical notes with autosave/revision conflicts, dental chart, staged treatment plans and private JPEG/PNG/passive-PDF attachments. Appointments/arrival/queue/visit linking, private tasks and Pakistan-midnight dashboard refresh. Doctor-authored prescriptions retain immutable issued snapshots and explicit void/replacement history; selected-document prints are white.

Exact Decimal charges/payments/corrections, installment allocations, receipt history and account closure preserve patient records. Doctor sees every individual patient's full clinical/financial history, outstanding individual balances and today's collections. Owner alone sees historical combined financial reports, expenses, exports, account administration and backup/recovery. Today pagination cannot select historical dates. Reports paginate display while totals/export cover the complete range. Read-only financial summaries use six bulk reads instead of per-account relationship queries; posting still rechecks under its financial lock.

Encrypted complete backups include original accounts/password hashes, business relationships, matching secret and attachments. Automatic backups use Windows-user DPAPI and run only while the app runs. Missing drives fail explicitly. A Google Drive folder save is not verified remote upload. Owner Backup & Restore shows destination availability, last verification/overdue failures, an honest unrecorded operational recovery status and remaining manual checks. Backup format/standalone recovery compatibility is retained.

## Verification and operating guides

- [DAILY_USE](docs/DAILY_USE.md): finding returning patients, notes, payments, daily backup checks and Start/Stop.
- [BACKUP_AND_RECOVERY](docs/BACKUP_AND_RECOVERY.md): encrypted backup, offline install/update, restore and interrupted-journal repair.
- [CLINIC_TRIAL](docs/CLINIC_TRIAL.md): reproducible test/performance commands and short Owner/Doctor checklist.
- [REQUIREMENTS](docs/REQUIREMENTS.md), [ROADMAP](docs/ROADMAP.md), [PROGRESS](docs/PROGRESS.md): exact contracts, actual verification and limitations.

Tests and browser/performance fixtures use isolated fictional data, generated credentials and ignored artifacts. Never commit patient screenshots, packages, databases, passwords or private logs. The GitHub workflow checks Linux and Windows; Windows exercises actual CMD/PowerShell launchers.

Physical USB/second-laptop recovery, actual cloud synchronization, printer output, native password/keyboard workflows, Windows reboot and clinic sign-off require user verification. Real power-loss behavior is not established by injected failures. No online deployment, arbitrary role editor, migration-export importer or historical receivable snapshots are included. Stop at Phase 6.
