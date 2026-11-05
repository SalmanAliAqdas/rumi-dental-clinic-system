"""Allowlisted local diagnostics: never format a LogRecord or exception text."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import traceback
import uuid

SAFE_EXCEPTIONS = frozenset(['OperationalError', 'IntegrityError', 'ValidationError', 'PermissionDenied',
    'SuspiciousOperation', 'DisallowedHost', 'ValueError', 'TypeError', 'KeyError', 'OSError',
    'FileNotFoundError', 'RuntimeError', 'TemplateSyntaxError', 'NoReverseMatch', 'Http404'])


class SafeDiagnosticHandler(logging.Handler):
    def __init__(self, max_bytes=262144, backup_count=3):
        super().__init__(logging.WARNING)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.writer = None

    def emit(self, record):
        try:
            from django.conf import settings
            event_id = getattr(getattr(record, 'request', None), '_rumi_error_id', '')
            if not isinstance(event_id, str) or not re.fullmatch('[0-9a-f]{32}', event_id):
                event_id = uuid.uuid4().hex
            category = 'security_rejection' if record.name.startswith('django.security') else 'server_error'
            payload = {'time_utc': datetime.now(timezone.utc).isoformat(), 'event_id': event_id,
                       'category': category, 'severity': 'ERROR' if record.levelno >= logging.ERROR else 'WARNING'}
            if record.exc_info and record.exc_info[0]:
                name = record.exc_info[0].__name__
                payload['exception'] = name if name in SAFE_EXCEPTIONS else 'UnhandledException'
                locations = []
                for frame, line in traceback.walk_tb(record.exc_info[2]):
                    try:
                        source = Path(frame.f_code.co_filename).resolve().relative_to(settings.BASE_DIR).as_posix()
                        if re.fullmatch(r'(clinic|config)/[A-Za-z0-9_/]+\.py', source):
                            locations.append({'source': source, 'line': int(line)})
                    except ValueError:
                        continue
                payload['locations'] = locations[-8:]
            if self.writer is None:
                directory = settings.DATA_DIR / 'diagnostics'
                directory.mkdir(parents=True, exist_ok=True)
                self.writer = RotatingFileHandler(directory / 'events.log', maxBytes=self.max_bytes,
                                                 backupCount=self.backup_count, encoding='utf-8')
                self.writer.setFormatter(logging.Formatter('%(message)s'))
            safe_record = logging.LogRecord('safe', record.levelno, '', 0, json.dumps(payload), (), None)
            self.writer.emit(safe_record)
        except Exception:
            # Logging failures must not fall back to printing the unsafe record.
            return

    def close(self):
        if self.writer:
            self.writer.close()
        super().close()
