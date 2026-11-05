import json
import logging
from pathlib import Path
import sys
import tempfile
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from .diagnostics import SafeDiagnosticHandler
from django.contrib.auth.models import User
from .models import Patient
from .views import doctor_group


class InternationalSearchTests(TestCase):
    def setUp(self):
        doctor = User.objects.create_user('review-doctor')
        doctor.groups.add(doctor_group())
        self.client.force_login(doctor)
        self.patient = Patient.objects.create(full_name='Fictional Review', phone='+442079460958', created_by=doctor, updated_by=doctor)
    def test_partial_00_international_matches_plus_and_preserves_minimums(self):
        self.patient.phone = '+442079460958'
        self.patient.save()
        for query in ['+442079', '00442079', '0044 2079', '00442079460958']:
            response = self.client.post('/patients/', {'query': query})
            self.assertEqual(response.context['page'].paginator.count, 1)
        self.assertTrue(self.client.post('/patients/', {'query': '004'}).context['search_error'])


class DiagnosticTests(SimpleTestCase):
    def test_sensitive_content_never_formatted(self):
        sensitive = 'PASSWORD_PHONE_03001234567_PATIENT_CLINICAL_NOTES_QUERY_SECRET'
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=Path(directory)):
            handler = SafeDiagnosticHandler(max_bytes=500, backup_count=2)
            try:
                try:
                    private_local = sensitive
                    raise ValueError(private_local)
                except ValueError:
                    record = logging.LogRecord('django.request', logging.ERROR, sensitive, 1, sensitive, (), sys.exc_info())
                    record.request = type('Request', (), {'POST': sensitive, 'body': sensitive, 'path': sensitive, 'META': {'QUERY_STRING': sensitive}})()
                    for _ in range(20):
                        handler.emit(record)
            finally:
                handler.close()
            files = list((Path(directory) / 'diagnostics').glob('*'))
            self.assertLessEqual(len(files), 3)
            self.assertGreater(len(files), 1)
            for file in files:
                data = file.read_text()
                self.assertNotIn(sensitive, data)
                self.assertNotIn('private_local', data)
                for line in data.splitlines():
                    event = json.loads(line)
                    self.assertEqual(event['exception'], 'ValueError')
                    self.assertEqual(set(event), {'time_utc', 'event_id', 'category', 'severity', 'exception', 'locations'})

    def test_diagnostic_write_failure_does_not_print_original_record(self):
        from unittest.mock import patch
        handler = SafeDiagnosticHandler()
        with patch('pathlib.Path.mkdir', side_effect=OSError('private error')), patch('sys.stderr') as stderr:
            handler.emit(logging.LogRecord('django.security.csrf', logging.WARNING, '', 0, 'private request body', (), None))
            stderr.write.assert_not_called()
        handler.close()
