"""Private-data-free proof that a listener uses this checkout and database."""
import hashlib
import hmac
import os
from pathlib import Path
import re
import sys

APPLICATION = 'rumi-dental-care-phase1-trial-v1'
CHALLENGE_HEADER = 'X-Rumi-Trial-Challenge'
READY_PATH = '/_local/trial-ready/'


def valid_challenge(value):
    return bool(re.fullmatch(r'[0-9a-f]{64}', value))


def identity_proof(secret, challenge, project, database, python=None):
    paths = [project, database, python or sys.executable]
    normalized = [os.path.normcase(str(Path(path).resolve())) for path in paths]
    payload = '\n'.join([APPLICATION, challenge, *normalized])
    return hmac.new(secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
