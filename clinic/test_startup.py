"""Regression coverage for the actual wrong-database login failure."""
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from django.core.management import get_commands
from django.core.servers.basehttp import WSGIRequestHandler, WSGIServer
from django.test import SimpleTestCase

from .management.commands.runserver import ExclusiveTrialServer


class TrialStartupTests(SimpleTestCase):
    def test_runserver_uses_clinic_guard_and_staticfiles(self):
        self.assertEqual(get_commands()['runserver'], 'clinic')
        from django.contrib.staticfiles.management.commands.runserver import Command as StaticCommand
        from .management.commands.runserver import Command
        self.assertTrue(issubclass(Command, StaticCommand))

    def assert_startup_refuses_database(self, directory):
        result = subprocess.run(
            [sys.executable, 'manage.py', 'runserver', '127.0.0.1:0', '--noreload', '--insecure', '--skip-checks'],
            cwd=Path(__file__).resolve().parent.parent,
            env=dict(os.environ, RUMI_DATA_DIR=str(directory)),
            capture_output=True, text=True, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Trial server not started', result.stderr)
        self.assertIn(str((directory / 'clinic.sqlite3').resolve()), result.stderr)
        self.assertIn('RUMI_DATA_DIR', result.stderr)
        self.assertIn('migrate', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertNotIn('Starting development server', result.stdout)

    def test_empty_wrong_database_is_rejected_before_login(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            database = directory / 'clinic.sqlite3'
            database.touch()
            self.assert_startup_refuses_database(directory)
            self.assertEqual(database.stat().st_size, 0)

    def test_missing_database_is_not_silently_created_by_runserver(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            self.assert_startup_refuses_database(directory)
            self.assertFalse((directory / 'clinic.sqlite3').exists())

    def test_pending_migrations_refused_without_changing_existing_records(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            database = directory / 'clinic.sqlite3'
            with closing(sqlite3.connect(database)) as connection:
                with connection:
                    connection.execute('CREATE TABLE preserved_record (value TEXT)')
                    connection.execute("INSERT INTO preserved_record VALUES ('fictional preserved record')")
            before = database.read_bytes()
            self.assert_startup_refuses_database(directory)
            self.assertEqual(database.read_bytes(), before)

    def test_another_server_cannot_share_the_trial_socket(self):
        with ExclusiveTrialServer(('127.0.0.1', 0), WSGIRequestHandler) as first:
            with self.assertRaises(OSError):
                with WSGIServer(first.server_address, WSGIRequestHandler):
                    self.fail('A second server must not accept the same trial address.')
