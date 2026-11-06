"""Windows Phase 1 trial launcher. No installation or database initialization."""
import argparse
import errno
import _thread
import hmac
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import sqlite3
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
ADDRESS = ('127.0.0.1', 8000)
URL = 'http://127.0.0.1:8000/'
READY_TIMEOUT = 15


class TrialLaunchError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def configure():
    os.chdir(ROOT)
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    os.environ['RUMI_DATA_DIR'] = str(ROOT / 'runtime' / 'development')
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return ROOT / 'runtime' / 'development' / 'clinic.sqlite3'


def preflight():
    database = configure()
    python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if not python.is_file():
        raise TrialLaunchError('Project .venv\\Scripts\\python.exe is missing. Follow README setup manually.')
    if not database.is_file() or database.stat().st_size == 0:
        raise TrialLaunchError(
            f'The intended existing database is missing or empty: {database}\n'
            'Do not initialize another database or create replacement accounts. '
            'Ask the owner to locate the existing trial data first.'
        )
    if (database.parent.parent / ('.' + database.parent.name + '.rumi-restore.json')).exists():
        raise TrialLaunchError('An interrupted restore needs scripts/recovery.py repair for the explicit data directory. Nothing initialized.')
    secret_file = database.parent / 'secret.key'
    if not secret_file.is_file() or not secret_file.read_text(encoding='utf-8').strip():
        raise TrialLaunchError('The existing runtime\\development\\secret.key is missing or empty. Restore the matching secret; this launcher will not generate one.')
    # Read-only SQLite inspection occurs before importing settings, which could
    # otherwise create runtime directories/secrets for an unintended database.
    try:
        connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()
    except sqlite3.Error:
        raise TrialLaunchError('The intended database cannot be read. Check its file permissions and ask the owner to inspect it; no data was changed.') from None
    required = {'auth_user', 'django_migrations', 'django_session', 'clinic_patient', 'clinic_loginattempt', 'clinic_auditevent'}
    if not required.issubset(tables):
        raise TrialLaunchError(
            'The intended database is missing required tables. No migrations were applied. '
            'Confirm this is the correct existing database, then follow README migration instructions manually.'
        )
    try:
        import django
        django.setup()
        from django.conf import settings
        from django.db import connection as django_connection
        from django.db.migrations.executor import MigrationExecutor
        if Path(settings.DATABASES['default']['NAME']).resolve() != database:
            raise TrialLaunchError('Resolved Django database differs from runtime\\development\\clinic.sqlite3. Startup stopped.')
        executor = MigrationExecutor(django_connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        django_connection.close()
        if pending:
            raise TrialLaunchError(
                'Required migrations are pending. Nothing was applied. Open PowerShell in this folder, '
                'set DJANGO_SETTINGS_MODULE=config.settings and RUMI_DATA_DIR to this runtime\\development, '
                'confirm the selected database, then manually run .\\.venv\\Scripts\\python.exe manage.py migrate.'
            )
    except ImportError:
        raise TrialLaunchError('A required Python package is unavailable in .venv. Follow the README dependency-installation instructions manually.') from None
    from clinic.trial_identity import identity_proof
    secret = secret_file.read_text(encoding='utf-8').strip()
    challenge = secrets.token_hex(32)
    proof = identity_proof(secret, challenge, ROOT, database)
    print('Rumi Dental Care - Phase 1 trial', flush=True)
    print(f'Project: {ROOT}', flush=True)
    print(f'Python: {sys.executable}', flush=True)
    print('Settings: config.settings', flush=True)
    print(f'Database: {database}', flush=True)
    print('Required migrations: applied (read-only check).', flush=True)
    return challenge, proof


def port_occupied():
    # A closed Windows TCP port can time out rather than immediately refusing a
    # connection. Probe bind availability instead of guessing from TCP timing.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(ADDRESS)
            return False
        except OSError as exc:
            if exc.errno in [errno.EADDRINUSE, errno.EACCES] or getattr(exc, 'winerror', None) in [10013, 10048]:
                return True
            # Ambiguous failures must never be interpreted as permission to start.
            raise TrialLaunchError('Cannot determine whether localhost port 8000 is available. Check the local port/firewall; no server was started.') from None


def application_ready(challenge, expected, timeout=1):
    from clinic.trial_identity import APPLICATION, CHALLENGE_HEADER, READY_PATH
    request = Request(URL.rstrip('/') + READY_PATH, headers={CHALLENGE_HEADER: challenge})
    # Bypass proxy environment settings; this request must stay on loopback.
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
            if response.status != 200 or response.geturl() != request.full_url:
                return False
            data = json.loads(response.read(4096))
        if not isinstance(data, dict):
            return False
        proof = data.get('proof')
        return data.get('application') == APPLICATION and isinstance(proof, str) and len(proof) == 64 and proof.isascii() and hmac.compare_digest(proof, expected)
    except (OSError, URLError, ValueError):
        return False


def wait_until_ready(challenge, expected, stopped, timeout=READY_TIMEOUT):
    deadline = time.monotonic() + timeout
    while not stopped.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        if application_ready(challenge, expected, timeout=min(1, remaining)):
            return True
        stopped.wait(min(.15, max(0, deadline - time.monotonic())))
    return False


def open_browser(enabled):
    print(f'Ready: {URL}', flush=True)
    if enabled:
        try:
            opened = webbrowser.open(URL)
        except Exception:
            opened = False
        if not opened:
            print('The default browser could not be opened. Enter the Ready address in your browser.', flush=True)


def launch(challenge, proof, browser=True):
    if port_occupied():
        if not application_ready(challenge, proof):
            raise TrialLaunchError(
                'Port 8000 is occupied, but its identity cannot be verified as this checkout using this database. '
                'It may be another program, another data directory, or an older Rumi server. '
                'Return to its console and stop it yourself with Ctrl+C only if it is the old Rumi trial, then retry. '
                'No process was killed and no other port was selected.'
            )
        print('Verified existing Rumi trial server; reusing it without starting another process.', flush=True)
        print('Keep the ORIGINAL server console open. Ctrl+C there stops it. Closing the browser does not stop the server.', flush=True)
        open_browser(browser)
        return 0
    print('Keep this window open while using the application.', flush=True)
    print('Press Ctrl+C in this window to stop. Closing only the browser does not stop the server.', flush=True)
    stopped = threading.Event()
    failed = threading.Event()

    def monitor():
        if wait_until_ready(challenge, proof, stopped):
            open_browser(browser)
        elif not stopped.is_set():
            failed.set()
            print('Application readiness could not be verified within 15 seconds. Browser not opened; stopping this trial startup.', flush=True)
            _thread.interrupt_main()

    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        from django.core.management import call_command
        call_command('runserver', '127.0.0.1:8000', insecure_serving=True, use_reloader=False)
    except KeyboardInterrupt:
        pass
    except SystemExit as exc:
        if exc.code not in [None, 0]:
            raise TrialLaunchError('Trial server stopped during startup. Review the console message above.') from None
    finally:
        stopped.set()
        watcher.join(timeout=2)
    return 1 if failed.is_set() else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Only inspect the intended environment/database; never start a server.')
    parser.add_argument('--no-browser', action='store_true', help='Run readiness checks without opening a browser (verification use).')
    args = parser.parse_args()
    try:
        challenge, proof = preflight()
        if args.check:
            return 0
        return launch(challenge, proof, browser=not args.no_browser)
    except TrialLaunchError as exc:
        print(f'\nStartup stopped: {exc}', file=sys.stderr, flush=True)
        return 1
    except Exception as exc:
        # No traceback/request/credential details in the interactive window.
        print(f'\nStartup stopped ({type(exc).__name__}). Ask the owner to inspect the local setup; no automatic repairs were made.', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, lambda *_: _thread.interrupt_main())
    sys.exit(main())
