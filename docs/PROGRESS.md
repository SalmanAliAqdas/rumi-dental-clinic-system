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
