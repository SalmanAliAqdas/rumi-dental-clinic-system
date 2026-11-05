import json
import os
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TestCase

from clinic.trial_identity import APPLICATION, READY_PATH, identity_proof
from scripts import trial_launcher


class ReadinessTests(TestCase):
    def test_loopback_proof_matches_checkout_database_and_python(self):
        challenge = 'a' * 64
        response = self.client.get(READY_PATH, REMOTE_ADDR='127.0.0.1', HTTP_X_RUMI_TRIAL_CHALLENGE=challenge)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'application': APPLICATION, 'proof': identity_proof(
            settings.SECRET_KEY, challenge, settings.BASE_DIR, connection.settings_dict['NAME'],
        )})
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertNotContains(response, settings.SECRET_KEY)
        self.assertNotContains(response, str(settings.BASE_DIR))

    def test_unsigned_malformed_and_nonlocal_requests_not_exposed(self):
        for address, challenge in [('127.0.0.1', ''), ('127.0.0.1', 'bad'), ('192.0.2.1', 'a' * 64)]:
            self.assertEqual(self.client.get(READY_PATH, REMOTE_ADDR=address, HTTP_X_RUMI_TRIAL_CHALLENGE=challenge).status_code, 404)
        self.assertEqual(self.client.post(READY_PATH).status_code, 405)

    def test_pending_migrations_are_not_reported_ready(self):
        with patch('django.db.migrations.executor.MigrationExecutor') as executor:
            executor.return_value.migration_plan.return_value = [object()]
            response = self.client.get(READY_PATH, REMOTE_ADDR='127.0.0.1', HTTP_X_RUMI_TRIAL_CHALLENGE='a' * 64)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('proof', response.json())


class LauncherTests(SimpleTestCase):
    def test_identity_rejects_another_checkout_database_python_or_secret(self):
        args = ['secret', 'a' * 64, '/project', '/data/clinic.sqlite3', '/python']
        expected = identity_proof(*args)
        for index in range(len(args)):
            altered = args.copy()
            altered[index] += '-different'
            self.assertNotEqual(identity_proof(*altered), expected)

    def test_environment_selection_overrides_wrong_terminal_from_other_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory(prefix='rumi project spaces ') as directory:
            root = Path(directory)
            with patch.object(trial_launcher, 'ROOT', root), patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'wrong.settings', 'RUMI_DATA_DIR': 'wrong-directory'}):
                try:
                    os.chdir(root.parent)
                    database = trial_launcher.configure()
                    self.assertEqual(Path.cwd(), root)
                    self.assertEqual(database, root / 'runtime/development/clinic.sqlite3')
                    self.assertEqual(os.environ['DJANGO_SETTINGS_MODULE'], 'config.settings')
                    self.assertEqual(os.environ['RUMI_DATA_DIR'], str(root / 'runtime/development'))
                finally:
                    os.chdir(original)
                    if str(root) in __import__('sys').path:
                        __import__('sys').path.remove(str(root))

    def test_verified_server_reused_without_starting_another_server(self):
        with patch.object(trial_launcher, 'port_occupied', return_value=True), patch.object(trial_launcher, 'application_ready', return_value=True), patch.object(trial_launcher, 'open_browser') as browser, patch('django.core.management.call_command') as command:
            self.assertEqual(trial_launcher.launch('challenge', 'proof'), 0)
            browser.assert_called_once_with(True)
            command.assert_not_called()

    def test_unknown_occupied_port_never_opens_browser_or_starts_server(self):
        with patch.object(trial_launcher, 'port_occupied', return_value=True), patch.object(trial_launcher, 'application_ready', return_value=False), patch.object(trial_launcher, 'open_browser') as browser, patch('django.core.management.call_command') as command:
            with self.assertRaisesMessage(trial_launcher.TrialLaunchError, 'identity cannot be verified'):
                trial_launcher.launch('challenge', 'proof')
            browser.assert_not_called()
            command.assert_not_called()

    def test_readiness_wait_has_a_deadline(self):
        started = time.monotonic()
        with patch.object(trial_launcher, 'application_ready', return_value=False):
            self.assertFalse(trial_launcher.wait_until_ready('challenge', 'proof', threading.Event(), timeout=.03))
        self.assertLess(time.monotonic() - started, 2)

    def test_identity_response_must_have_correct_proof(self):
        for payload, expected in [({'application': APPLICATION, 'proof': 'b' * 64}, False), ([], False), ({'application': APPLICATION, 'proof': 'a' * 64}, True)]:
            with patch.object(trial_launcher, 'build_opener') as opener:
                response = opener.return_value.open.return_value.__enter__.return_value
                response.status = 200
                response.geturl.return_value = trial_launcher.URL.rstrip('/') + READY_PATH
                response.read.return_value = json.dumps(payload).encode()
                self.assertEqual(trial_launcher.application_ready('c' * 64, 'a' * 64), expected)
