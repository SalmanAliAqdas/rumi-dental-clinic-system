# Confirmed requirements

Private business software for Rumi Dental Care, Lahore, Pakistan: one branch, one dentist, no receptionist. Daily workflow: phone → matching patients → complete individual profile → today's visit → reliable retrieval years later. Windows offline operation comes first. Phases 1-5 are implemented as a fictional-data trial. Online deployment is a separate future stage.

## Stack and local operation

Django 5.2 LTS on supported Python, SQLite, Django templates, local CSS and minimal local JavaScript for revision-safe draft saving. Pillow validates images; pypdf validates passive PDFs. Use Django authentication, password validation/hashing, permissions, sessions, CSRF, ORM and migrations. Pin dependency versions. Separate runtime data and settings from source. No external APIs, Neon, Vercel, Supabase, paid services, CDN scripts/styles or remote fonts. Network access is for initial dependency installation only.

## Exact role contract

Owner/Administrator:

- Full application access.
- Account and permission management.
- All individual and combined financial records and reports.
- Backup, restore, export and configuration access.

Doctor:

- Register, search and update patients.
- Open **ANY individual patient's complete clinical AND financial history**, including old payments and fully paid accounts.
- Create agreed charges, record today's payments and set initial installment agreements; Owner approves revisions.
- See today's combined collections.
- See outstanding patients and their individual balances.
- Must **NOT** see combined historical financial totals or weekly, monthly or annual income reports.
- Must **NOT** have bulk financial export or backup/restore access.

Never hide old financial records from the Doctor inside an individual patient's profile. Server authorization must enforce these rules on every future endpoint, query, report and export. Current owner accounts are superusers; Doctors receive fixed patient and clinical-record view/add/change permissions as appropriate. No audit write, hard deletion, account administration or export permissions are granted to Doctor. Owners can create and disable/enable Doctors and reset passwords from the local console. Arbitrary custom-role UI remains pending; Owner-only encrypted backup/verified offline restore is implemented. Financial reports and export are Owner-only. No general Django admin route is exposed. Trusted local maintenance commands operate under Windows filesystem privileges.

## Patient record

Permanent unique automatically generated patient number; required full name and primary phone. Optional WhatsApp, birth date **or** approximate age, address, occupation, emergency contact, medical history, current medicines, allergies and alerts. Approximate age stores the value and recording date; never infer an exact birth date. Age range 0–120, no future birth dates. Created/updated actor and timestamp retained. Blank medical values mean “not recorded”; explicitly confirmed absence must be entered as “None confirmed”. Do not delete patients in Phase 1.

## Search contract

One tested normalization function validates and stores full primary/WhatsApp numbers as E.164 and supports canonical search and duplicate checks. `03001234567`, `0300 1234567`, `0300-1234567`, `+923001234567` and `00923001234567` match the same Pakistani phone. Accept valid international numbers with country codes; no-country-code numbers use Pakistan. Exact indexed lookup first, then partial fallback for incomplete numbers. Four digits minimum for partial phone queries; two characters for name or patient-number queries. Partial local PK prefixes are mapped to the canonical country prefix. POST carries search terms without putting them in URLs. Results are 20 per page with no public directory or API. No live-search race is introduced.

Families can share numbers. Display selection rows with name, permanent number and age/birth date. Before creation (or a phone edit), show possible duplicates and require explicit shared-phone confirmation; do not block legitimate family members. No results must offer registration. Ordinary logs must exclude search terms and clinical text.

## Interface and scope

Charcoal, blue and light-green accents; accessible light text, clear focus and large controls; local system fonts, responsive layout, text identity only. No invented logo, statistics or money. Dashboard phone search, registration and actual patient count. Right panels show current/next patients, remaining/overdue appointments and private unfinished tasks. Owner account management, restricted financial reports and Owner backup/recovery. Profile has demographics, prominent medical alerts and functional Overview, Visits, Medical History, Dental Chart, Treatment Plans and Attachments sections. Payments, appointments and prescriptions are functional. Print foundation uses white backgrounds.

## Security and audit

No public signup. Hidden-password owner setup and restricted Doctor creation. Every patient/clinical/attachment endpoint is authenticated and permission checked. CSRF protects mutations and POST search; POST logout; 30-minute idle sessions and close-browser expiry. Persistent 15-minute login throttles. Private no-store responses, same-origin referrer policy and same-origin assets. Audit patient/clinical changes, completion/amendments, medical reviews, treatment-plan changes and attachment upload/access using actor, object IDs and time, without clinical text. Doctor cannot access or modify audits. Owner has read-only audit UI. This audit is not tamper-proof; trusted filesystem/ORM maintenance can bypass application protections. Application logs suppress request paths. Bounded allowlisted diagnostics contain IDs, time, exception type and source locations, without raw errors, request contents or frame locals. Avoid actual patient data in Git and test artifacts.

## Implemented Phase 2 clinical contract

Visits have a date/time, clinician, complaint, examination, diagnosis, adult/primary FDI teeth or general area, planned/performed treatment, advice, remaining work and follow-up. Multiple same-day visits are valid. Draft/in-progress revisions use conditional updates; stale requests return conflict without overwriting current data. The interface retains unsaved text in the current tab, shows Saving/Saved/Failed, and supports reauthentication in another tab. There is no localStorage of patient notes. Closing an unsaved tab or browser crash can lose pending edits. Completed notes cannot be routinely edited; dated reasoned amendments retain the originals.

Medical history, medicines, allergies and alerts each distinguish Not recorded, None confirmed and Details recorded. A dated review is captured for every new visit, preserving context after subsequent medical updates. Direct profile medical edits also create historical reviews. Clinical fields are escaped in HTML. Tooth identifiers use all 32 permanent and 20 primary FDI codes, support multiple teeth and general areas, and reject invalid/duplicate IDs. The chart is a text-labelled selection/history aid, not an automated diagnosis or image interpretation tool.

The editable procedure catalogue has six clearly labelled examples and no prices. Plans contain staged items with dates, notes and teeth/areas; immutable snapshots retain plan changes. Performed procedures link to a patient/visit and optional same-patient plan item. Recorded procedure labels survive catalogue renaming. Work may span multiple visits. There are no clinical deletion endpoints. Date/actor-linked observations and attachments are retained as historical records.

Uploads accept actual JPEG, PNG and passive PDF only, with matching extension, content parsing and resource bounds. Originals are preserved under generated names; images receive separate stripped-metadata thumbnails. PDFs with actions, forms, embedded files or encryption are rejected and accepted PDFs are download-only. Original images may contain sensitive metadata and must remain private. Every upload/download/preview/thumbnail route checks permissions and patient ownership; no public MEDIA route exists. Categories, dates, descriptions, teeth/area and optional visit linkage are supported. Missing files keep metadata and report unavailability. Failed upload writes roll back metadata and remove newly created files; abrupt power-loss recovery is not yet implemented.

## Phase 2 schema and storage

Existing Patient and authentication records are retained. Additive migrations `0002` and `0003` create clinical tables, add audit object IDs and seed fixed clinical permissions/examples. Foreign keys protect referenced clinical records from routine deletion.

| Model | Relationships and purpose |
| --- | --- |
| MedicalReview | Patient + reviewer/time; immutable JSON medical snapshot and reason |
| Visit | Patient + clinician + MedicalReview + creator/updater; notes, status, revision |
| VisitAmendment | Visit + author/time; retained correction and reason |
| Procedure | Editable active/example catalogue; no financial fields |
| TreatmentPlan / PlanItem | Patient plan with revision; items reference Procedure and stages |
| PlanRevision | Plan + author/time; immutable complete plan snapshot |
| PerformedWork | Patient + Visit + Procedure; optional PlanItem; retained procedure label |
| ToothObservation | Patient + optional Visit + author/time; teeth/area and observation |
| Attachment | Patient + optional Visit + uploader/time; file metadata and generated storage IDs |
| AuditEvent | Actor + patient + object type/ID + action/time; no clinical text |

Default and launcher runtime selection is `<project>/runtime/development`, overridable explicitly with `RUMI_DATA_DIR`. Database: `clinic.sqlite3`; matching secret: `secret.key`; originals: `attachments/originals`; derived thumbnails: `attachments/thumbnails`; temporary uploads: `upload-tmp`; diagnostics: `diagnostics/events.log` (256 KiB + three rotations). All are ignored by Git. Do not move/copy the database without originals and required configuration. Pre-migration database/secret safety copies are not complete clinical backups. Phase 5 complete backups implement the contract below; safety copies remain a separate limited tool.

## Phase 5 backup contract (implemented trial)

A restorable archive must contain the **database + every attachment + manifest/schema version**, with application version, UTC creation time and checksums. Produce a consistent snapshot across database and attachments; a raw copy of an open SQLite file is insufficient. Encrypt archives with a documented key/recovery procedure. Verify archive integrity, retain dated generations, and test restore into a separate directory before replacing live data. Verify patient counts, selected complete records, attachment references and application/schema compatibility after restore.

Support local/external folders and an existing Google Drive synchronized folder without API integration; remote upload/protection is not verified by a local save. Daily workflows must not require Drive or internet. Define retention and failure reporting, prevent unauthorized Doctor access, and validate paths/archive contents on restore. Back up the needed runtime configuration securely. **A backup on the same laptop does not protect against laptop failure, theft or loss.** A separate external/off-device copy and restore rehearsal are mandatory before live clinical use.

## Live-data gate

No real patient data until backup/restore verification and a fictional-data clinic trial are complete. The trial must check realistic data volume, keyboard use, Windows restarts, interrupted sessions, access boundaries, print needs and reliable local startup. Phase 6 owns final installation packaging. Document limitations honestly; do not treat passing unit tests as full clinical readiness.


## Implemented Phase 3 financial contract

Patients have multiple protected treatment accounts; charge items optionally reference existing same-patient plan items/visits. Plan items have a global unique charge link so repeated visits cannot charge the same item again. No clinical text is rewritten. Financial and clinical completion are independent.

Immutable LedgerEntry records hold kind, Decimal amount, reason/description, received_at, recorded_at, actor, method, external reference, unique receipt UUID, unique submission UUID, original correction link and posting balance. Balance = original charges - charge reversals - approved discounts/write-offs - payments + refunds/payment reversals. No float arithmetic or negative balances; positive entries with at most two decimal places only. Cash, bank transfer and Easypaisa only. SQLite writes begin with a singleton FinancialLock UPDATE before balance/idempotency reads; all state changes and audit entries share an atomic transaction. File-backed concurrent-process tests cover competing payments and identical submission tokens.

Doctor can access any individual complete financial history across all dates/closed accounts, today's combined collections, initial schedules and individual reminder balances. Server access checks apply before queries, reports, exports, expense pages and decisions. Doctor receives no combined outstanding or combined historical paid totals, cannot select dates on the today endpoint, and cannot backdate by submitted data. Owner alone approves financial corrections, discounts, write-offs, refunds, schedule revisions and reopening; historical aggregate reports and CSV are Owner-only. Financial routes use the existing fixed Doctor patient permission and active authenticated sessions. No general admin editing/deletion route is introduced.

Posted entries cannot be routinely edited/deleted, including via their model manager. Explicit reasoned reversals link to complete uncorrected originals; refunds link to payments and cannot exceed the uncorrected original amount. Correction requests retain requester, reason, pending/approved/rejected decision, decision reason/actor/time, with duplicate-decision protection and an immutable decision event. Closed accounts require Owner reopening before new postings. Zero-balance closure never posts cash; fully paid and discount/write-off settlement labels differ. Only Owner closes adjusted settlements. AuditEvent links patient transactions/requests/schedules/account events to actor/object/time; immutable Expense originals/reversals retain their own actor, time and reason. Trusted filesystem/ORM maintenance remains outside application authorization and is not tamper-proof.

An immutable Schedule supersedes earlier agreements; positive installment rows sum to the current balance at creation. Payments allocate rows in recorded agreement order (oldest row first), refunds release newest-row allocations first. Signed immutable Allocation records link movements to ledger entries and never add cash. No agreed date means no inferred date. Paid/partial/pending status derives from allocations; overdue means unpaid with due date before today's Asia/Karachi date. Owner revisions retain history and schedule only the current remaining balance. New charges, noncash adjustments or corrections invalidating the schedule mark it historical; refunds beyond current allocations do likewise. Owner must explicitly agree a matching revision. Early settlement pays all remaining rows.

Business ranges use Asia/Karachi [start midnight, midnight after end). Weekly means Monday-Sunday; monthly and annual are calendar periods; custom is inclusive dates. Owner reports distinguish range charges/noncash reductions, gross collections, refunds/reversals, net collections and expenses; method breakdowns are net collections. Net cash movement = net collections - net expenses, not accounting profit. Current outstanding/overdue are labelled present-time balances, not snapshots at the historical report end. Expense corrections use one immutable linked reversal with reason; replacements are separate. CSV contains financial entries and cash-effect columns, excludes clinical fields and prefixes dangerous spreadsheet strings.

Individual print receipts show clinic name/location, patient name/number, account/receipt reference, Pakistan received time, method, amount, posting/current balances and linked later corrections; no other patients or invented tax identifiers. Trial storage stays `<project>/runtime/development`; additive migrations 0004-0005 preserve all original tables. Before local migration: stop writes, verify consistent database + matching-secret safety copy, retain uploads and compare originals after migration. This is not Phase 5 backup/restore.


## Implemented Phase 4 workflow contract

Appointment belongs to an existing patient, holds Pakistan-aware start/end, purpose/notes, explicit Scheduled/Arrived/In Treatment/Completed/Cancelled/No-show status, arrival/queue times, walk-in flag, optional unique same-patient Visit, revisions and creator/updater timestamps. End > start has a database constraint. A first-statement WorkflowLock UPDATE serializes overlap checks, visit creation and all workflow writes on SQLite. Unique WorkflowEvent tokens make retries idempotent; optimistic revisions reject conflicting changes. Before/after events retain reschedules, reasons and actor/time; no hard-delete endpoints are introduced. Overlaps use start < other end and end > other start among active statuses. Intentional overlaps require explicit confirmation plus reason; reactivation checks again. Only one patient may be In Treatment. Clock passage never changes a status.

Dashboard queue: current In Treatment; arrived bookings ordered by queue_at (initial arrival), arrived_at and ID; otherwise earliest upcoming Scheduled booking today. Explicit queue adjustment requires a reason and preserves the original arrival. Unresolved past Scheduled bookings remain in a separate overdue list across midnight. Daily schedule includes bookings crossing into the selected day. Optional existing editable visits must be same patient and unlinked elsewhere. Appointment Start Visit creates/links once and changes only appointment state; clinical completion remains separate. Phone-search result/profile actions and new-patient registration links preserve phone-first flow.

The explicit Refresh control loads current panels. Local JavaScript checks Asia/Karachi date every 15 seconds and refreshes just the panels at midnight without interrupting search/forms; it does not poll continuously. Unauthorized/network-failed refresh removes old panel data. Local idle expiry clears panels and returns to login; server session/permission checks remain authoritative. JS-disabled operation requires explicit Refresh at a date change. Narrow panels follow the main workspace. No financial aggregate is included in panel context.

PersonalTask belongs exclusively to creator; Owner cannot access another user's tasks through list, dashboard, history, pagination or direct mutation URLs. Title/notes/optional due time, completion/reopen events and unchanged original due dates support carry-forward; tasks and appointments remain distinct. All updates have revisions and submission tokens. No recurrence or notification service exists.

Prescription drafts belong to the signed-in Doctor. Prescribing requires actual membership in the fixed Doctor group plus clinical creation permission; superuser status alone is insufficient. Owner-only accounts view/print but cannot draft, issue, correct or maintain someone else's prescribing identity. No client-supplied prescriber is accepted. Doctor maintains their own actual name and optional clinician details; Owner maintains clinic print name/address/contact. Blank qualifications/registration/signature/logo are not invented.

Drafts include date, optional same-patient visit, up to 20 structured medication rows (name, strength/form, dose, route, frequency, duration, quantity, instructions), general advice and follow-up. Editing/issuing shows allergies/alerts. No medications, doses or advice are generated. Drafts may be incomplete; issue requires medication name/dose/route/frequency/duration, configured clinician name and explicit review confirmation. Immutable issued snapshots retain relevant patient identity/age, clinic/clinician print details and contents. Corrections create an immutable linked void with reason/actor/time and optional replacement draft; replacement uses correcting Doctor's own identity and requires independent issuance. Original becomes void immediately and remains visible/printable as void. Clinical/financial histories are not rewritten.

Standalone white prescription/optional appointment prints contain only the selected patient/document, with draft/void labels and normal browser Print/Save as PDF. Config changes do not alter issued snapshots. No PDF service, signature or legal invoice claims. Manual reminder text contains only clinic name, appointment Pakistan date/time and a rescheduling prompt; no patient name, clinical purpose, diagnosis, finances or attachments. Validate saved WhatsApp number; primary phone requires explicit fallback confirmation. External Open WhatsApp is user-controlled, sends nothing automatically and does not log delivery. Only user-confirmed copied/manually-sent activity is recorded accurately. Reminder preparation itself is read-only.

Migrations 0006-0007 add workflow tables/serialization row only. Runtime stays `runtime/development`; writes pause and a consistent database+matching-secret safety copy is verified before local migration. Existing rows, credentials, roles and attachment/secret fingerprints are compared after migration. All Phase 3 permission boundaries remain unchanged. Full backup/restore and operational recovery remain Phases 5-6; fictional data only.


## Implemented Phase 5 recovery contract

Owner-only Backup & Restore has independent destination configuration, background backup/verify/export jobs, daily settings, per-destination results/history, overdue/failure/availability warnings, protected downloads and re-authenticated restore preview. Doctor/anonymous access is denied before reading any package/config/history. Metadata uses local atomic JSON under `backup-control`, not business schema migrations; configuration revisions prevent lost updates. No schema migration or working-data reset is needed for this phase.

All supported HTTP requests acquire a cross-process shared runtime lease around view/session writes; attachment storage acquires it too. A snapshot worker obtains the exclusive lease after existing requests finish, reserves SQLite writes and uses sqlite3.Connection.backup, then copies every original/thumbnail and matching secret. New clinic submissions receive a clear 503/retry during this short boundary; encryption/verification/copying run asynchronously afterward. Readiness is read-only. The guarded server holds a separate lifetime lease; offline restoration cannot replace an active guarded runtime. Trusted external direct filesystem/SQL maintenance is outside these protections.

A versioned `.rumibak` contains SQLite, every original/thumbnail (including retained unreferenced generated files), matching secret, allowlisted portable timezone/upload limits and encrypted manifest with app/format/schema, UTC creation, migrations, row counts, sizes and SHA-256 checksums. Business records/accounts/password hashes/settings/audits retain IDs/relationships. Source/venv, logs, older backups, temp files and machine-bound destination/DPAPI/job state are excluded. Restore clears database sessions; destinations/automatic credentials are reconfigured after transfer. The source expected schema is derived only from clean trusted migrations; package code is never imported or executed.

Encryption is maintained cryptography AES-256-GCM with fresh salt/nonce and Argon2id (64 MiB, 3 iterations, 4 lanes). No custom cryptographic algorithm/password ZIP. Recovery depends on the password, not old-machine keys. Automatic credential storage uses Windows current-user DPAPI only; unsupported platforms/users fail explicitly with no plaintext fallback. Recovery passwords are hidden/local form or prompt input, never command arguments, logs or plaintext settings. Plaintext local staging is transient on normal completion, not an encryption/secure-erasure guarantee for the live disk after crashes.

Destinations must be existing absolute folders outside live data/source. Paths/junctions/symlinks are checked, missing drives never fall back, disk capacity is checked, output copies are verified and atomically finalized. Google Drive needs an explicitly selected unsynchronized staging folder on the same volume; selected sync folder receives only completed encrypted packages. Label exactly Saved to Google Drive folder; Desktop synchronization/internet and remote upload are outside app verification. Another partition is not independent disk protection; require off-device copies and rehearsed recovery before live data.

Daily scheduling runs only in the active guarded server, checks startup and each minute, uses Asia/Karachi due slots and catches up only the most recent slot with current data/actual creation time. OS job lease prevents overlap; deterministic daily filenames plus verification close crash/retry duplicate windows. Per-destination completion is separate; unavailable copies retry without duplicating an already successful daily destination. Failed local history persistence is shown as failed in memory, not success. Polling does not extend idle sessions. Retention keeps 2-365 dated generations; only recorded, present, checksum-matching files from this installation/destination are eligible. Retain newest good copies, never remove unrelated/changed files, never prune after failed/partial jobs.

Verify authenticates before extraction, checks strict inventories, SHA-256, full SQLite integrity/FKs, trusted table definitions/migration history, secret/config and all attachment references. Fixed limits: 8 GiB package/expanded, 2 GiB per file, 100,000 files, 16 MiB manifest; stored-file archive only, no symlinks/unsafe/duplicate paths or compression bombs. Supported older tail schemas are tested/upgraded only on a staged copy via trusted source; future/unknown/inconsistent structures fail. Portable migration record size is capped at 15 MiB with clear refusal, never silent truncation.

Web restore requires Owner re-authentication and explicit confirmation but performs preview only. Separate standalone local helper works without an initialized database, prompts for recovery password and confirmation, and re-authenticates an active Owner for existing-runtime replacement. It refuses active server/job leases, validates staging boundaries, verifies a pre-restore old runtime, swaps directory generations together and probes activation. Normal failure rolls back; interruption journal blocks startup before database/secret creation and supports authenticated repair. Sessions clear; original restored accounts/passwords are used with no defaults or merge. Root shortcuts intentionally select `runtime/development`; other explicit targets require the matching manual environment.

Encrypted `.rumiexport` contains all business module rows with stable IDs/relationships, Unicode JSON, formula-neutralized CSV, field/FK dictionary, attachment mapping/files/checksums and export/schema timestamps. Password hashes, secret, session and throttle/DPAPI state are excluded. Decimal money uses fixed text. It is not a full disaster backup; no importer is supplied. Full restore retains credentials; migration export intentionally does not.

All recovery checks use copies/isolated fictional fixtures; working clinic is never restored over during automated verification. Physical USB disconnection/cloud sync, native power loss, other-user DPAPI portability and representative-volume operational trials are not claimed verified. Final packaging/trial sign-off remains Phase 6; continue fictional data.
