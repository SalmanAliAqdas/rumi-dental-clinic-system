"""Complete local safety snapshot, including host configuration; never a cloud backup."""
from pathlib import Path
import json
import os
import shutil
import sys
from datetime import datetime, timezone
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from clinic.backups.archive import snapshot, digest, atomic_json, inspect_database, check_attachments
from clinic.backups.locks import lease, lock_path


def create(data):
    data = Path(data).resolve()
    if not (data / 'clinic.sqlite3').is_file() or not (data / 'secret.key').is_file():
        raise RuntimeError('Existing database and matching secret required; nothing initialized.')
    destination = ROOT / 'runtime' / 'phase6-safety' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    destination.mkdir(parents=True)
    with lease(lock_path(data, 'job')), lease(lock_path(data, 'backup-config')):
        stage = destination / 'data'
        stage.mkdir()
        info = snapshot(data, stage)
        # Include machine configuration separately; portable recovery intentionally excludes it.
        if (data / 'backup-control').exists():
            shutil.copytree(data / 'backup-control', destination / 'backup-control')
        inventory = {p.relative_to(destination).as_posix(): digest(p) for p in destination.rglob('*') if p.is_file()}
        atomic_json(destination / 'safety-manifest.json', {'source': str(data), 'created_at': datetime.now(timezone.utc).isoformat(), 'files': inventory, 'row_counts': info['row_counts']})
        assert all(digest(destination / name) == value for name, value in inventory.items())
        assert inspect_database(stage / 'clinic.sqlite3')['row_counts'] == info['row_counts']
        check_attachments(stage, info)
    print('Complete local safety backup verified:', destination)
    print('Database, matching secret, all attachments, portable settings and existing host backup configuration retained. Local plaintext safety copy; keep private.')
    return destination


if __name__ == '__main__':
    create(os.environ.get('RUMI_DATA_DIR', ROOT / 'runtime/development'))
