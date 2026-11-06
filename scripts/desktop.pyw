"""No-console desktop entry. Errors are visible; credentials are never recorded."""
from pathlib import Path
import ctypes
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts import trial_launcher


def stop_window(challenge, proof):
    import tkinter as tk
    import threading
    window=tk.Tk()
    window.title('Stop Rumi Dental Care')
    window.geometry('460x130')
    tk.Label(window,text='Stopping safely…\nWaiting for active requests and backup jobs.\nLeave Windows running until this window closes.',padx=20,pady=20).pack()
    window.protocol('WM_DELETE_WINDOW',lambda:None)
    result=[]
    def worker():
        try:
            trial_launcher.stop(challenge,proof)
            result.append(None)
        except Exception as exc:
            result.append(exc)
    threading.Thread(target=worker,daemon=True).start()
    def poll():
        if result:
            window.destroy()
        else:
            window.after(100,poll)
    window.after(100,poll)
    window.mainloop()
    if result[0]:
        raise result[0]


def main():
    try:
        challenge, proof = trial_launcher.preflight()
        if '--stop' in sys.argv:
            stop_window(challenge, proof)
            return
        if not trial_launcher.port_occupied():
            subprocess.Popen([str(ROOT / '.venv/Scripts/pythonw.exe'), str(ROOT / 'scripts/trial_launcher.py'), '--serve'], cwd=ROOT,
                             creationflags=subprocess.CREATE_NO_WINDOW, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not trial_launcher.wait_until_ready(challenge, proof, __import__('threading').Event(), timeout=30):
            raise trial_launcher.TrialLaunchError('Startup could not verify this installation. Port 8000 may be occupied. Use Diagnostic Start Rumi Dental Care.cmd for details. No process was killed.')
        trial_launcher.open_browser(True)
    except Exception as exc:
        message = str(exc) if isinstance(exc, trial_launcher.TrialLaunchError) else f'Local operation failed ({type(exc).__name__}). Use Diagnostic Start for details.'
        ctypes.windll.user32.MessageBoxW(None, message, 'Rumi Dental Care', 0x10)


if __name__ == '__main__':
    # pythonw has no stdout/stderr; preflight uses print(..., flush=True).
    with open(__import__('os').devnull, 'w') as sink:
        sys.stdout = sys.stderr = sink
        main()
