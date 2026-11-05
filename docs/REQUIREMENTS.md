# Confirmed requirements

Private business software for Rumi Dental Care, Lahore, Pakistan: one branch, one dentist, no receptionist. Daily workflow: phone → matching patients → complete individual profile → today's visit → reliable retrieval years later. Windows offline operation comes first. Only Phase 1 is implemented; today's clinical visit entry starts in Phase 2. Online deployment is a separate future stage.

## Stack and local operation

Django 5.2 LTS on supported Python, SQLite, Django templates, local CSS and minimal JavaScript (none currently required). Use Django authentication, password validation/hashing, permissions, sessions, CSRF, ORM and migrations. Pin dependency versions. Separate runtime data and settings from source. No external APIs, Neon, Vercel, Supabase, paid services, CDN scripts/styles or remote fonts. Network access is for initial dependency installation only.

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

Never hide old financial records from the Doctor inside an individual patient's profile. Server authorization must enforce these rules on every future endpoint, query, report and export. Current owner accounts are superusers; Doctors receive only patient add/view/change permissions. Owners can create and disable/enable Doctors and reset passwords from the local console. Permission management in Phase 1 is assignment of the fixed Doctor role; finance, arbitrary custom-role UI, backup and export are pending. No general Django admin route is exposed. Trusted local maintenance commands operate under Windows filesystem privileges.

## Patient record

Permanent unique automatically generated patient number; required full name and primary phone. Optional WhatsApp, birth date **or** approximate age, address, occupation, emergency contact, medical history, current medicines, allergies and alerts. Approximate age stores the value and recording date; never infer an exact birth date. Age range 0–120, no future birth dates. Created/updated actor and timestamp retained. Blank medical values mean “not recorded”; explicitly confirmed absence must be entered as “None confirmed”. Do not delete patients in Phase 1.

## Search contract

One tested normalization function validates and stores full primary/WhatsApp numbers as E.164 and supports canonical search and duplicate checks. `03001234567`, `0300 1234567`, `0300-1234567`, `+923001234567` and `00923001234567` match the same Pakistani phone. Accept valid international numbers with country codes; no-country-code numbers use Pakistan. Exact indexed lookup first, then partial fallback for incomplete numbers. Four digits minimum for partial phone queries; two characters for name or patient-number queries. Partial local PK prefixes are mapped to the canonical country prefix. POST carries search terms without putting them in URLs. Results are 20 per page with no public directory or API. No live-search race is introduced.

Families can share numbers. Display selection rows with name, permanent number and age/birth date. Before creation (or a phone edit), show possible duplicates and require explicit shared-phone confirmation; do not block legitimate family members. No results must offer registration. Ordinary logs must exclude search terms and clinical text.

## Interface and scope

Charcoal, blue and light-green accents; accessible light text, clear focus and large controls; local system fonts, responsive layout, text identity only. No invented logo, statistics, clinical workflows or money. Dashboard phone search, registration and actual patient count. Right panel reserves appointments and tasks with honest Phase 4 placeholders. Owner account management and pending financial/backup areas. Profile has demographics, prominent medical alerts, edit action and visible future Overview/Visits/Treatments/X-rays/Prescriptions/Payments navigation; only Overview works now. Print foundation uses white backgrounds.

## Security and audit

No public signup. Hidden-password owner setup and restricted Doctor creation. Every patient endpoint is authenticated and permission checked. CSRF protects mutations and POST search; POST logout; 30-minute idle sessions and close-browser expiry. Persistent 15-minute login throttles. Private no-store responses, same-origin referrer policy and same-origin assets. Record patient create/update and individual profile access with actor, reference and time. Doctor cannot access or modify audits. Owner has read-only audit UI. This audit is not tamper-proof, immutable storage or field-version history. Application logs suppress request paths. Avoid actual patient data in Git and test artifacts.

## Phase 5 backup contract (not implemented)

A restorable archive must contain the **database + every attachment + manifest/schema version**, with application version, UTC creation time and checksums. Produce a consistent snapshot across database and attachments; a raw copy of an open SQLite file is insufficient. Encrypt archives with a documented key/recovery procedure. Verify archive integrity, retain dated generations, and test restore into a separate directory before replacing live data. Verify patient counts, selected complete records, attachment references and application/schema compatibility after restore.

Support local and external targets, plus optional Google Drive upload only when online. Daily workflows must not require Drive or internet. Define retention and failure reporting, prevent unauthorized Doctor access, and validate paths/archive contents on restore. Back up the needed runtime configuration securely. **A backup on the same laptop does not protect against laptop failure, theft or loss.** A separate external/off-device copy and restore rehearsal are mandatory before live clinical use.

## Live-data gate

No real patient data until backup/restore verification and a fictional-data clinic trial are complete. The trial must check realistic data volume, keyboard use, Windows restarts, interrupted sessions, access boundaries, print needs and reliable local startup. Phase 6 owns final installation packaging. Document limitations honestly; do not treat passing unit tests as full clinical readiness.
