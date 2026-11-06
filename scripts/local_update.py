"""Offline-safe existing-installation maintenance; explicit data selection required."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--apply', action='store_true', help='Create verified complete safety backup, then apply pending migrations with server stopped.')
    args = parser.parse_args()
    data = Path(args.data_dir)
    if not data.is_absolute():
        parser.error('Select an absolute existing data directory.')
    data = data.resolve()
    selected = os.environ.get('RUMI_DATA_DIR')
    if selected and Path(selected).resolve() != data:
        parser.error('RUMI_DATA_DIR conflicts with --data-dir. Resolve the selection first; nothing changed.')
    if not (data / 'clinic.sqlite3').is_file() or not (data / 'clinic.sqlite3').stat().st_size or not (data / 'secret.key').is_file() or not (data / 'secret.key').read_text().strip():
        parser.error('Existing complete runtime required. Recover the original database and matching secret; no initialization or replacement accounts.')
    journal = data.parent / ('.' + data.name + '.rumi-restore.json')
    if journal.exists():
        parser.error('Interrupted restore requires standalone recovery repair before updates.')
    os.environ.update(DJANGO_SETTINGS_MODULE='config.settings', RUMI_DATA_DIR=str(data))
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from clinic.backups.locks import lease, lock_path
    from scripts.complete_safety_backup import create
    with lease(lock_path(data, 'server')):
        pending = MigrationExecutor(connection).migration_plan(MigrationExecutor(connection).loader.graph.leaf_nodes())
        connection.close()
        print('Selected runtime:', data)
        print('Pending migration count:', len(pending))
        if args.apply:
            create(data)
            call_command('migrate', interactive=False)
        elif pending:
            raise SystemExit('Update required. Stop Rumi and rerun with --apply; a verified complete safety backup is mandatory.')
        call_command('check')


if __name__ == '__main__':
    main()
