# Daily use — local Windows trial

Use fictional records until the Owner and Doctor complete CLINIC_TRIAL.md.

1. Double-click **Rumi Dental Care** on the desktop. It starts the background app, verifies this installation, then opens the browser at http://127.0.0.1:8000/. Sign in with your existing account. Repeated Start reuses the verified app. Closing the browser leaves it running; Start opens it again.
2. Choose **Find a patient** or use the dashboard phone field. Enter the patient's Pakistani phone in local or international format. Family members may share it: choose the correct name, permanent number and age. Review medical alerts before starting a visit.
3. Book/mark arrival/Start Visit as appropriate. Clinical note Saving/Saved/Failed messages matter. Keep an unsaved tab open after failure; sign in in another tab and retry. A stale-tab conflict requires reviewing the current saved record. Closing an unsaved tab can lose edits.
4. In the patient's **Payments**, select the correct treatment account. Record the agreed charge once and each actual payment once. Review the amount, method, receipt and remaining balance. Installment allocations are not additional collections. Close only the settled account; the patient and full history remain.
5. Doctor authors/reviews prescriptions, reviews patient/allergy and actual print identity, then issues. Correct an issued prescription through Void / replace with a reason; retain the original. Preview the selected document before printing.
6. Owner checks **Backup & Restore** daily: destination available, recent verified backup, and no overdue/failure warning. Confirm off-device availability separately. A Drive folder save does not prove cloud upload.
7. Before Windows shutdown or offline recovery, double-click **Stop Rumi Dental Care**. Allow time for requests and backup jobs. A timeout displays a message: leave Windows running, wait, then retry. Stop never forcibly kills a process. Closing the browser is not Stop.

If startup fails, double-click **Diagnostic Start Rumi Dental Care.cmd** in the project folder. It shows local details in a visible console. Do not copy diagnostic details or patient screenshots into public issues. A port conflict does not authorize killing its listener. Do not recreate accounts, reset data, move the database alone or delete recovery journals.

Recreate Start/Stop shortcuts from the project folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Setup Desktop Shortcut.ps1"
```

Both shortcuts always select this checkout's `runtime\development`. Existing passwords and data remain in that directory. No administrator rights, Windows service or login autostart are used.
