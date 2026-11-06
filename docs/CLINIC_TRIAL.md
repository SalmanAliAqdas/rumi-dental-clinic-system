# Fictional clinic trial and readiness

Software verification is separate from permission to enter real patient information. Use a fresh isolated runtime and generated private test credentials. Never seed the working clinic, restore over it, unplug real hardware or simulate power loss.

Automated replay from the project folder:

```powershell
.\.venv\Scripts\python.exe manage.py test -v 1
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts\check_windows_launchers.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check_desktop_shortcut.ps1
.\.venv\Scripts\python.exe scripts\recovery_drill.py
.\.venv\Scripts\python.exe scripts\performance_trial.py
```

Port 8000 must be free for Windows launcher fixtures. Stop only the known clinic first. Browser verification: `scripts/browser_check.py`, with development-only Playwright 1.64.1 and Chromium installed in the invoking environment. The fixture app runs with this project's dependencies and Waitress. It covers Owner/Doctor at 1440px and 390px, local-only assets, note autosave/stale/session recovery, clinical uploads/history, payment installments/closure, workflow/private tasks/midnight, prescriptions/print and backup UI. Unit tests cover additional financial corrections/reconciliation, shared phones, prescription correction and failure injection. See PROGRESS for actual results, not this command list.

Performance fixture: 5,000 fictional patients, 5,000 visits/medical reviews/accounts/schedules/installments/allocations and 10,000 ledger entries. Each account has PKR 10,000 charge, PKR 3,000 payment and PKR 7,000 remaining. Verify PKR 35,000,000 receivables/overdue and PKR 15,000,000 collections. The script compares a reproduced per-account query strategy with the final read-only summary implementation and measures three warm operations including template rendering/session work. Generated timing output stays under ignored runtime. It is a same-machine synthetic measurement, not a clinical capacity guarantee.

Owner and Doctor manual sign-off — **User verification required** for every unchecked item:

- [ ] Start/Stop shortcuts, browser close/reopen, normal Windows restart, repeated Start; native hidden-password entry.
- [ ] Both original roles log in/out; returning-patient search matches 0300, +92 and 0092 forms; choose correctly between family members sharing a phone.
- [ ] Registration, medical alerts and keyboard-only navigation; arrival, queue and Start Visit match actual practice.
- [ ] Notes save/retry/conflict recovery is understood; chart, treatment plans and X-ray original retrieval are usable.
- [ ] Doctor authors, issues and corrects a fictional prescription; actual clinician/clinic identity is checked; white print and receipt page breaks are acceptable on the physical printer.
- [ ] PKR 10,000 charge → 3,000 + 2,000 + 5,000 payments → zero → close → full retained history. Doctor sees individual past records/today's collections but historical combined reports/exports remain restricted. Owner checks expense corrections and reconciliation.
- [ ] Tasks stay private; date refresh and expired-session behavior are understood.
- [ ] Real destinations/password are selected by Owner, encrypted backup verified and copied off-device. Confirm Drive upload separately if used.
- [ ] Restore a fictional backup on a second laptop; check original logins/IDs/relationships/balances/prescription snapshots/images and cleared sessions.
- [ ] Owner and Doctor approve the completed trial before real patient use. Record date, reviewer and any unresolved issues privately.

No operational recovery drill or sign-off for the working clinic is automatically asserted. Physical checks, actual cloud synchronization and real power-loss behavior remain unverified. Custom role editing, historical receivable snapshots and a migration-export importer remain outside the delivered feature set; no new business modules or online deployment are included.
