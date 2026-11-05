from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from .forms import PatientForm
from .models import AuditEvent, LoginAttempt, Patient
from .phones import normalize_phone
from .views import doctor_group

FORMATS = ['03001234567', '0300 1234567', '0300-1234567', '+923001234567', '00923001234567']

class PhoneTests(SimpleTestCase):
    def test_equivalent_pakistani_formats(self):
        for value in FORMATS:
            with self.subTest(value=value):
                self.assertEqual(normalize_phone(value), '+923001234567')

    def test_international_numbers(self):
        self.assertEqual(normalize_phone('+44 20 7946 0958'), '+442079460958')
        self.assertEqual(normalize_phone('0012025550123'), '+12025550123')

    def test_invalid_numbers(self):
        for value in ['', '123', 'not a phone', '+999123456789', '03001234567<script>', '03001234567 ext 5']:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize_phone(value)

class ClinicTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser('owner', password='fictional-test-only-489!')
        cls.doctor = User.objects.create_user('doctor', password='fictional-test-only-489!')
        cls.doctor.groups.add(doctor_group())
        cls.patient = Patient.objects.create(full_name='Fictional Patient', phone=FORMATS[0], created_by=cls.owner, updated_by=cls.owner)

    def setUp(self):
        self.client.force_login(self.doctor)

    def test_anonymous_all_patient_and_account_endpoints_blocked(self):
        self.client.logout()
        for path in ['/', '/patients/', '/patients/new/', f'/patients/{self.patient.pk}/', f'/patients/{self.patient.pk}/edit/', '/accounts/']:
            for method in ['get', 'post']:
                with self.subTest(path=path, method=method):
                    self.assertEqual(getattr(self.client, method)(path).status_code, 302)

    def test_doctor_permission_boundaries(self):
        for path in ['/', '/patients/', '/patients/new/', f'/patients/{self.patient.pk}/', f'/patients/{self.patient.pk}/edit/']:
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/accounts/').status_code, 403)
        self.assertEqual(self.client.get('/audit/').status_code, 403)
        self.assertEqual(self.client.post('/audit/').status_code, 403)
        self.assertEqual(self.client.post('/accounts/', {'username': 'bad'}).status_code, 403)
        self.assertFalse(self.doctor.is_staff)
        self.assertFalse(self.doctor.is_superuser)
        self.assertFalse(self.doctor.has_perm('clinic.delete_patient'))
        self.assertFalse(self.doctor.has_perm('clinic.change_auditevent'))
        self.assertEqual(self.client.get('/admin/').status_code, 404)
        self.assertEqual(self.client.post(f'/patients/{self.patient.pk}/delete/').status_code, 404)

    def test_unassigned_user_denied(self):
        self.client.force_login(User.objects.create_user('unassigned'))
        self.assertEqual(self.client.get('/').status_code, 403)
        self.assertEqual(self.client.post('/patients/new/', {'full_name': 'No Access', 'phone': FORMATS[0]}).status_code, 403)

    def test_create_edit_and_audit(self):
        response = self.client.post('/patients/new/', {'full_name': 'Fictional New', 'phone': '+442079460958', 'approximate_age': '35'})
        self.assertEqual(response.status_code, 302)
        patient = Patient.objects.get(full_name='Fictional New')
        self.assertEqual(patient.created_by, self.doctor)
        self.assertEqual(patient.age_recorded_on, timezone.localdate())
        self.assertIsNone(patient.date_of_birth)
        number = patient.number
        self.client.get(response.url)
        response = self.client.post(f'/patients/{patient.pk}/edit/', {'full_name': 'Fictional Edited', 'phone': '+442079460958', 'approximate_age': '35', 'allergies': 'None confirmed'})
        self.assertEqual(response.status_code, 302)
        patient.refresh_from_db()
        self.assertEqual(patient.number, number)
        self.assertEqual(patient.full_name, 'Fictional Edited')
        self.assertEqual(patient.updated_by, self.doctor)
        self.assertEqual(list(AuditEvent.objects.filter(patient=patient, action__in=['create', 'view', 'update']).order_by('pk').values_list('action', flat=True)), ['create', 'view', 'update'])
        event = AuditEvent.objects.filter(patient=patient).first()
        self.assertEqual(event.actor, self.doctor)
        self.assertEqual({f.name for f in event._meta.fields}, {'id', 'actor', 'patient', 'action', 'occurred_at', 'object_type', 'object_id'})

    def test_patient_numbers_unique_and_permanent(self):
        other = Patient.objects.create(full_name='Other', phone=FORMATS[0], created_by=self.owner, updated_by=self.owner)
        self.assertNotEqual(other.number, self.patient.number)
        other.number = 'RDC-REPLACEMENT'
        with self.assertRaises(ValueError):
            other.save()

    def test_equivalent_searches_and_whatsapp(self):
        self.patient.whatsapp = '+442079460958'
        self.patient.save()
        for query in [*FORMATS, '+44 20 7946 0958', 'Fictional', self.patient.number, self.patient.number.lower(), '0300', '1234567']:
            with self.subTest(query=query):
                response = self.client.post('/patients/', {'query': query})
                self.assertContains(response, self.patient.number)
                self.assertEqual(response.context['page'].paginator.count, 1)
        self.assertNotContains(self.client.get('/patients/?query=03001234567'), self.patient.number)

    def test_shared_phone_duplicate_confirmation(self):
        data = {'full_name': 'Fictional Family Member', 'phone': '00923001234567', 'approximate_age': 12}
        response = self.client.post('/patients/new/', data)
        self.assertContains(response, 'Possible duplicate')
        self.assertContains(response, self.patient.number)
        self.assertEqual(Patient.objects.count(), 1)
        data['confirm_shared_phone'] = 'on'
        self.assertEqual(self.client.post('/patients/new/', data).status_code, 302)
        response = self.client.post('/patients/', {'query': FORMATS[0]})
        self.assertEqual(response.context['page'].paginator.count, 2)
        self.assertContains(response, 'About 12 years')

    def test_pagination_and_minimum_input(self):
        for i in range(24):
            Patient.objects.create(full_name=f'Fictional Family {i:02}', phone=FORMATS[0], created_by=self.owner, updated_by=self.owner)
        response = self.client.post('/patients/', {'query': 'Fictional'})
        self.assertEqual(len(response.context['page']), 20)
        response = self.client.post('/patients/', {'query': 'Fictional', 'page': 2})
        self.assertEqual(len(response.context['page']), 5)
        self.assertEqual(self.client.post('/patients/', {'query': 'Fictional', 'page': 'bad'}).status_code, 200)
        for query in ['030', 'a']:
            response = self.client.post('/patients/', {'query': query})
            self.assertTrue(response.context['search_error'])
            self.assertEqual(response.context['page'].paginator.count, 0)
        self.assertContains(self.client.post('/patients/', {'query': 'No Match Ever'}), 'Register new patient')

    def test_invalid_patient_inputs(self):
        invalid = [{'phone': '123'}, {'approximate_age': '-1'}, {'approximate_age': '121'}, {'approximate_age': 'nonsense'}, {'date_of_birth': '2100-01-01'}, {'date_of_birth': '1800-01-01'}, {'date_of_birth': '2020-99-01'}, {'date_of_birth': '2000-01-01', 'approximate_age': 26}, {'whatsapp': 'bad'}, {'full_name': ' '}]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                form = PatientForm({'full_name': 'Fictional Valid', 'phone': '+442079460958', **overrides})
                self.assertFalse(form.is_valid())

    def test_approximate_age_recording_date_preserved(self):
        self.patient.approximate_age = 35
        self.patient.age_recorded_on = timezone.localdate() - timedelta(days=400)
        self.patient.save()
        recorded = self.patient.age_recorded_on
        form = PatientForm({'full_name': 'Renamed', 'phone': FORMATS[0], 'approximate_age': 35}, instance=self.patient)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.age_recorded_on, recorded)
        form = PatientForm({'full_name': 'Renamed', 'phone': FORMATS[0], 'approximate_age': 36}, instance=self.patient)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.save().age_recorded_on, timezone.localdate())

    def test_csrf_for_mutations_and_search(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.doctor)
        for path in ['/patients/new/', f'/patients/{self.patient.pk}/edit/', '/logout/', '/patients/']:
            self.assertEqual(client.post(path, {'full_name': 'CSRF attempt'}).status_code, 403)
        self.assertEqual(client.post('/login/', {'username': 'doctor'}).status_code, 403)
        client.force_login(self.owner)
        self.assertEqual(client.post('/accounts/', {}).status_code, 403)
        client.get('/patients/new/')
        response = client.post('/patients/new/', {'full_name': 'CSRF Fictional', 'phone': '+442079460958', 'csrfmiddlewaretoken': client.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 302)

    def test_escaping_and_not_recorded(self):
        self.patient.full_name = '<script>alert(1)</script>'
        self.patient.allergies = '<img src=x onerror=alert(1)>'
        self.patient.save()
        response = self.client.get(f'/patients/{self.patient.pk}/')
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;img')
        self.assertContains(response, 'Not recorded')

    def test_privacy_headers(self):
        for path in ['/', '/patients/', f'/patients/{self.patient.pk}/', '/accounts/', '/login/']:
            response = self.client.get(path)
            self.assertIn('no-store', response.headers['Cache-Control'])
            self.assertIn('private', response.headers['Cache-Control'])
            self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')
            self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
            self.assertIn("default-src 'self'", response.headers['Content-Security-Policy'])

    def test_owner_creates_restricted_doctor(self):
        self.client.force_login(self.owner)
        response = self.client.post('/accounts/', {'username': 'newdoctor', 'password1': 'Trial-only-unique-9372!', 'password2': 'Trial-only-unique-9372!'})
        self.assertEqual(response.status_code, 302)
        doctor = User.objects.get(username='newdoctor')
        self.assertTrue(doctor.check_password('Trial-only-unique-9372!'))
        self.assertTrue(doctor.has_perm('clinic.add_patient'))
        self.assertFalse(doctor.has_perm('auth.add_user'))
        self.assertFalse(doctor.is_superuser or doctor.is_staff)

    def test_owner_weak_password_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post('/accounts/', {'username': 'weakdoctor', 'password1': '123', 'password2': '123'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='weakdoctor').exists())

    def test_logout_is_post_only(self):
        self.assertEqual(self.client.get('/logout/').status_code, 405)
        self.assertEqual(self.client.post('/logout/').status_code, 302)
        self.assertEqual(self.client.get('/patients/').status_code, 302)

    def test_idle_session_settings_and_expiry(self):
        from django.conf import settings
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
        from django.contrib.sessions.models import Session
        Session.objects.filter(session_key=self.client.session.session_key).update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get('/patients/').status_code, 302)

    def test_login_throttle_persists_and_expires(self):
        self.client.logout()
        for _ in range(5):
            self.assertEqual(self.client.post('/login/', {'username': 'doctor', 'password': 'wrong'}).status_code, 200)
        self.assertEqual(self.client.post('/login/', {'username': 'doctor', 'password': 'fictional-test-only-489!'}).status_code, 429)
        LoginAttempt.objects.update(window_started=timezone.now() - timedelta(minutes=16))
        self.assertEqual(self.client.post('/login/', {'username': 'doctor', 'password': 'fictional-test-only-489!'}).status_code, 302)

    def test_profile_view_records_actor(self):
        self.client.get(f'/patients/{self.patient.pk}/')
        event = AuditEvent.objects.get()
        self.assertEqual((event.actor, event.patient, event.action), (self.doctor, self.patient, 'view'))

    def test_secure_doctor_command(self):
        from django.core.management import call_command
        from io import StringIO
        with patch('clinic.management.commands.create_doctor.getpass', return_value='Trial-only-command-3874!'):
            call_command('create_doctor', 'commanddoctor', stdout=StringIO())
        doctor = User.objects.get(username='commanddoctor')
        self.assertTrue(doctor.has_perm('clinic.view_patient'))
        self.assertFalse(doctor.is_staff or doctor.is_superuser)

    def test_owner_disables_and_enables_doctor(self):
        doctor_client = Client()
        doctor_client.force_login(self.doctor)
        self.client.force_login(self.owner)
        response = self.client.post('/accounts/', {'action': 'disable', 'account_id': self.doctor.pk})
        self.assertEqual(response.status_code, 302)
        self.doctor.refresh_from_db()
        self.assertFalse(self.doctor.is_active)
        self.assertEqual(doctor_client.get('/patients/').status_code, 302)
        self.assertEqual(self.client.post('/accounts/', {'action': 'disable', 'account_id': self.owner.pk}).status_code, 404)
        self.client.post('/accounts/', {'action': 'enable', 'account_id': self.doctor.pk})
        self.doctor.refresh_from_db()
        self.assertTrue(self.doctor.is_active)

    def test_owner_readonly_audit(self):
        self.client.get(f'/patients/{self.patient.pk}/')
        self.client.force_login(self.owner)
        response = self.client.get('/audit/')
        self.assertContains(response, self.patient.number)
        self.assertEqual(self.client.post('/audit/').status_code, 405)

    def test_form_accepts_formatted_long_international_number(self):
        form = PatientForm({'full_name': 'Fictional International', 'phone': '+1 (202) 555-0123', 'whatsapp': '+44 (20) 7946 0958'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['phone'], '+12025550123')

    def test_csrf_rejections_have_privacy_headers(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post('/patients/new/')
        self.assertEqual(response.status_code, 403)
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_browser_login_origin_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.get('/login/')
        token = client.cookies['csrftoken'].value
        data = {'username': 'doctor', 'password': 'fictional-test-only-489!', 'csrfmiddlewaretoken': token}
        self.assertEqual(client.post('/login/', data, HTTP_ORIGIN='http://evil.example').status_code, 403)
        self.assertEqual(client.post('/login/', data, HTTP_ORIGIN='null').status_code, 403)
        self.assertEqual(client.post('/login/', data, HTTP_ORIGIN='http://testserver').status_code, 302)
