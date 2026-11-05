# Phase 1 delivery record

Verified 6 November 2026 (Asia/Karachi). Phase 1 only; no online deployment.

## Starting state and completed work

The selected workspace was empty, was not a Git repository and had no applicable AGENTS.md instructions. No existing implementation was replaced. Git was initialized locally. No remote was configured.

Implemented Django 5.2.19 LTS with SQLite and fully pinned runtime dependencies. Python used: 3.13.5 on Windows. Local app/settings/templates/static assets are separated from runtime database and persistent secret. Default data location is `%LOCALAPPDATA%\RumiDentalCare`; validation used ignored `runtime\development` instead, without creating default clinic credentials.

Working features: Django login, POST logout, restricted Doctor role, owner Doctor creation/disable/enable, hidden-password account command, owner read-only audit page, idle expiry and persistent login throttles. Patient registration/edit/profile, permanent references, exact or approximate age with recording date, medical alerts and explicit unrecorded states. Shared normalization supports Pakistani equivalents and international E.164 numbers. POST search supports primary/WhatsApp numbers, partial numbers, names, patient numbers, pagination and shared-family selection. Duplicate warnings require review confirmation. Responsive local charcoal/blue/green interface, real patient count, Phase 4 appointment/task placeholders and honest future profile sections.

## Checks actually executed

| Check | Actual result |
| --- | --- |
| Install pinned packages in `.venv` | Passed: Django 5.2.19, phonenumbers 9.0.33, asgiref 3.13.0, sqlparse 0.6.1, tzdata 2026.6 |
| `manage.py makemigrations clinic` then `migrate` | Initial schema generated and all migrations applied successfully to ignored development database |
| `manage.py test -v 1` | **28 tests passed**, final full run 22.435 seconds |
| `manage.py check` | Passed: no issues |
| `manage.py makemigrations --check --dry-run` | Passed: no changes detected |
| `python -m pip check` | Passed: no broken requirements |
| `manage.py check --deploy` | Four expected loopback-HTTP warnings: W004 HSTS, W008 HTTPS redirect, W012 secure session cookie, W016 secure CSRF cookie. No warnings silenced; online deployment is not authorized/configured |
| Chromium/Playwright at 1440×1000 and 390×1000 | Passed complete login → fictional registration → alternate-country-format phone search → matching profile → edit → POST logout → anonymous profile denied |
| Browser privacy/layout | External requests blocked by test route; local CSS loaded; no JS errors; no horizontal overflow at either width; Doctor `/accounts/` request returned 403 |
| Visual review | Desktop and narrow patient-profile screenshots inspected; artifacts retained only in ignored `runtime/` |

Automated tests cover anonymous GET/POST denial, unassigned-user denial, Doctor patient permissions and owner/audit restrictions, owner Doctor creation and disable/enable, password validation, hidden-password command, patient create/edit, unique permanent references, actor/action audit entries, canonical phone equivalence and international formats, WhatsApp lookup, family sharing and duplicate confirmation, name/number search, pagination/minimum inputs, invalid phone/age/date values, approximate age recording-date preservation, CSRF enforcement and valid/foreign/null origins, HTML escaping, cache/privacy/security headers (including CSRF rejection), POST-only logout, idle expiry and login throttling/expiry.

Browser tooling already installed in a neighboring local environment was used only to execute `scripts/browser_check.py`; the app/server used this project's own `.venv` and pinned Django. No files in that neighboring project were edited. Browser tests used freshly generated temporary credentials and a temporary database, then stopped the server and removed that database. No default passwords or demo accounts remain in the application.

## Findings resolved

The first dependency download was blocked by sandbox networking; an approved network retry succeeded. Review found and fixed formatted international phone inputs being limited to canonical-storage length, and privacy headers missing on early CSRF rejection responses. The first real browser login exposed Chromium sending `Origin: null` with `Referrer-Policy: no-referrer`. Changed the policy to `same-origin`, preserving CSRF checks and preventing cross-origin referrer disclosure; added an origin regression test. A Windows console encoding issue in the browser check's status output was corrected to ASCII. The final full suite and both browser flows passed after these changes.

## Git handoff

Source and documentation are the only intended committed artifacts. `.gitignore` excludes runtime data, SQLite files/sidecars, secret files, environment files, uploads, backups, virtual environments and browser screenshots. Staged paths and contents are reviewed before the delivery commit. There is no Git remote, so no push or deployment is performed. README contains exact private `rumi-dental-care` repository creation/connection/push instructions. The resulting commit hash can be obtained with `git log -1 --oneline`.

The verified source was committed on `main` as `3ca2a87`. Final housekeeping also excludes Chromium diagnostic `.log` artifacts and documents Git's Windows sandbox ownership warning. Git writes required the normal Windows executor with an exact-repository, command-scoped trust exception; global Git trust settings were not changed. No diagnostic logs were committed.

## Limitations and blockers

No Phase 1 implementation blocker remains. Real clinic operation is not approved: backup/restore, reliable Windows installation and a fictional-data clinic trial remain outstanding. Tests do not establish clinical readiness, protection from a compromised Windows account, database encryption, tamper-proof auditing, or representative-volume performance. Do not enter real patient data yet.

No visit entry, dental chart, treatments, uploads, X-rays, prescriptions, financial transactions/reports, appointments/tasks, backup/restore or export is implemented. The future role and backup contracts are documented in REQUIREMENTS.md. HTTPS deployment checks intentionally remain outstanding for the separate future online stage. GitHub upload awaits creation of the user's chosen private repository.

## Exact next step

Stop Phase 1 here. On user authorization for Phase 2, define and implement an encounter model under each permanent patient record, with encounter date, Doctor, reason for visit, clinical findings and auditable clinical corrections; then add longitudinal medical history, dental chart, treatments and authorized local attachments. Preserve all future financial access rules, especially Doctor access to every individual patient's entire history. Keep testing with fictional data until Phases 5–6 gates pass.

## Phase 1 login incident and fix — 6 November 2026

The reported message is the generic `templates/500.html` response. An actual CSRF-valid HTTP login submission reproduced it. A temporary local-only `got_request_exception` receiver captured the traceback without POST data, passwords or frame locals; `DEBUG` stayed false. The exact exception was **`django.db.utils.OperationalError: no such table: clinic_loginattempt`**, originating at `ClinicLoginView.post`, the first `LoginAttempt.objects.filter(...).first()` query. This is the login-throttle read, before credential validation, session creation, audit recording or dashboard redirect.

Two sets of Django trial processes were active for the same loopback address. Selected process environment values established that one used the migrated `runtime\development` database and another, started without `RUMI_DATA_DIR`, used the empty default `%LOCALAPPDATA%\RumiDentalCare\clinic.sqlite3`. Windows address reuse allowed competing listeners. The existing Owner and Doctor were in `runtime\development`; that database had all 16 migrations applied. Owner was active/superuser; Doctor was active/non-staff/non-superuser with only patient add/view/change group permissions. No password reset or replacement database was needed.

Stopped only this project's competing/diagnostic trial servers and left one fixed server on `127.0.0.1:8000`, explicitly selecting `runtime\development`. The empty AppData database was preserved without migrations or replacement accounts. Temporary capture files, process diagnostics and preservation fingerprints remain under ignored `runtime/`; none are committed.

The source fix adds a guarded `runserver`, preserving Django staticfile handling and all authentication/CSRF/permission behavior. It rejects missing/empty databases and pending migrations before serving any requests, names the selected database in the local console, and explains how to select the existing directory. It never applies migrations or resets records automatically. The command's Windows socket uses exclusive binding to reject a competing listener. `clinic` precedes `staticfiles` in installed apps so Django actually selects this command. README now distinguishes the existing handoff trial from a new installation and uses an explicit data directory when resuming.

Verification after the fix:

- **33 tests passed** in 31.181 seconds, including five startup regressions: command selection/staticfile inheritance; empty database rejected; missing database not silently created; pending migrations rejected while fixture records remain byte-for-byte unchanged; and a second server cannot share the trial address. These tests include startup with `--skip-checks`, which cannot bypass the migration guard.
- Django checks passed; migration consistency reported no changes; dependency check passed; the existing clinic database had **zero pending migrations**.
- Real Chromium with separate incognito-style contexts passed Owner and Doctor login, dashboard, registration, alternate-format phone search, individual profile/edit, POST logout and anonymous denial at both 1440px and 390px. Owner account/audit access returned 200; Doctor access returned 403. These four flows used isolated fictional accounts and generated temporary passwords, not the user's existing passwords. The browser check leaves the clinic database untouched.
- The fixed server on port 8000 returned HTTP 200 with normal invalid-credentials validation for a CSRF-valid deliberately invalid login; no generic 500. Local CSS returned 200. A second socket bind to the active trial address was rejected.
- A private before/after fingerprint confirmed the existing usernames, password hashes, role flags, patient count and audit count were unchanged. No user password was obtained, printed or reset. Existing credentials were not independently entered by the automated browser check.

Only Phase 1 startup/verification/documentation changed. No Phase 2 work or online deployment occurred. Source is pushed normally to the existing `SalmanAliAqdas/rumi-dental-clinic-system` origin; the delivery response records the verified remote commit.

## Phase 1 Windows trial launchers — 6 November 2026

Added root-level **`Start Rumi Dental Care.cmd`** and **`clinic-shell.cmd`**. Both derive the project folder from their own location, change to it, set `DJANGO_SETTINGS_MODULE=config.settings` and `RUMI_DATA_DIR=<project>\runtime\development` only for their process/children, and invoke the existing `.venv\Scripts\python.exe` without activation or elevation. CMD files use Windows CRLF checkout endings. No global environment settings are changed.

Shared preflight checks require the Python executable, intended nonempty existing SQLite database, matching persistent secret, expected tables and all required migrations. SQLite inspection and migration planning do not initialize/repair data. Missing prerequisites or pending migrations produce instructions and a paused error window. Nothing installs dependencies, creates accounts, changes passwords or runs migrations automatically. The matching clinic shell opens real PowerShell with the same working directory/settings/data selection, preventing the previous new-terminal database mismatch.

The localhost server remains Django's documented Phase 1 development trial (`127.0.0.1:8000`, `--insecure`, no reloader). A temporary exclusive bind checks port availability; a TCP timeout is not mistaken for an occupied port. A loopback-only readiness endpoint accepts a random challenge and returns an HMAC proof bound to this checkout, Python and resolved database using the existing runtime secret. Responses contain no paths, patient/account data or secret values, and use private/no-store headers. Unknown/nonlocal/malformed requests are rejected. The launcher disables HTTP proxy use and redirects for its loopback probe. Readiness polling has a 15-second deadline and opens the default browser only after a correct proof. No unverified service is reused, killed or moved to another port.

The server runs in the launcher's visible console. Startup explains that the window must remain open, Ctrl+C stops the server, and closing the browser does not stop it. Verified existing servers are reused without spawning a duplicate; users are told to keep the original server console open. An older listener without readiness support must be stopped by the user from its own console before this launcher can verify/reuse it. This is **Phase 1 trial convenience only**; final operational packaging remains Phase 6.

Checks actually executed on Windows:

- **42 Django tests passed**, including nine new readiness/launcher tests. These cover signed loopback proof, rejection of malformed/nonlocal requests, pending-schema readiness, identity changes across checkout/database/Python/secret, environment selection from another directory containing spaces, verified reuse without another server, unknown-listener rejection without browser launch, bounded readiness polling and incorrect proof rejection. The prior startup/security/patient tests remained passing.
- `manage.py check`, `makemigrations --check --dry-run` and `pip check` passed. No new migrations or dependencies are required.
- `scripts/check_windows_launchers.py` passed using actual Windows CMD and PowerShell. It created/migrated only a temporary fictional fixture under ignored `runtime/`, linked to the existing venv; no clinic database was copied. Verified missing Python, missing/empty database, paused failure instructions, pending migrations without application, working-directory independence, paths containing spaces, wrong terminal environment overrides, resolved fixture database, matching PowerShell shell, readiness/startup, verified reuse without duplicate server, rejection of another Rumi checkout/database, and rejection of an unrelated listener even when it copied the application name. The check terminated only its own fixture process tree and removed its own junction/fixture.
- That integration check fingerprinted the actual clinic database and secret plus the unintended AppData database and secret before/after: **all byte-for-byte unchanged**. No real account password was obtained or changed.
- Four real Chromium flows passed: Owner and Doctor at 1440px and 390px, login → dashboard → register fictional patient → alternate-format phone search → profile/edit → POST logout. Existing authorization rules, local assets and layout checks passed. These browser tests used isolated generated accounts/passwords, not the user's existing passwords.
- Started the actual root CMD launcher from a different working directory in a visible normal-user console. It selected the existing project `runtime\development\clinic.sqlite3`. A second invocation verified/reused the same server. Process inspection confirmed one listener on **127.0.0.1:8000** with the launcher helper as its server process. The server remains running for manual trials.
- Actual desktop keyboard Ctrl+C interaction was not automated; its normal console shutdown path is retained from Django. Final service/startup resilience and live-data readiness remain Phase 6 work.

README now documents double-click start/stop, the matching clinic shell, explicit manual environment selection, launcher checks and opt-in Windows verification. Runtime data, secrets, private diagnostics, screenshots and fixture artifacts remain ignored. Only source/tests/documentation are included in the launcher commit. No Phase 2 work or deployment occurred. The final delivery records the normal push and remote-SHA verification.
