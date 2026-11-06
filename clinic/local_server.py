"""Loopback WSGI lifetime and cooperative file control. No PID-based termination."""
from contextlib import ExitStack
import logging
import secrets
import threading
import time

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from .backups.archive import atomic_json, read_json
from .backups.locks import Busy, lease, lock_path


class RequestGate:
    def __init__(self, app):
        self.app = app
        self.condition = threading.Condition()
        self.active = 0
        self.closing = False

    def __call__(self, environ, start_response):
        with self.condition:
            if self.closing and environ.get('PATH_INFO') != '/_local/trial-ready/':
                start_response('503 Service Unavailable', [('Content-Type', 'text/plain'), ('Retry-After', '5'), ('Cache-Control', 'no-store')])
                return [b'Rumi is stopping safely. Keep unsaved forms open; start again before retrying.']
            self.active += 1
        def stream():
            result = None
            try:
                result = self.app(environ, start_response)
                yield from result
            finally:
                try:
                    if hasattr(result, 'close'):
                        result.close()
                finally:
                    with self.condition:
                        self.active -= 1
                        self.condition.notify_all()
        return stream()


def control_paths(data):
    return data / 'local-server.json', data / 'local-stop.json'


def serve(port=8000):
    from waitress import create_server
    from whitenoise import WhiteNoise
    from .backups.jobs import start_scheduler, wait_for_jobs
    data = settings.DATA_DIR
    state_path, stop_path = control_paths(data)
    token = secrets.token_hex(32)
    # Waitress must not emit request paths or raw exception messages.
    logging.getLogger('waitress').handlers = [logging.NullHandler()]
    logging.getLogger('waitress').propagate = False
    with lease(lock_path(data, 'server')):
        app = WhiteNoise(get_wsgi_application(), root=str(settings.BASE_DIR / 'static'), prefix='static/', max_age=0)
        gate = RequestGate(app)
        server = create_server(gate, host='127.0.0.1', port=port, threads=4, expose_tracebacks=False, channel_timeout=30)
        scheduler = start_scheduler(data)
        atomic_json(state_path, {'token': token, 'status': 'running'})
        finished = threading.Event()
        drained = threading.Event()

        def stop_monitor():
            while not finished.wait(.2):
                try:
                    request = read_json(stop_path, 4096) if stop_path.exists() else {}
                    if request.get('token') != token:
                        continue
                except (OSError, ValueError):
                    continue
                with gate.condition:
                    gate.closing = True
                atomic_json(state_path, {'token': token, 'status': 'waiting for requests and backup jobs'})
                scheduler[0].set()
                scheduler[1].join()  # Prevent a scheduler tick starting a new job after drain.
                with gate.condition:
                    while gate.active:
                        gate.condition.wait(.2)
                wait_for_jobs(data)
                # Jobs may outlive the request which queued them. Never interrupt them.
                while not finished.is_set():
                    try:
                        with ExitStack() as stack:
                            stack.enter_context(lease(lock_path(data, 'job')))
                            stack.enter_context(lease(lock_path(data, 'access')))
                            drained.set()
                            return
                    except Busy:
                        finished.wait(.2)
        watcher = threading.Thread(target=stop_monitor, daemon=True, name='rumi-orderly-stop')
        watcher.start()
        try:
            while not drained.is_set():
                server.asyncore.loop(timeout=.2, count=1, map=server._map)
        finally:
            with gate.condition:
                gate.closing = True
            scheduler[0].set()
            scheduler[1].join()
            with gate.condition:
                while gate.active:
                    gate.condition.wait(.2)
            wait_for_jobs(data)
            finished.set()
            watcher.join(timeout=2)
            server.task_dispatcher.shutdown()
            server.asyncore.close_all(server._map)
            # Do not release the lifetime lease while backup workers still run.
            while True:
                try:
                    with lease(lock_path(data, 'job')):
                        break
                except Busy:
                    time.sleep(.2)
            atomic_json(state_path, {'token': token, 'status': 'stopped'})
