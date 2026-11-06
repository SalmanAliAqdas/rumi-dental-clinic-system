"""Fail safely when the local trial selects an uninitialized database."""
from pathlib import Path
import os
import socket

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import Command as StaticRunserverCommand
from django.core.management.base import CommandError
from django.core.servers.basehttp import WSGIServer
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor


class ExclusiveTrialServer(WSGIServer):
    # Windows SO_REUSEADDR can allow two servers to bind the same address,
    # sending a browser to a different database than the intended trial.
    allow_reuse_address = False

    def __init__(self, *args, **kwargs):
        kwargs['allow_reuse_address'] = False
        super().__init__(*args, **kwargs)

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Command(StaticRunserverCommand):
    server_cls = ExclusiveTrialServer

    def inner_run(self, *args, **kwargs):
        from clinic.backups.locks import lease, lock_path, Busy
        self._backup_lifetime = True
        self._backup_scheduler = None
        try:
            with lease(lock_path(settings.DATA_DIR, 'server')):
                return super().inner_run(*args, **kwargs)
        except Busy:
            raise CommandError('This runtime is already served or under offline restoration. Nothing started.') from None
        finally:
            if self._backup_scheduler:
                self._backup_scheduler[0].set()
                self._backup_scheduler[1].join(timeout=2)

    def check_migrations(self):
        connection = connections[DEFAULT_DB_ALIAS]
        database = str(connection.settings_dict['NAME'])
        instruction = (
            f'Trial server not started: database is not initialized or has pending migrations.\n'
            f'Selected database: {database}\n'
            'Set RUMI_DATA_DIR to the directory containing your existing clinic database. '
            'Use that SAME directory for migrate, account commands and runserver. '
            'After confirming the directory, run python manage.py migrate, then restart. '
            'Do not create replacement accounts or reset an existing database.'
        )
        if connection.vendor == 'sqlite' and database != ':memory:' and not database.startswith('file:'):
            path = Path(database)
            if not path.is_file() or path.stat().st_size == 0:
                raise CommandError(instruction)
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise CommandError(instruction)
        self.stdout.write(f'Trial data directory: {settings.DATA_DIR}')

        if getattr(self, '_backup_lifetime', False) and not self._backup_scheduler and os.environ.get('RUMI_DISABLE_BACKUP_SCHEDULER') != '1':
            from clinic.backups.jobs import start_scheduler
            self._backup_scheduler = start_scheduler(settings.DATA_DIR)
