# Confirmed requirements

Private business software for Rumi Dental Care, Lahore, Pakistan: one branch, one dentist, no receptionist. Daily workflow: phone → matching patients → complete individual profile → today's visit → reliable retrieval years later. Windows offline operation comes first. Phases 1–2 are implemented as a fictional-data trial. Online deployment is a separate future stage.

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
- Later: enter today's charges/payments and manage installments.
- Later: see today's combined collections.
- Later: see outstanding patients and their individual balances.
- Must **NOT** see combined historical financial totals or weekly, monthly or annual income reports.
- Must **NOT** have bulk financial export or backup/restore access.

Never hide old financial records from the Doctor inside an individual patient's profile. Server authorization must enforce these rules on every future endpoint, query, report and export. Current owner accounts are superusers; Doctors receive fixed patient and clinical-record view/add/change permissions as appropriate. No audit write, hard deletion, account administration or export permissions are granted to Doctor. Owners can create and disable/enable Doctors and reset passwords from the local console. Finance, arbitrary custom-role UI, backup and export are pending. No general Django admin route is exposed. Trusted local maintenance commands operate under Windows filesystem privileges.

## Patient record

Permanent unique automatically generated patient number; required full name and primary phone. Optional WhatsApp, birth date **or** approximate age, address, occupation, emergency contact, medical history, current medicines, allergies and alerts. Approximate age stores the value and recording date; never infer an exact birth date. Age range 0–120, no future birth dates. Created/updated actor and timestamp retained. Blank medical values mean “not recorded”; explicitly confirmed absence must be entered as “None confirmed”. Do not delete patients in Phase 1.

## Search contract

One tested normalization function validates and stores full primary/WhatsApp numbers as E.164 and supports canonical search and duplicate checks. `03001234567`, `0300 1234567`, `0300-1234567`, `+923001234567` and `00923001234567` match the same Pakistani phone. Accept valid international numbers with country codes; no-country-code numbers use Pakistan. Exact indexed lookup first, then partial fallback for incomplete numbers. Four digits minimum for partial phone queries; two characters for name or patient-number queries. Partial local PK prefixes are mapped to the canonical country prefix. POST carries search terms without putting them in URLs. Results are 20 per page with no public directory or API. No live-search race is introduced.

Families can share numbers. Display selection rows with name, permanent number and age/birth date. Before creation (or a phone edit), show possible duplicates and require explicit shared-phone confirmation; do not block legitimate family members. No results must offer registration. Ordinary logs must exclude search terms and clinical text.

## Interface and scope

Charcoal, blue and light-green accents; accessible light text, clear focus and large controls; local system fonts, responsive layout, text identity only. No invented logo, statistics or money. Dashboard phone search, registration and actual patient count. Right panel reserves appointments and tasks with honest Phase 4 placeholders. Owner account management and pending financial/backup areas. Profile has demographics, prominent medical alerts and functional Overview, Visits, Medical History, Dental Chart, Treatment Plans and Attachments sections. Prescriptions (Phase 4) and Payments (Phase 3) remain visibly pending. Print foundation uses white backgrounds.

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

Default and launcher runtime selection is `<project>/runtime/development`, overridable explicitly with `RUMI_DATA_DIR`. Database: `clinic.sqlite3`; matching secret: `secret.key`; originals: `attachments/originals`; derived thumbnails: `attachments/thumbnails`; temporary uploads: `upload-tmp`; diagnostics: `diagnostics/events.log` (256 KiB + three rotations). All are ignored by Git. Do not move/copy the database without originals and required configuration. Pre-migration database/secret safety copies are not complete clinical backups. The definitive backup contract below remains Phase 5.

## Phase 5 backup contract (not implemented)

A restorable archive must contain the **database + every attachment + manifest/schema version**, with application version, UTC creation time and checksums. Produce a consistent snapshot across database and attachments; a raw copy of an open SQLite file is insufficient. Encrypt archives with a documented key/recovery procedure. Verify archive integrity, retain dated generations, and test restore into a separate directory before replacing live data. Verify patient counts, selected complete records, attachment references and application/schema compatibility after restore.

Support local and external targets, plus optional Google Drive upload only when online. Daily workflows must not require Drive or internet. Define retention and failure reporting, prevent unauthorized Doctor access, and validate paths/archive contents on restore. Back up the needed runtime configuration securely. **A backup on the same laptop does not protect against laptop failure, theft or loss.** A separate external/off-device copy and restore rehearsal are mandatory before live clinical use.

## Live-data gate

No real patient data until backup/restore verification and a fictional-data clinic trial are complete. The trial must check realistic data volume, keyboard use, Windows restarts, interrupted sessions, access boundaries, print needs and reliable local startup. Phase 6 owns final installation packaging. Document limitations honestly; do not treat passing unit tests as full clinical readiness.
