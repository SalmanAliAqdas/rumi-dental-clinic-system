# Rumi Dental Care — Phase 5 trial

Private, offline-first patient management for one dental clinic and one dentist in Lahore. The workflow is phone → matching patients → individual profile → dated visit → clinical history, treatment stages and private attachments. No online deployment, paid services, CDN assets or internet calls are used during everyday operation.

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

**Recovering an existing clinic? Do not run migrate/createsuperuser below to initialize replacement accounts. Install source/dependencies, then use the Phase 5 standalone recovery instructions before launching.** The initialization commands below are only for a genuinely new clinic with no existing records.

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

The command asks for and validates a hidden password. It assigns the fixed Doctor role: patient and clinical-record permissions, never staff, superuser, audit-write, export or deletion permissions. Local management commands are trusted workstation maintenance: restrict Windows access to the clinic owner. They are not public web endpoints.

Start the local trial:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --insecure --noreload
```

Open **http://127.0.0.1:8000/**. `--insecure` is Django's flag for serving this project's local CSS when `DEBUG=False`; patient views still require authentication. Bind to loopback only. Do not bind to `0.0.0.0`, publish this server, or configure a router tunnel. Stop with Ctrl+C. `runserver` is for development/trials; a reliable Windows service/startup package is Phase 6.

You do not need to activate the virtual environment or change PowerShell execution policy.

## Data and account maintenance

**Both launchers select the existing ignored `runtime\development` directory**, containing `clinic.sqlite3` and `secret.key`. The default in `config.settings` now selects that same project-relative directory when `RUMI_DATA_DIR` is unset; it no longer falls back to AppData. Existing explicit overrides still work. Use `clinic-shell.cmd` for maintenance so the settings, Python and directory always match. Never move only the database and leave its matching secret and attachments behind. Keep the secret private and retain it across restarts. Use a Windows account with a password, disk encryption where available, and private filesystem permissions; application roles do not protect against someone who can read the database file.

To choose another writable directory, set this before **every** management/start command, including migrations:

```powershell
$env:RUMI_DATA_DIR = 'C:\ClinicData\RumiDentalCare'
```

Do not switch directories accidentally: doing so opens a different clinic database. Implementation verification uses the existing `runtime\development` and isolated temporary browser data; no demo accounts are seeded into the clinic database.

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

It uses an isolated temporary database, random temporary password, loopback server and fictional data, then removes its database and stops the server. Screenshots go to ignored `runtime/`. It verifies both Owner and Doctor login, dashboard, patient search/edit and logout at desktop and narrow widths. Doctor flows also cover visit notes, persisted autosave, stale revisions, expired-session recovery, teeth, procedure, image upload/thumbnail, completion, amendment and return visit/history. It checks account/audit permissions and blocks external asset requests. It does not use or change your existing account passwords. Playwright is not needed to run the clinic application. See `docs/PROGRESS.md` for checks actually executed.

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

Patient responses have private/no-store cache controls, a same-origin referrer policy and restrictive same-origin CSP headers. Ordinary Django request/access logs are suppressed to avoid retaining URLs or patient terms. The audit database stores actor, patient/object references, action and timestamp, never copies of clinical text. It records clinical changes, completion/amendments, medical updates, treatment-plan changes and attachment upload/access. Dated medical snapshots, plan revisions and completed-visit amendments retain their clinical context in clinical tables. Trusted direct database/ORM maintenance can bypass application restrictions: this is **not tamper-proof**. Neither SQLite, uploaded originals nor the secret file is encrypted by this application. Encrypted complete backups and verified offline recovery are implemented; final operational trials remain Phase 6. Financial reports and CSV export are Owner-only.

Safe local diagnostics are bounded to a 256 KiB file plus three rotated files at `runtime/development/diagnostics/events.log`. Only a generated event ID, time, fixed category/severity, allowlisted exception type and application source locations are recorded. No exception message, request fields, passwords, patient text, SQL or locals are formatted. Generic 500 responses provide an `X-Rumi-Error-ID` header without showing details. A logging failure never falls back to printing the unsafe event.

## Git and source verification

Runtime files, virtual environments, secrets, SQLite sidecars, uploads and backups are ignored. Inspect `git status` and staged file names before each commit. Never include actual patient information in fixtures, screenshots, issues or Git.

The configured source repository is `https://github.com/SalmanAliAqdas/rumi-dental-clinic-system.git`. Source upload does not deploy the application. Check repository visibility separately; runtime privacy must never depend on GitHub visibility.

If Git reports **dubious ownership** because this repository was initialized under the restricted Codex Windows account, run this once from the project folder in your normal PowerShell. It trusts only this specific folder, not other repositories:

```powershell
git config --global --add safe.directory (Get-Location).Path
```

```powershell
git status
git remote -v
git log --oneline origin/main..main
git push origin main
```

GitHub Actions runs the complete Django suite, system checks, migration consistency and dependency checks on pushes and pull requests, with isolated temporary runtime storage. CI contains no clinic database, secret or account credentials.

## Try a returning patient (fictional data only)

1. Double-click **Rumi Dental Care** on the Desktop. Keep the original server console open, visit **http://127.0.0.1:8000/** and sign in with your existing `owner` or `doctor` account. Passwords have not changed.
2. Register a fictional patient, or find one by phone. `00442079` also matches an international phone beginning `+442079`; Pakistani alternate-format matching remains supported.
3. Open **Medical History** and record reviewed medicines, allergies, history and alerts using **Not recorded**, **None confirmed** or **Details recorded**. Use **Start Visit**, confirm that you reviewed the displayed context, and enter complaint, findings and diagnosis.
4. Select adult and/or primary FDI teeth; leave teeth empty and use area text for general work. Enter planned/performed treatment, advice, remaining work and follow-up. Watch **Saving / Saved / Failed**. Failed or conflicting saves retain the text in the current tab; do not close it until saved. No notes are stored in browser localStorage. After session expiry, sign in in another tab and retry.
5. Record a procedure from the editable example catalogue. On **Treatment Plans**, create a staged plan and link performed work across visits. Examples have no prices and are not clinical recommendations.
6. Upload a fictional JPEG, PNG or passive PDF under **Attachments**; optionally link its visit/teeth. Images have local thumbnails and authenticated previews; PDFs are download-only. Complete the visit after entering complaint and performed-treatment text. Its original notes are then retained; corrections use a dated amendment with a reason.
7. Search that patient again, start another dated visit (same-day visits are allowed), and retrieve the previous history, chart, treatment stages and attachments. Use **Continue Visit** for unfinished work. Log out when finished.

Medical snapshots and amendments are dated records, not a clinical decision system. Visit/medical/treatment timelines are paginated; the chart summarizes the latest 50 performed records and the complete history remains in Visits. Catalogue entries can be edited/deactivated; already recorded procedure labels are retained.

## Phase 2 storage and upgrade

The existing laptop database has migrations `0002` and `0003` applied. Do not reinitialize it. After stopping the known server, future upgrades should make and verify a safety copy before applying reviewed migrations:

```powershell
# Open clinic-shell.cmd first; stop the known server in its own console.
.\.venv\Scripts\python.exe scripts\safety_copy.py
.\.venv\Scripts\python.exe manage.py showmigrations --plan
.\.venv\Scripts\python.exe manage.py migrate
```

The helper copies the consistent SQLite database with its matching secret to ignored `runtime/development/safety-copies/<UTC-id>/`, checks readability, foreign keys and all table rows, and writes a manifest. It assumes writes are stopped. It is **not** the Phase 5 encrypted, complete, off-device backup/restore system and does not copy uploads.

Generated originals live at `runtime/development/attachments/originals/`; replaceable image thumbnails at `attachments/thumbnails/`; temporary upload files at `upload-tmp/`. Uploads are limited to 10 MiB, images to 10,000 pixels per side/25 million pixels, and passive PDFs to 200 pages with bounded structure checks. Extension and actual content must agree; active/encrypted/malformed PDFs and unsupported formats are rejected. All original, thumbnail and preview routes require authentication and permission; there is no public media route. Missing files produce a safe unavailable response while their metadata is retained. Upload failures clean up newly created files; power-loss orphan reconciliation and full restore testing remain future work. Future complete backups must capture the database **and every uploaded original together**, plus needed configuration and a verified manifest.

Phases 3-5 are implemented below. Final packaging and clinic trials remain Phase 6. See [requirements](docs/REQUIREMENTS.md), [roadmap](docs/ROADMAP.md) and [progress](docs/PROGRESS.md).


## Phase 3: charges, payments and installments

Open a patient by phone, then **Payments > New treatment account**. Each returning course of treatment can have a separate account without creating another patient. Record the agreed total through one or more **Record Charge** entries. Link an existing plan item or visit where appropriate; a plan item may be charged only once across all accounts. Subsequent visits do not create charges automatically. Clinical completion and financial settlement are separate.

**Receive Payment / Pay in Full** supports both full and partial amounts without a visit. Choose Cash, Bank transfer or Easypaisa. There are no card payments or external services. Use the suggested remaining amount for full payment, or enter the partial amount. A printable individual receipt follows a successful payment; use the browser Print command. Receipt balances distinguish the balance immediately after posting from the current balance and show later corrections.

### Test the PKR 10,000 example with fictional data

1. Find a fictional patient by phone, open Payments and create an account named "Fictional installment trial".
2. Record Charge: PKR `10000`, with an agreed-treatment description.
3. Receive Payment: PKR `3000`, method Cash. Return from the receipt; remaining balance is PKR `7000`.
4. Choose Installment Plan, enter agreement notes and two lines: `2000 | | First installment` and `5000 | | Final installment`. The blank middle field means no due date was agreed. Optionally enter an actual agreed date as `YYYY-MM-DD` between the separators.
5. Receive PKR `2000`; remaining balance is PKR `5000`. The first installment is paid. Receive the final PKR `5000`; remaining balance is zero and both installments are paid.
6. Choose **Full Payment Received & Close Account**, give a reason and save. Closure creates an account event, never a second payment. The account leaves the default Outstanding payments list. Reopen the patient's Payments tab to see its complete closed history and all three receipts.
7. As Doctor, `/finance/today/` shows today's final payment too. `/finance/reports/` and `/finance/export/`, including direct historical URL parameters, return 403. As Owner, open Financial reports and choose daily, Monday-Sunday weekly, monthly, annual or custom dates.

### Calculation, permissions and corrections

All amounts use Decimal with two decimal places; positive entries only. Zero, negatives, nonfinite values, excess precision and accidental overpayment are rejected. Remaining balance = original charges - charge reversals - approved discounts/write-offs - gross payments + refunds/payment reversals. Discounts and write-offs are never counted as cash. Original charges, explicit reversals and every posted entry remain visible. Financial state changes serialize through a first-statement SQLite write reservation inside an atomic transaction; state is reread after acquiring the lock. Unique form submission tokens and receipt references prevent duplicate posting on double-click/retry. A busy-database response preserves the token and asks for a retry.

Doctor can read every individual patient's financial history, including old closed accounts, create charges, record today's payments, set an initial installment agreement, request corrections and use the individual outstanding list. The list includes patient/contact/account, individual balance, due date and actions, with no combined monetary totals in its template context. Doctor cannot backdate, revise schedules, approve corrections, reopen accounts, view combined past reports, manage expenses or bulk-export. The server forces Doctor receipt time to now regardless of submitted fields. Access follows the existing fixed Doctor patient permission and Owner superuser role; no roles/passwords are changed.

Owner can approve discounts/write-offs, refunds and full original-entry reversals with reasons. Refunds link to the original payment, use its method and cannot exceed its uncorrected remainder. Full reversal requires the entire uncorrected original; a previously refunded payment cannot also be fully reversed. A charge reversal or reduction cannot produce a negative balance. Doctor correction requests remain Pending until Owner explicitly approves a reversal or rejects with a reason. Re-enter any corrected replacement transaction separately; originals are retained. Closed accounts must first be reopened by Owner with a recorded reason. Adjusted settlements are labelled separately and only Owner can close them.

Installment rows must sum exactly to the current remaining balance when agreed. Payments allocate oldest schedule rows first, including partial and multiple-row payments; allocations are not additional collections. Refunds/reversals release allocations from the last row backwards. Due dates are optional; overdue means unpaid and before today's Pakistan date. Revisions are Owner-only, retain previous agreements/allocations and cover the then-remaining balance. Charges/discounts/charge reversals or refunds beyond current-schedule allocations invalidate that agreement as the current schedule; its history remains visible and Owner must agree a replacement. The UI never presents such an old agreement as the current amount payable. Early full payment completes all remaining scheduled rows without changing due dates.

Today's collections and reports use **Asia/Karachi midnight inclusive through next midnight exclusive**, independent of server UTC. Today accepts no date/filter/pagination parameters. Owner reports separate net charges, approved noncash reductions, gross receipts, refunds/payment reversals, net collections, net expenses and **net cash movement** (net collections minus net expenses). Net cash movement is not accounting profit. Method totals are net collections for cash/bank/Easypaisa. Current receivables and overdue installments are explicitly **as of today**, even when the selected cash-flow range is historical; historical receivable snapshots are not provided. Expense corrections are immutable linked reversals with reasons and actor/time; enter a replacement separately. CSV includes financial entries/expenses and summaries, no clinical notes, and neutralizes spreadsheet formulas.

### Migration and verification

Migrations `0004` and `0005` add finance tables and the serialization row. Before applying to this checkout, its identified server was stopped; an exclusive SQLite check confirmed writes were paused. `scripts/safety_copy.py` created and verified a consistent database and matching-secret copy under ignored `runtime/development/safety-copies`. All original rows (including login hashes and roles) were compared after migration; original uploads and secret were fingerprinted unchanged. This local safety copy is **not** the complete Phase 5 backup system.

`manage.py test` now includes financial arithmetic, role boundaries, refunds/corrections, schedules, reports and two independent file-backed SQLite posting processes. `scripts/browser_check.py` also runs the entire example for both roles at desktop/narrow widths with isolated fictional data. Existing launchers/shortcuts still select `runtime/development`. See `docs/PROGRESS.md` for actual results. Runtime dependencies are unchanged; development browser tooling is optional.

Phase 3 financial rules remain unchanged by Phase 4. Continue fictional-data use until backup/restore and clinic trials pass. Large-volume financial query performance, physical receipt/printer testing and power-loss/recovery trials remain future verification; this is a single-workstation trial.


## Phase 4: appointments, next patient, personal tasks and prescriptions

Use the existing desktop shortcut to open the local app. Phone search remains central. Each search result and patient profile now offers **Book appointment** and **Register walk-in**; Schedule also links to new-patient registration. Patient Appointments shows the complete booking history. Schedule provides today, previous/next day, chosen date and upcoming views, in Pakistan time.

Enter start/end, purpose and optional notes. End must be after start. Active Scheduled/Arrived/In Treatment bookings are checked for overlap under a SQLite write reservation; touching end/start times are allowed. An overlap first blocks saving with a clear warning. To save intentionally, review the schedule, check the explicit overlap confirmation and provide a reason. Cancelled/No-show/Completed bookings do not block times. Rescheduling, status changes, walk-in arrival and explicit queue ordering retain actor/time/reason and before/after details. No status changes automatically when time passes. Single-dentist operation permits only one In Treatment appointment at a time. Reactivating a terminal booking checks overlaps again.

The dashboard right panels show current patient, **Who's next**, arrived queue, today's remaining bookings and overdue unresolved bookings (including earlier days). Arrived patients come first by queue ordering time, initially their arrival time, then arrival time and ID for ties. An explicit queue-time adjustment on Change Status requires a reason and is retained in history. Otherwise next means the earliest not-yet-past Scheduled booking today. Past Scheduled bookings remain separately overdue until a person changes their status. No-show and cancellation are explicit decisions.

**Mark Arrived**, **Start Visit**, **Change Status** and **Open Patient** are available from the dashboard/booking. Start Visit requires review of medical history/alerts, optionally links an existing editable same-patient visit, and otherwise creates a visit once. Repeated/concurrent requests reuse that appointment's link. Appointment completion never completes, edits or signs clinical notes. The original walk-in clinical Start Visit remains available separately.

Use **Refresh today & tasks** for current data. A small local script checks the Pakistan date every 15 seconds and refreshes only the panels at midnight, preserving phone-search input. It does not continually poll the server or extend an idle session. A failed/unauthorized refresh clears old panel data; a local idle-expiry timer clears panels and returns to sign-in. Normal server session/permission checks still guard every refresh. With JavaScript disabled, use the explicit Refresh/Today link to load the current day. Narrow layouts put the panels below the main workspace.

**My tasks** is private to the signed-in creator, including from Owner accounts. Add/edit notes and optional due time, complete or reopen. Unfinished tasks carry forward with original dates; completed history remains available separately. Tasks are not appointments. Revision checks and submission tokens prevent lost updates and duplicate writes. No recurring jobs or external notifications are implemented.

### Prescriptions and print identity

Open patient **Prescriptions**. Only an active account in the fixed Doctor role with clinical creation permission can draft/issue; Owner-only accounts can view/print but cannot prescribe or choose another person's identity. A dual-role Owner/Doctor must explicitly have the Doctor group and still prescribes only as the signed-in user. Under **Your clinician print details**, enter your actual name and any actual optional qualifications/registration/contact; nothing is invented. Owner configures clinic name/address/contact under **Clinic print details**. No logo, signature or registration defaults are supplied.

Doctor drafts contain date, optional same-patient visit, medication name, strength/form, dose, route, frequency, duration, quantity/instructions, advice and follow-up. All text is entered/reviewed by Doctor. Drafts can remain incomplete. Save a draft, then choose Edit draft/add medication to get another blank row (maximum 20); rows can be removed explicitly. Issue requires medication name/dose/route/frequency/duration for each row, your own clinician print details and explicit patient/allergy/content/identity confirmation. No doses, diagnoses or advice are generated or recommended.

Issuance retains a snapshot of patient identity/age context, clinician, clinic details, date and all content. Later patient/config edits do not change that print snapshot. Issued originals cannot be edited through the app. **Void / replace with reason** retains the original and creates an explicit linked void record, optionally with a replacement draft under the correcting signed-in Doctor's identity. The original is marked void immediately; a replacement needs its own review/issuance. Both remain in patient history. Draft and void print layouts are prominently labelled. Appointment and prescription prints are standalone white documents containing only the selected patient/document. Use browser Print / Save as PDF; no PDF service or invented signature is used.

### Manual reminders

Prepare Reminder shows a short clinic-name/date/time reminder without patient name, purpose, diagnosis, treatment, money or attachments. Review/copy it. The saved validated WhatsApp number is preferred; if absent, explicitly confirm the primary phone before enabling the link. **Open WhatsApp** is an explicit external navigation requiring internet; the app itself sends nothing. Merely viewing/opening does not log a send or delivery. Only a user's explicit Copied or Manually sent confirmation is recorded, with actor/time/recipient and appointment time. It never represents a delivery receipt. Core operation remains offline.

### Try the new dashboard with fictional data

1. Doctor: find a fictional patient by phone, choose Book appointment, set a future start/end and purpose, save, then open Dashboard.
2. Mark Arrived and give a reason. Confirm the patient moves into the arrival queue. Start Visit, review the alerts and save; retrying the appointment link reopens the same visit.
3. Open Prescriptions, configure your actual clinician print details, draft fictional medication text and save. Review and issue with explicit confirmation; open the white print preview and browser Print / Save as PDF.
4. Return to the appointment, change status to Completed with a reason. Confirm clinical notes remain an independently editable In Progress visit.
5. Add/complete a personal task; use Completed history to reopen it. Log in as another user and confirm that task is absent and its direct URL is denied.
6. Owner-only: view/print the prescription and historical financial reports; prescription creation/issuance is denied. Doctor financial report/export restrictions remain unchanged.

Migrations 0006-0007 are additive. The known clinic server was paused before a verified consistent database/secret safety copy; every pre-existing row and uploaded-file/secret fingerprint was compared after applying only to `runtime/development`. That limited safety copy is separate from Phase 5 backup/restore below. Verification results and exact limitations are in `docs/PROGRESS.md`. Continue fictional data until operational clinic trials pass.


## Phase 5: complete encrypted backups and verified recovery

Owner opens **Backup & Restore**. Doctor is denied settings, packages/downloads, verification/restore and bulk migration exports on the server. No real recovery password or destination has been configured on your behalf. Choose your own password and folders; test first with fictional data.

### First backup setup and daily use

1. In Windows Explorer, create/select an existing backup folder **outside** `runtime/development`, for example a project `runtime/backup-packages` folder or a folder on your USB drive. Copy its full absolute path. Add destination in Backup & Restore, give it a clear label, select Local/External/Google Drive folder, and paste that path. Missing/unwritable/disconnected drives never fall back to another folder. Multiple destinations are supported independently.
2. Choose **Back Up Now**, enter/confirm a strong recovery password (minimum 12 characters), and Continue. A background job reserves a coordinated write pause only for SQLite snapshot and attachment copying; concurrent writes receive an explicit retry response. Encryption, verification and destination copying run separately. Watch the job's **per-destination** results. Only a complete verified file is successful; partial local/external results remain distinct.
3. Use **Verify Backup** with the generated encrypted package's full path and recovery password. This checks it without replacing working data. Keep the recovery password in a separate password manager/off-device record. **Losing it prevents recovery.** Do not store the only password record on the laptop being backed up.
4. Configure **Automatic settings** for daily Pakistan time and retained versions (2-365, default 7). Enter the recovery password once for automatic use; it is saved only with **current Windows user-bound DPAPI**, never plaintext. Run the app as that same Windows user. If DPAPI is unavailable/unreadable, automatic backup fails with a clear warning; reconfigure it after moving computers/users. Manual portable recovery needs the recovery password, not DPAPI or the failed laptop's secret.
5. Backups run **only while this app/server is running**. Startup and minute checks find the latest due daily slot; a missed slot creates a snapshot of data **now**, with the actual creation timestamp, not an invented past snapshot. Successful destinations are not duplicated for that slot; disconnected destinations retry separately. Check missing/overdue/failure warnings and the latest file's availability. Do not assume a hidden/background server runs after Windows shuts down.

Each versioned `.rumibak` includes a supported SQLite backup snapshot, every original and thumbnail, matching `secret.key`, allowlisted portable upload limits/timezone, migration/schema metadata, row counts and a size/SHA-256 file manifest. Accounts/password hashes, roles, permanent IDs, all clinical/financial/workflow data, business settings and database audit history are retained. Source, virtual environments, sessions-in-memory, diagnostics, temporary work, earlier backups and machine-specific DPAPI/destination/job configuration are excluded. Database sessions inside the snapshot are cleared when restored. Reconfigure destinations/automatic credentials on the new computer. Business print/clinician settings in the database are preserved.

Packages use [cryptography](https://cryptography.io/en/stable/hazmat/primitives/aead/) AES-256-GCM authenticated encryption with a random nonce/salt and [Argon2id](https://cryptography.io/en/stable/hazmat/primitives/key-derivation-functions/#argon2id) password derivation (64 MiB, 3 iterations, 4 lanes). Parameters are fixed/bounded by package version; the password is not a command argument or plaintext setting. The format is an authenticated encrypted container, not a password-protected ZIP. Plaintext temporary staging stays local under the private runtime work area and is removed on normal completion; this does not encrypt the live runtime or promise secure erasure after power loss. Do not synchronize the live runtime/staging folder.

### External drives, Google Drive folders and retention

Keep at least one external/off-device copy and rehearse recovery. **Another partition on the same physical disk does not protect against disk failure.** A destination labelled External is the folder you selected; the app cannot establish that it is a physically independent disk.

Google Drive mode uses an **existing synchronized folder** and requires a separate existing **unsynchronized staging folder on the same volume**, outside the destination tree. Encrypted temporary output stays there; only completed verified encrypted packages are atomically moved into the selected sync folder. You must choose a staging folder not watched by a sync client; the app validates path/volume boundaries, not Drive's client configuration. Unsupported virtual/streamed-drive rename behavior fails instead of silently substituting a location. The result says **Saved to Google Drive folder**. Google Drive Desktop plus internet are needed for synchronization. Local saving is **not verified cloud upload or remote protection**. No OAuth/API integration was added.

Completed copies are read/verified before success. Free-space checks, temporary names and atomic finalization handle normal errors/disconnections. Retention prunes only positively recorded packages from this installation/destination with matching checksums, preserves at least the newest two present good versions, ignores unrelated/changed files and never prunes after a failed/partial new job. It does not recursively clean a drive. Interrupted `.part`/work directories can remain after abrupt termination; they are not successful packages. No power-loss durability claim is made.

### Restore onto this or another laptop

The web Restore action requires the current Owner password and explicit confirmation, then provides a verified preview/instructions. **It never replaces an active database in a request.** Actual activation is done by the local helper with the intended server stopped. A running guarded server holds a cross-process lease and blocks replacement. Existing runtime replacement also requires active Owner username/password at the helper; new-computer recovery requires the package password and explicit confirmation without creating default accounts.

1. Install compatible project source, Python and this `requirements.txt` into its `.venv`. On a new computer with no initialized database, **do not run createsuperuser or initialize a substitute database**.
2. Copy the encrypted `.rumibak` outside the directory to be restored. Choose the data directory explicitly. To use the existing desktop shortcut/CMD launchers, choose **this checkout's `runtime/development`**. Those launchers intentionally always select that directory.
3. Verify first (the password prompt is hidden in an interactive terminal):

```powershell
.\.venv\Scripts\python.exe scripts\recovery.py verify --package "E:\RumiBackups\selected.rumibak"
```

4. Stop only the intended Rumi server. Restore after reviewing date/schema and the explicit replacement target:

```powershell
.\.venv\Scripts\python.exe scripts\recovery.py restore --package "E:\RumiBackups\selected.rumibak" --data-dir "C:\path\to\rumi-dental-clinic-system\runtime\development"
```

Enter the recovery password, existing Owner credentials when replacing an initialized runtime, and `RESTORE` at confirmation. Passwords are not accepted as CLI arguments. The helper also supports private redirected input for fictional automated drills without Windows console echo/credential arguments. It rejects wrong passwords, corruption, unsafe paths/links, excessive resources, unsupported future schemas and inconsistent migration/table definitions. Known older supported schemas are migrated **only in staging using trusted checkout code**; the original package remains unchanged. It never imports/runs code from the package.

Activation retains a checked pre-restore runtime in a sibling rollback directory, closes its SQLite handles, switches the entire staged database/secret/attachments directory together, probes it and clears sessions. A normal activation failure recovers the old directory. An interruption journal blocks normal startup before secret/database initialization; after stopping servers, use:

```powershell
.\.venv\Scripts\python.exe scripts\recovery.py repair --data-dir "C:\path\to\rumi-dental-clinic-system\runtime\development"
```

Repair requires local confirmation and the existing/rollback Owner credentials where available. Do not manually delete the journal or overwrite the only rollback copy. Rollback/failed-stage directories are local runtime data, not encrypted off-device backups; preserve them until recovery is checked. This design was tested for injected activation failure and interrupted-journal repair, **not real power loss**.

5. Launch with the existing shortcut and sign in with the **restored original credentials**. No account bypass/reset is performed. Verify phone search, complete histories, balances, appointments, prescription prints and images. Reconfigure destinations/automatic credentials on the new Windows user/computer. If you intentionally restored to another data directory, use explicit `RUMI_DATA_DIR` plus `manage.py runserver` as documented above; the root shortcut will still select `runtime/development` and must not be mistaken for that other installation.

### Portable migration export and verification limits

Owner **Encrypted migration export** produces a `.rumiexport` with versioned Unicode `records.json`, safe CSV tables, field/foreign-key dictionary, stable PK/FK IDs and an attachment mapping/files/checksums. It includes every business module from Phases 1-4. Password hashes, application secret, sessions, login-throttle state and DPAPI credentials are excluded. Decimal money is written as fixed-precision text. CSV formula cells are neutralized; JSON preserves original values. **This is not a login-preserving disaster-recovery backup and cannot be restored as one.** No migration importer is implemented.

Current strict limits: 8 GiB encrypted/expanded package, 2 GiB per file, 100,000 entries, 16 MiB manifest, and 15 MiB structured migration records. Oversize/unsupported content fails clearly; no partial export is marked successful. Archives use stored files, so compressed archives, symlinks, unexpected paths, executable files and compression bombs are rejected. Enough local working space for snapshot/encryption/decryption/staging is required. Bulk-volume work and reliable operational packaging remain Phase 6.

`manage.py test` covers backup/recovery permissions, consistency, corruption/resource cases, destinations, scheduling/retention, full restoration and exports. `scripts/recovery_drill.py` creates only isolated fictional clinical/financial/workflow data, invokes the standalone helper to a clean directory and verifies original logins/relationships/file checksums. `scripts/backup_ui_check.py` is the optional Playwright backup-only UI check; the full browser script includes it too. The maintainer-only `scripts/generate_backup_schema.py --write` regenerates public schema metadata from fresh trusted migrations, never from patient data, when supported migrations change. See PROGRESS for actual runs and limitations.

Phase 5 stops here. Final Windows packaging, physical off-device/restore trials, power-loss behavior and operational clinic sign-off remain Phase 6. Continue **fictional data only** until those gates pass.
