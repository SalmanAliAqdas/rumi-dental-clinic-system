# Backup and recovery

Owner configures existing destination folders under **Backup & Restore**, chooses a recovery password, runs **Back Up Now**, and checks each destination's verified result. Keep the password separately and at least one copy on a physically independent device. Another partition is insufficient. Do not synchronize the live runtime or plaintext work area.

Automatic settings use the current Windows user's DPAPI credential and run only while the app is running. Background desktop startup runs the same scheduler. Missing drives fail explicitly; no alternate destination is chosen. An overdue backup remains a warning even with automatic scheduling off. Drive-folder saving is local only; verify synchronization yourself.

Portable encrypted `.rumibak` packages preserve database, original/thumbnail files, matching secret, accounts/password hashes, roles, business settings, relationships and checksums. Sessions are cleared on restoration. Destination paths and DPAPI credentials are machine-specific and must be configured again. `.rumiexport` is a credential-free migration export, not disaster recovery. Package format and existing Phase 5 recovery compatibility are unchanged.

Recover with the server stopped. The helper works without a running web app. On a new laptop install Python 3.13, the same compatible source and pinned dependencies; **do not initialize a replacement database or accounts**. Copy the package outside the target runtime. From the project folder:

```powershell
.\.venv\Scripts\python.exe scripts\recovery.py verify --package "E:\RumiBackups\selected.rumibak"
.\.venv\Scripts\python.exe scripts\recovery.py restore --package "E:\RumiBackups\selected.rumibak" --data-dir "C:\your project\runtime\development"
```

Enter the recovery password at the hidden prompt, current Owner credentials if replacing an existing runtime, and explicit RESTORE confirmation. Choose the actual absolute target, not the example literally. Never restore over working data for a drill. Locks refuse activation while the app or a backup job runs. Original accounts/passwords return; no bypass or reset is performed.

Activation retains a rollback runtime and uses an interruption journal. If startup reports interrupted restoration, stop the intended app and run:

```powershell
.\.venv\Scripts\python.exe scripts\recovery.py repair --data-dir "C:\your project\runtime\development"
```

Do not delete the journal/rollback manually. Verify original logins, patient numbers, clinical/financial histories, balances, issued prescription snapshots, tasks, appointment links and attachment checksums before accepting recovery. Keep rollback until checked. Local plaintext runtime, rollback and staging need Windows account/disk protection; secure erasure and real power-loss durability are not claimed.

Updates to an existing installation: Stop, review the selected runtime, then:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Setup Local.ps1" -DataDirectory "$PWD\runtime\development" -Update
```

This checks Python/dependencies and takes a verified complete local safety snapshot before migrations. It never relocates data, regenerates a working secret or replaces passwords. Keep an encrypted off-device backup as well. For fully offline dependency installation add `-Wheelhouse "E:\RumiWheels"`; prepare that wheel folder for the target Python/Windows ahead of time using `python -m pip download -r requirements.txt --dest E:\RumiWheels` on a compatible online machine. One-time package download needs internet. Source updates are reviewed local Git updates; no automatic updater is installed.

**User verification required:** physical USB/off-device recovery, a second laptop, real Drive synchronization, securely retained recovery password and native password prompts. Same-laptop fixtures do not establish these checks.
