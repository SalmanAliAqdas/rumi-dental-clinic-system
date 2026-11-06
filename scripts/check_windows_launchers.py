"""Opt-in Windows integration checks; requires port 8000 to be unused.

Creates only an isolated fictional fixture under ignored runtime/. No clinic
database is copied, migrated or reset. Does not open a browser.
"""
from contextlib import closing
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from clinic.trial_identity import APPLICATION, CHALLENGE_HEADER, READY_PATH, identity_proof


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def run_cmd(path, *args, input='\n', timeout=20):
    environment = dict(os.environ, DJANGO_SETTINGS_MODULE='wrong.settings', RUMI_DATA_DIR='deliberately-wrong-directory')
    return subprocess.run(['cmd.exe', '/d', '/c', str(path), *args], cwd=ROOT.parent,
                          env=environment, input=input, capture_output=True, text=True, timeout=timeout)


def ready(fixture):
    database = fixture / 'runtime/development/clinic.sqlite3'
    challenge = 'a' * 64
    expected = identity_proof((database.parent / 'secret.key').read_text().strip(), challenge,
                              fixture, database, fixture / '.venv/Scripts/python.exe')
    request = Request('http://127.0.0.1:8000' + READY_PATH, headers={CHALLENGE_HEADER: challenge})
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=.5) as response:
            value = json.loads(response.read(4096))
        return value.get('application') == APPLICATION and value.get('proof') == expected
    except (OSError, ValueError):
        return False


def main():
    if os.name != 'nt':
        raise SystemExit('Windows-only check; not run on this platform.')
    import socket
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(('127.0.0.1', 8000))
        except OSError:
            raise SystemExit('Port 8000 must be free. Stop only your known trial server in its console before running this check.') from None
    default_data = Path(os.environ['LOCALAPPDATA']) / 'RumiDentalCare'
    protected = [ROOT / 'runtime/development/clinic.sqlite3', ROOT / 'runtime/development/secret.key', default_data / 'clinic.sqlite3', default_data / 'secret.key']
    before = {str(p): fingerprint(p) for p in protected}
    runtime = ROOT / 'runtime'
    runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='launcher verification spaces ', dir=runtime) as directory:
        fixture = Path(directory).resolve()
        assert fixture.is_relative_to(runtime.resolve())
        link = fixture / '.venv'
        process = None
        detached = None
        log = None
        try:
            for folder in ['clinic', 'config', 'templates', 'static', 'scripts']:
                shutil.copytree(ROOT / folder, fixture / folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            for file in ['manage.py', 'Start Rumi Dental Care.cmd', 'clinic-shell.cmd']:
                shutil.copy2(ROOT / file, fixture / file)
            launcher = fixture / 'Start Rumi Dental Care.cmd'
            result = run_cmd(launcher, '--check')
            assert result.returncode != 0 and 'python.exe is missing' in result.stdout, result.stdout + result.stderr
            assert 'Press any key' in result.stdout
            subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(ROOT / '.venv')], check=True, capture_output=True)
            result = run_cmd(launcher, '--check')
            assert result.returncode != 0 and 'missing or empty' in result.stderr
            assert not (fixture / 'runtime/development/clinic.sqlite3').exists()
            print('PASS: missing Python and missing database stop with open-window pause instructions; no replacement database.', flush=True)
            data = fixture / 'runtime/development'
            data.mkdir(parents=True)
            database = data / 'clinic.sqlite3'
            database.touch()
            result = run_cmd(launcher, '--check')
            assert result.returncode != 0 and database.stat().st_size == 0
            print('Initializing only the isolated fictional verification fixture.', flush=True)
            environment = dict(os.environ, DJANGO_SETTINGS_MODULE='config.settings', RUMI_DATA_DIR=str(data))
            subprocess.run([str(link / 'Scripts/python.exe'), 'manage.py', 'migrate', '--noinput'], cwd=fixture, env=environment, check=True, capture_output=True)
            before_fixture = fingerprint(database)
            result = run_cmd(launcher, '--check')
            assert result.returncode == 0 and str(database) in result.stdout, result.stdout + result.stderr
            assert fingerprint(database) == before_fixture
            print('PASS: real CMD resolves a path containing spaces from another working directory, overrides wrong terminal settings, and checks migrations without modifying the database.', flush=True)
            update = subprocess.run([str(link / 'Scripts/python.exe'), str(fixture / 'scripts/local_update.py'), '--data-dir', str(data), '--apply'], cwd=ROOT.parent, env=environment, capture_output=True, text=True, timeout=30)
            assert update.returncode == 0 and 'Complete local safety backup verified' in update.stdout, update.stdout + update.stderr
            assert fingerprint(database) == before_fixture
            manifests=list((fixture / 'runtime/phase6-safety').glob('*/safety-manifest.json'))
            assert len(manifests)==1
            print('PASS: explicit local update creates verified complete safety backup before migration checks, preserves existing data and supports spaces.',flush=True)

            with closing(sqlite3.connect(database)) as connection:
                rows = connection.execute("SELECT app,name,applied FROM django_migrations WHERE app='clinic'").fetchall()
                with connection:
                    connection.execute("DELETE FROM django_migrations WHERE app='clinic'")
            pending_fingerprint = fingerprint(database)
            result = run_cmd(launcher, '--check')
            assert result.returncode != 0 and 'migrations are pending' in result.stderr
            assert fingerprint(database) == pending_fingerprint
            with closing(sqlite3.connect(database)) as connection:
                with connection:
                    connection.executemany('INSERT INTO django_migrations (app,name,applied) VALUES (?,?,?)', rows)
            print('PASS: pending migrations are refused, never applied automatically.', flush=True)
            shell_command = "Write-Output ('SHELL_PROOF=' + $env:DJANGO_SETTINGS_MODULE + '|' + $env:RUMI_DATA_DIR + '|' + (Get-Location).Path); exit\n"
            result = run_cmd(fixture / 'clinic-shell.cmd', input=shell_command)
            assert result.returncode == 0 and f'SHELL_PROOF=config.settings|{data}|{fixture}' in result.stdout, result.stdout + result.stderr
            print('PASS: clinic-shell opens real PowerShell with the matching working directory, settings and data directory.', flush=True)
            log = (fixture / 'fixture-server.log').open('w', encoding='utf-8')
            process = subprocess.Popen(['cmd.exe', '/d', '/c', str(launcher), '--no-browser'], cwd=ROOT.parent, stdout=log, stderr=log, stdin=subprocess.PIPE)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and process.poll() is None and not ready(fixture):
                time.sleep(.1)
            assert ready(fixture), (fixture / 'fixture-server.log').read_text()
            result = run_cmd(launcher, '--no-browser')
            assert result.returncode == 0 and 'Verified existing Rumi trial server' in result.stdout, result.stdout + result.stderr
            assert process.poll() is None
            print('PASS: application starts and becomes ready; a second launcher verifies and reuses it without a duplicate server.', flush=True)
            result = run_cmd(ROOT / 'Start Rumi Dental Care.cmd', '--no-browser')
            assert result.returncode != 0 and 'identity cannot be verified' in result.stderr
            assert process.poll() is None and ready(fixture)
            print('PASS: another Rumi checkout/database on the same port is rejected, not reused or killed.', flush=True)
            # This is the fixture process tree created above, never an arbitrary
            # port owner or the user's real server. Close the complete CMD/venv tree.
            result = run_cmd(launcher, '--stop')
            assert result.returncode == 0 and 'stopped safely' in result.stdout, result.stdout + result.stderr
            process.wait(timeout=10)
            process = None
            log.close()
            log = None
            result = run_cmd(launcher, '--stop')
            assert result.returncode == 0 and 'already stopped' in result.stdout
            # A stale control file must not stop a newly started instance.
            old_state = json.loads((data / 'local-server.json').read_text())
            detached = subprocess.Popen([str(link / 'Scripts/pythonw.exe'), str(fixture / 'scripts/trial_launcher.py'), '--serve'], cwd=fixture, creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not ready(fixture): time.sleep(.1)
            assert ready(fixture)
            state = json.loads((data / 'local-server.json').read_text())
            assert state['token'] != old_state['token']
            (data / 'local-stop.json').write_text(json.dumps({'token':old_state['token']}))
            time.sleep(.4)
            assert ready(fixture) and detached.poll() is None
            # An active job lease delays shutdown, then Stop completes after release.
            from clinic.backups.locks import lease, lock_path
            with lease(lock_path(data, 'job')):
                stopper = subprocess.Popen([str(link / 'Scripts/python.exe'), str(fixture / 'scripts/trial_launcher.py'), '--stop'], cwd=fixture, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if json.loads((data / 'local-server.json').read_text())['status'].startswith('waiting'): break
                    time.sleep(.1)
                assert detached.poll() is None and stopper.poll() is None
            out, err = stopper.communicate(timeout=15)
            assert stopper.returncode == 0, out + err
            detached.wait(timeout=15)
            print('PASS: orderly and repeated Stop, hidden pythonw restart, stale instance token refusal and active backup lease drain.', flush=True)

            class UnrelatedService(BaseHTTPRequestHandler):
                def do_GET(self):
                    payload = json.dumps({'application': APPLICATION, 'proof': '0' * 64}).encode()
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(payload)

                def log_message(self, *_):
                    pass

            with HTTPServer(('127.0.0.1', 8000), UnrelatedService) as conflict:
                thread = threading.Thread(target=conflict.serve_forever, daemon=True)
                thread.start()
                try:
                    result = run_cmd(launcher, '--no-browser')
                    assert result.returncode != 0 and 'identity cannot be verified' in result.stderr
                    assert thread.is_alive()
                    result = run_cmd(launcher, '--stop')
                    assert result.returncode != 0 and thread.is_alive()
                finally:
                    conflict.shutdown()
                    thread.join(timeout=2)
            print('PASS: unrelated occupied port (even with a copied app name) is rejected without killing it or changing ports.', flush=True)
        finally:
            if detached is not None and detached.poll() is None:
                state_file = fixture / 'runtime/development/local-server.json'
                if state_file.exists():
                    state = json.loads(state_file.read_text())
                    (state_file.parent / 'local-stop.json').write_text(json.dumps({'token': state['token']}))
                    detached.wait(timeout=15)
            if process is not None and process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                process.wait(timeout=10)
            if log is not None:
                log.close()
            # Remove the junction itself before TemporaryDirectory cleanup. Never
            # recursively traverse the real virtual environment through a link.
            if link.is_junction():
                os.rmdir(link)
    assert {str(p): fingerprint(p) for p in protected} == before
    print('PASS: existing clinic database/secret and unintended AppData database/secret are byte-for-byte unchanged.', flush=True)


if __name__ == '__main__':
    main()
