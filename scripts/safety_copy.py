"""Consistent pre-migration SQLite/secret safety copy; NOT Phase 5 backups.

Stop the clinic server before invoking. Does not initialize or migrate a database.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parent.parent

def main():
    data = Path(os.environ.get('RUMI_DATA_DIR', ROOT / 'runtime/development')).resolve()
    database, secret = data / 'clinic.sqlite3', data / 'secret.key'
    if not database.is_file() or not database.stat().st_size or not secret.is_file():
        raise SystemExit('Existing database and matching secret are required. Nothing initialized.')
    directory = data / 'safety-copies' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(directory / 'clinic.sqlite3')) as target:
            source.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or target.execute('PRAGMA foreign_key_check').fetchall():
                raise SystemExit('Safety copy verification failed. Do not migrate.')
            counts = {}
            fingerprints = {}
            for (table,) in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                quoted = '"' + table.replace('"', '""') + '"'
                rows = source.execute('SELECT * FROM ' + quoted + ' ORDER BY rowid').fetchall()
                copied = target.execute('SELECT * FROM ' + quoted + ' ORDER BY rowid').fetchall()
                if rows != copied:
                    raise SystemExit('Safety copy row verification failed. Do not migrate.')
                counts[table] = len(rows)
                fingerprints[table] = hashlib.sha256(repr(rows).encode()).hexdigest()
    shutil.copyfile(secret, directory / 'secret.key')
    if secret.read_bytes() != (directory / 'secret.key').read_bytes():
        raise SystemExit('Secret safety copy verification failed. Do not migrate.')
    (directory / 'manifest.json').write_text(json.dumps({'purpose': 'pre-migration safety copy; not Phase 5 backup',
        'created_utc': datetime.now(timezone.utc).isoformat(), 'row_counts': counts, 'table_fingerprints': fingerprints,
        'database_sha256': hashlib.sha256((directory / 'clinic.sqlite3').read_bytes()).hexdigest()}, indent=2), encoding='utf-8')
    print('Verified consistent database + matching secret safety copy:', directory)
    print('Readability, foreign keys and all existing table rows verified. NOT a complete/encrypted/off-device Phase 5 backup.')

if __name__ == '__main__':
    main()
