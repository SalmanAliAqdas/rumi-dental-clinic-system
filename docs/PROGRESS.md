# Phases 1–2 delivery record

## Phase 2 delivery — 6 November 2026

Implemented dated visits with multiple same-day encounters, clinician, clinical fields, tooth/area selection, follow-up and draft/in-progress/completed states. Conditional revision updates prevent stale overwrites. Local JavaScript serializes autosaves, visibly reports Saving/Saved/Failed, retains failed edits in the tab, refreshes CSRF after reauthentication and waits for in-flight saves before explicit completion. Completed notes retain their originals; corrections require dated, authored, reasoned amendments. Notes are not stored in localStorage. Unsaved browser-tab loss remains a limitation.

Added dated medical reviews with Not recorded / None confirmed / Details recorded states and a fresh immutable medical-context snapshot on each visit. Existing profile medical changes also retain before/after reviews. Added validated adult and primary FDI multi-tooth/general-area charting, observations, editable no-price example procedure catalogue, staged treatment plans with revision snapshots, and performed procedures linked across visits. Recorded procedure labels survive catalogue renames.

Added local private JPEG/PNG/passive-PDF attachments, actual-content parsing/resource limits, generated filenames, original-byte preservation and separate image thumbnails. Authenticated download/preview/thumbnail routes enforce permission and patient linkage; no public media route exists. PDFs are download-only; active/encrypted/malformed PDFs are rejected. Missing files retain metadata and report unavailability. Ordinary upload failures remove newly written files and roll back metadata. Abrupt power-loss reconciliation is not implemented. Originals, thumbnails and SQLite remain unencrypted local runtime data.

Patient sections now provide Overview, Visits, Medical History, Dental Chart, Treatment Plans and Attachments with Start/Continue Visit actions, identity and prominent medical alerts. Timelines paginate at 20; the chart shows the latest 50 performed records with full visit history available separately. Prescriptions and Payments remain explicitly pending. Clinical audit events contain IDs/actions/actors/times, not notes. Application immutability and auditing are not tamper-proof against trusted database/ORM access.

### Migration and preservation

Stopped only the identified project trial listener before migration. `scripts/safety_copy.py` used SQLite's backup API to make an ignored database + matching secret copy at `runtime/development/safety-copies/20261105T231601Z-f68ef942/`. Verified readability, foreign keys, all table rows and matching secret, then compared the source again before applying reviewed additive migrations `0002` and `0003`. This same-laptop safety copy is not the complete Phase 5 backup system and does not contain attachments.

Applied both migrations to the intended existing `runtime/development/clinic.sqlite3` (18 migrations total). Verified all original Patient rows/identifiers (zero patients existed), both account rows including password hashes/active and role flags, audit rows and user/group memberships were preserved. Existing group-permission links remain; fixed clinical Doctor permissions were added. The matching secret is unchanged. Integrity and foreign-key checks passed. No replacement accounts or password resets were performed. Six labelled procedure examples contain no prices. New tables/relationships and attachment paths are documented in REQUIREMENTS.md.

The default data path now agrees with the launchers even when `RUMI_DATA_DIR` is unset: `<project>/runtime/development`. The unintended AppData database is preserved without initialization. Existing desktop shortcut, root CMD names, local readiness proof, CSRF, permissions and login throttling remain intact.

### Checks actually executed

- **66 full Django tests passed** in 39.414 seconds. Existing tests remain passing. Added coverage for role/anonymous/unassigned denial; same-day visits; database-persisted drafts; stale HTML/JSON requests; expired sessions; completion/amendment originals and escaping; medical snapshot retention; adult/primary/general teeth; cross-patient links; staged plans across visits; catalogue renaming; private image/PDF routes; spoofed, malformed, unsupported, oversized and unsafe-name uploads; missing files; upload rollback; CSRF/audit/private headers. Review regressions cover international search, diagnostic sensitive-data exclusion, rotation/write failure and an actual generic 500 with correlated error ID.
- Django system checks, `makemigrations --check --dry-run` and `pip check` passed. Pillow and pypdf dependencies are pinned. GitHub Actions runs the same checks using isolated temporary runtime storage; final push/CI status is recorded in the delivery response.
- The first push exposed a GitHub workflow-validation error before jobs ran: `Unrecognized named-value: 'runner'` for job-level `runner.temp`. Corrected CI to export `RUMI_DATA_DIR` from the runner's `RUNNER_TEMP` in an initial step through `GITHUB_ENV`. This source-only follow-up does not alter the running clinic or its data; final delivery reports the replacement run's actual result.
- Real Chromium: Owner and Doctor login, dashboard, fictional registration, alternate-format phone search, profile/edit and POST logout at **1440px and 390px**. Both Doctor widths also passed notes/FDI selection, autosave verified against SQLite, stale-tab text retention, expired-session failure and reauthentication/retry, procedure recording, fictional image upload/rendered thumbnail, completion, amendment, return visit and previous-history retrieval. External assets were blocked; no JavaScript errors or horizontal overflow were found. Screenshot inspection confirmed the narrow completed-visit layout. Tests used isolated generated accounts and temporary passwords, never the existing user's passwords or clinic records.
- Actual Windows CMD/PowerShell launcher integration passed: paths with spaces, another working directory, terminal overrides, missing Python/database, pending-migration refusal without mutation, matching clinic shell, readiness, verified reuse, another-checkout rejection and conflicting occupied port. Updated the fixture to restore all migration markers after its pending-migration test, rather than assuming only one clinic migration. Actual clinic and unintended AppData database/secret fingerprints were unchanged across this integration check.
- Desktop-shortcut fixture checks passed: Windows paths with spaces, exact target/working directory, normal window, built-in icon, no credentials/elevation, same-installation repeat, and preservation of a conflicting installation/custom arguments. Generated shortcuts remain ignored.
- Opened the laptop's existing Windows-resolved desktop shortcut after checking its exact launcher target, project working directory and empty arguments. Its visible console started the application; signed readiness verified the existing `runtime/development/clinic.sqlite3` at `http://127.0.0.1:8000/`. The server is left running for manual testing. The 20 clinical tests were rerun successfully in 6.355 seconds after explicitly clearing thumbnail metadata; the image test proves original-byte retention and private EXIF removal from the thumbnail.

### Manual trial and limits

Double-click the existing **Rumi Dental Care** desktop shortcut, open **http://127.0.0.1:8000/**, and use existing `owner` or `doctor` credentials. Follow README's returning-patient trial: fictional patient → medical review → Start Visit → save notes/teeth → record procedure → upload fictional image → complete → start return visit → retrieve earlier history → logout. Keep the original console open; Ctrl+C stops it and closing the browser does not. Use `clinic-shell.cmd` for maintenance with the same settings/database. The Phase 1 trial launcher remains trial convenience; operational packaging is Phase 6.

Only fictional data is approved. No finance, prescriptions, appointments, encrypted/off-device complete backups, restore drills, production Windows service, representative-volume clinic validation or online deployment is delivered. Upload scanning is format validation, not a malware-scanning service or DICOM viewer. Keyboard Ctrl+C itself was not automated. Exact next step: stop after Phase 2 and await explicit Phase 3 authorization. Do not enter real patient data until the Phase 5–6 gates pass.

## Phase 1 review fixes before Phase 2

Corrected partial international phone prefixes: all leading `00` country-code prefixes now map to the same canonical fragment as `+`, preserving Pakistani normalization and minimum input lengths. Added regression coverage for UK partial/full variants.

Added allowlisted local diagnostic events under the selected runtime `diagnostics/events.log`: UTC time, random event ID, fixed category/severity, allowlisted exception type and up to eight application source-file/line locations. Never formats exception messages, log messages/arguments, requests, passwords, query strings, bodies, clinical text or frame locals. A 500 response can carry the corresponding opaque `X-Rumi-Error-ID`; browsers retain generic errors and DEBUG stays false. Retention is one 256 KiB active file plus three rotations (approximately 1 MiB). Logging failures do not print the original record. Diagnostic files remain ignored. Tests exercise sensitive payload exclusion, bounded rotation and write failure.

Added GitHub Actions checks for the complete test suite, Django checks, migration consistency and dependency consistency on Python 3.13, using only a runner-temporary data directory and fictional test data. These review fixes are committed separately before Phase 2 schema/application work. Verification results and the review commit are recorded in the final Phase 2 delivery below.

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

## Phase 1 desktop shortcut — 6 November 2026

Created **Rumi Dental Care.lnk** on this laptop's Windows-resolved Desktop. It targets the existing root `Start Rumi Dental Care.cmd`, sets the project working directory, uses a normal visible window, has empty arguments, and has no RunAs/elevation flag. No credentials or authentication bypass are included. No suitable local clinic icon exists; the shortcut uses the built-in blue Windows PowerShell console icon as a trial application icon, not an official clinic logo. No assets were downloaded or generated.

Added root **Setup Desktop Shortcut.ps1**. Its project directory comes from its own location; Desktop comes from Windows `DesktopDirectory` special-folder resolution, respecting OneDrive/redirection. No hardcoded user path, elevation, global environment/registry changes, database operations or account changes are performed. Setup creates and verifies a fresh temporary shortcut before placing it on Desktop. Same-installation reruns update the shortcut; another target or custom arguments cause a conflict and leave the existing file unchanged. After moving the project, rerun setup from its new folder; review and manually rename/remove a conflicting old shortcut rather than automatically overwriting another installation. Added `*.lnk` to `.gitignore`.

Windows verification actually run:

- `scripts/check_desktop_shortcut.ps1` passed against isolated Desktop/project fixture directories containing spaces. Verified exact launcher target, working directory, empty arguments, normal window/icon and same-installation rerun.
- A fixture shortcut targeting another existing installation caused a conflict and remained **byte-for-byte unchanged**. A shortcut with custom arguments was also preserved without displaying those arguments. Fixtures were cleaned up only after checking their resolved boundary inside ignored `runtime/`.
- Actual laptop shortcut creation succeeded using the current user's Windows-resolved Desktop, and its saved target/working directory/icon/window style/empty arguments and no-elevation flag were inspected.
- Opened the actual `.lnk` through Windows shell execution. After an initial verification attempt raced two launcher invocations, the sequential retest passed: fresh desktop launch produced the signed ready response for the existing clinic database; a second desktop invocation retained the same server listener; anonymous entry returned HTTP 200 at `/login/`. No sign-in bypass or password entry was involved. The visible trial console remains running for manual use.

Only shortcut setup, its Windows fixture check, Git ignore rules and documentation changed. Application logic, records, passwords and login protection were not modified. No Phase 2 work or deployment occurred. The final delivery records the normal source/documentation push and verified remote commit; generated `.lnk` files are not committed.
