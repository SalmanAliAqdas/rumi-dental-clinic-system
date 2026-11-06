"""Private-data-free proof that a listener uses this checkout and database."""
import hashlib
import hmac
import os
from pathlib import Path
import re
import sys

APPLICATION = 'rumi-dental-care-local-v2'
CHALLENGE_HEADER = 'X-Rumi-Trial-Challenge'
READY_PATH = '/_local/trial-ready/'


def valid_challenge(value):
    return bool(re.fullmatch(r'[0-9a-f]{64}', value))


def identity_proof(secret, challenge, project, database, python=None):
    executable = Path(python or sys.executable)
    # pythonw is the no-console entry to the same virtual environment interpreter.
    if executable.name.lower() == 'pythonw.exe':
        executable = executable.with_name('python.exe')
    paths = [project, database, executable]
    normalized = [os.path.normcase(str(Path(path).resolve())) for path in paths]
    payload = '\n'.join([APPLICATION, challenge, *normalized])
    return hmac.new(secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
