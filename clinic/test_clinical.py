from contextlib import closing
from io import BytesIO
from pathlib import Path
import tempfile
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image
from pypdf import PdfWriter
from .attachments import validate_upload, stored_path
from .clinical_services import current_medical
from .models import (Patient, Visit, MedicalReview, VisitAmendment, Procedure, TreatmentPlan,
                     PlanItem, PerformedWork, ToothObservation, Attachment, AuditEvent)
from .teeth import TEETH, validate_teeth
from .views import doctor_group

def image_upload(name='fictional.png', size=(24, 24)):
    buffer = BytesIO()
    Image.new('RGB', size, color='blue').save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')

def pdf_upload(script=False):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    if script:
        writer.add_js('app.alert("fictional test");')
    buffer = BytesIO()
    writer.write(buffer)
    return SimpleUploadedFile('fictional.pdf', buffer.getvalue(), content_type='application/pdf')


class ClinicalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser('clinicalowner', password='Fictional-only-7362!')
        cls.doctor = User.objects.create_user('clinicaldoctor', password='Fictional-only-7362!')
        cls.doctor.groups.add(doctor_group())
        cls.patient = Patient.objects.create(full_name='Fictional Clinical', phone='03001234567', allergies='Fictional allergy', created_by=cls.owner, updated_by=cls.owner)
        cls.other = Patient.objects.create(full_name='Fictional Other', phone='+442079460958', created_by=cls.owner, updated_by=cls.owner)
        cls.procedure = Procedure.objects.create(name='Fictional procedure')

    def setUp(self):
        self.client.force_login(self.doctor)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings_override = override_settings(DATA_DIR=Path(self.temporary.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def visit_data(self, **values):
        return {'visit_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'clinician': self.doctor.pk,
                'status': 'in_progress', 'revision': 0, 'medical_reviewed': 'on', 'chief_complaint': 'Fictional complaint',
                'performed_treatment': 'Fictional work recorded', 'teeth': ['11', '55'], **values}

    def start(self, patient=None, **values):
        patient = patient or self.patient
        response = self.client.post(f'/patients/{patient.pk}/visits/new/', self.visit_data(**values))
        self.assertEqual(response.status_code, 302, response.content[:1500])
        return patient.visits.order_by('-pk').first()

    def complete(self, visit):
        response = self.client.post(f'/patients/{visit.patient_id}/visits/{visit.pk}/edit/', self.visit_data(revision=visit.revision, action='complete'))
        self.assertEqual(response.status_code, 302, response.content[:1500])
        visit.refresh_from_db()
        self.assertEqual(visit.status, 'completed')

    def upload(self, file=None, patient=None, **values):
        patient = patient or self.patient
        return self.client.post(f'/patients/{patient.pk}/attachments/upload/', {'title': 'Fictional image', 'category': 'photo', 'file': file or image_upload(), **values})

    def test_role_boundaries_and_anonymous_routes(self):
        visit = self.start()
        urls = [f'/patients/{self.patient.pk}/clinical/{section}/' for section in ['visits', 'medical', 'chart', 'plans', 'attachments']]
        urls += [f'/patients/{self.patient.pk}/visits/{visit.pk}/', f'/patients/{self.patient.pk}/visits/{visit.pk}/edit/', '/catalogue/']
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get('/accounts/').status_code, 403)
        self.assertEqual(self.client.get('/audit/').status_code, 403)
        self.assertFalse(self.doctor.has_perm('clinic.delete_visit'))
        self.assertFalse(self.doctor.has_perm('clinic.change_medicalreview'))
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(User.objects.create_user('unassigned-clinical'))
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.owner)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_visit_multiple_same_day_and_return_history(self):
        first = self.start()
        second = self.start()
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.visit_at, second.visit_at)
        self.assertNotEqual(first.medical_review_id, second.medical_review_id)
        self.assertEqual(first.medical_review.snapshot, second.medical_review.snapshot)
        page = self.client.get(f'/patients/{self.patient.pk}/clinical/visits/')
        self.assertContains(page, 'Fictional complaint', count=2)
        self.assertEqual(list(page.context['page'].object_list), [second, first])

    def test_draft_saved_in_database_and_stale_revision_denied(self):
        visit = self.start()
        endpoint = f'/patients/{self.patient.pk}/visits/{visit.pk}/draft/'
        response = self.client.post(endpoint, self.visit_data(examination='Persisted fictional examination'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['revision'], 1)
        visit.refresh_from_db()
        self.assertEqual(visit.examination, 'Persisted fictional examination')
        response = self.client.post(endpoint, self.visit_data(examination='Stale text'))
        self.assertEqual(response.status_code, 409)
        visit.refresh_from_db()
        self.assertEqual(visit.examination, 'Persisted fictional examination')
        response = self.client.post(f'/patients/{self.patient.pk}/visits/{visit.pk}/edit/', self.visit_data(examination='Unsaved retained text'))
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'Unsaved retained text', status_code=409)

    def test_session_expiry_rejects_draft_without_change(self):
        visit = self.start()
        self.client.logout()
        response = self.client.post(f'/patients/{self.patient.pk}/visits/{visit.pk}/draft/', self.visit_data(examination='Must not persist'))
        self.assertEqual(response.status_code, 401)
        visit.refresh_from_db()
        self.assertEqual(visit.examination, '')

    def test_completed_notes_original_and_amendments_preserved(self):
        visit = self.start()
        self.complete(visit)
        original = visit.chief_complaint
        response = self.client.post(f'/patients/{self.patient.pk}/visits/{visit.pk}/draft/', self.visit_data(revision=visit.revision, chief_complaint='overwrite'))
        self.assertEqual(response.status_code, 409)
        response = self.client.post(f'/patients/{self.patient.pk}/visits/{visit.pk}/amend/', {'reason': 'Fictional correction', 'content': '<script>clinical</script>'})
        self.assertEqual(response.status_code, 302)
        visit.refresh_from_db()
        self.assertEqual(visit.chief_complaint, original)
        amendment = visit.amendments.get()
        self.assertEqual(amendment.author, self.doctor)
        amendment.content = 'replace'
        with self.assertRaises(ValidationError):
            amendment.save()
        visit.chief_complaint = 'replace'
        with self.assertRaises(ValidationError):
            visit.save()
        response = self.client.get(f'/patients/{self.patient.pk}/visits/{visit.pk}/')
        self.assertContains(response, '&lt;script&gt;clinical&lt;/script&gt;')
        self.assertNotContains(response, '<script>clinical</script>')

    def test_completion_requires_documented_complaint_and_performed_work(self):
        visit = self.start()
        response = self.client.post(f'/patients/{self.patient.pk}/visits/{visit.pk}/edit/', self.visit_data(action='complete', performed_treatment=''))
        self.assertContains(response, 'Record the chief complaint')
        visit.refresh_from_db()
        self.assertEqual(visit.status, 'in_progress')

    def test_medical_reviews_do_not_rewrite_visit_context(self):
        first = self.start()
        review_id = first.medical_review_id
        data = {'reason': 'Fictional review'}
        for field in ['medical_history', 'current_medicines', 'allergies', 'medical_alerts']:
            data[field + '_state'] = 'none'
        response = self.client.post(f'/patients/{self.patient.pk}/medical/review/', data)
        self.assertEqual(response.status_code, 302)
        second = self.start()
        self.assertNotEqual(second.medical_review_id, review_id)
        first.refresh_from_db()
        self.assertEqual(first.medical_review.snapshot['allergies']['details'], 'Fictional allergy')
        self.assertEqual(second.medical_review.snapshot['allergies']['state'], 'none')
        review = MedicalReview.objects.get(pk=review_id)
        with self.assertRaises(ValidationError):
            review.save()

    def test_patient_medical_edit_preserves_old_review(self):
        visit = self.start()
        response = self.client.post(f'/patients/{self.patient.pk}/edit/', {'full_name': self.patient.full_name, 'phone': self.patient.phone, 'allergies': 'New fictional allergy'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(visit.medical_review.snapshot['allergies']['details'], 'Fictional allergy')
        self.assertEqual(self.patient.medical_reviews.first().snapshot['allergies']['details'], 'New fictional allergy')

    def test_medical_states_require_details_consistency(self):
        response = self.client.post(f'/patients/{self.patient.pk}/medical/review/', {'reason': 'Review', **{field + '_state': 'details' for field in ['medical_history', 'current_medicines', 'allergies', 'medical_alerts']}})
        self.assertContains(response, 'Record the details')

    def test_fdi_adult_primary_multi_and_general_and_invalid(self):
        self.assertEqual(len(TEETH), 52)
        validate_teeth(['18', '11', '21', '48', '38', '55', '65', '75', '85'])
        validate_teeth([])
        for invalid in [['19'], ['00'], ['59'], ['91'], ['11', '11'], [11], '11']:
            with self.assertRaises(ValidationError):
                validate_teeth(invalid)
        for teeth in [['11', '55'], []]:
            response = self.client.post(f'/patients/{self.patient.pk}/chart/add/', {'observation': 'Fictional observation', 'teeth': teeth, 'area': 'General area'})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(ToothObservation.objects.count(), 2)
        response = self.client.post(f'/patients/{self.patient.pk}/visits/new/', self.visit_data(teeth=['99']))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Visit.objects.count(), 0)

    def test_plan_work_spans_visits_and_catalogue_rename_preserves_label(self):
        response = self.client.post(f'/patients/{self.patient.pk}/plans/new/', {'title': 'Fictional long plan', 'notes': 'Two visits', 'revision': 0})
        self.assertEqual(response.status_code, 302)
        plan = TreatmentPlan.objects.get()
        response = self.client.post(f'/patients/{self.patient.pk}/plans/{plan.pk}/items/new/', {'procedure': self.procedure.pk, 'teeth': ['11'], 'status': 'in_progress', 'revision': 0})
        self.assertEqual(response.status_code, 302)
        item = plan.items.get()
        for _ in range(2):
            visit = self.start()
            response = self.client.post(f'/patients/{self.patient.pk}/visits/{visit.pk}/work/', {'procedure': self.procedure.pk, 'plan_item': item.pk, 'teeth': ['11'], 'notes': 'Fictional staged work'})
            self.assertEqual(response.status_code, 302, response.content[:1500])
            self.complete(visit)
        self.assertEqual(item.work.count(), 2)
        self.procedure.name = 'Renamed catalogue entry'
        self.procedure.save()
        self.assertEqual(item.work.first().procedure_label, 'Fictional procedure')
        response = self.client.post(f'/patients/{self.patient.pk}/plans/{plan.pk}/items/{item.pk}/', {'procedure': self.procedure.pk, 'teeth': ['11'], 'status': 'completed', 'revision': 0})
        self.assertEqual(response.status_code, 302)
        self.assertGreaterEqual(plan.history.count(), 3)

    def test_cross_patient_urls_and_submitted_relationships_denied(self):
        visit = self.start(self.other)
        for suffix in ['', 'edit/', 'work/']:
            self.assertEqual(self.client.get(f'/patients/{self.patient.pk}/visits/{visit.pk}/' + suffix).status_code, 404)
        response = self.client.post(f'/patients/{self.patient.pk}/chart/add/', {'visit': visit.pk, 'observation': 'wrong patient'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ToothObservation.objects.count(), 0)
        self.assertEqual(self.upload(visit=visit.pk).status_code, 200)
        self.assertEqual(Attachment.objects.count(), 0)
        other_plan = TreatmentPlan.objects.create(patient=self.other, title='Other plan', created_by=self.owner)
        item = PlanItem.objects.create(plan=other_plan, procedure=self.procedure)
        own_visit = self.start()
        response = self.client.post(f'/patients/{self.patient.pk}/visits/{own_visit.pk}/work/', {'procedure': self.procedure.pk, 'plan_item': item.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PerformedWork.objects.count(), 0)

    def test_upload_original_thumbnail_preview_download_authorized_and_private(self):
        image = Image.new('RGB', (24, 24), color='blue')
        exif = Image.Exif()
        exif[270] = 'Fictional private original metadata'
        buffer = BytesIO()
        image.save(buffer, format='PNG', exif=exif)
        file = SimpleUploadedFile('fictional.png', buffer.getvalue(), content_type='image/png')
        original = file.read()
        file.seek(0)
        self.assertEqual(self.upload(file=file).status_code, 302)
        attachment = Attachment.objects.get()
        self.assertEqual(stored_path(attachment.storage_name).read_bytes(), original)
        self.assertTrue(stored_path(attachment.thumbnail_name).is_file())
        with Image.open(stored_path(attachment.thumbnail_name)) as thumbnail:
            self.assertFalse(thumbnail.getexif())
            self.assertNotIn(b'Fictional private original metadata', stored_path(attachment.thumbnail_name).read_bytes())
        for mode in ['original', 'thumbnail', 'preview', 'download']:
            url = f'/patients/{self.patient.pk}/attachments/{attachment.pk}/{mode}/'
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response.headers['Cache-Control'])
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
            self.assertNotIn(str(Path(self.temporary.name)), response.headers.get('Content-Disposition', ''))
            b''.join(response.streaming_content)
            response.close()
            self.assertEqual(self.client.get(f'/patients/{self.other.pk}/attachments/{attachment.pk}/{mode}/').status_code, 404)
            anonymous = Client()
            self.assertEqual(anonymous.get(url).status_code, 302)
            unauthorized = Client()
            unauthorized.force_login(User.objects.get_or_create(username='no-file-access')[0])
            self.assertEqual(unauthorized.get(url).status_code, 403)
        self.assertEqual(self.client.get('/media/' + attachment.storage_name).status_code, 404)
        self.assertEqual(AuditEvent.objects.filter(action='attachment_access').count(), 4)

    def test_passive_pdf_download_only_active_pdf_rejected(self):
        self.assertEqual(self.upload(file=pdf_upload(), category='document').status_code, 302)
        attachment = Attachment.objects.get()
        response = self.client.get(f'/patients/{self.patient.pk}/attachments/{attachment.pk}/download/')
        self.assertIn('attachment;', response.headers['Content-Disposition'])
        response.close()
        self.assertEqual(self.client.get(f'/patients/{self.patient.pk}/attachments/{attachment.pk}/preview/').status_code, 404)
        with self.assertRaises(ValidationError):
            validate_upload(pdf_upload(script=True))

    def test_spoofed_executable_svg_html_malformed_and_limits(self):
        bad = [('bad.png', b'<html>patient</html>'), ('bad.jpg', b'\x89PNG fake'), ('bad.pdf', b'%PDF-broken'), ('bad.exe', b'MZexecutable'), ('bad.svg', b'<svg/>'), ('bad.html', b'<html/>')]
        for name, data in bad:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validate_upload(SimpleUploadedFile(name, data))
        with override_settings(RUMI_MAX_UPLOAD_BYTES=4), self.assertRaises(ValidationError):
            validate_upload(image_upload())
        with override_settings(RUMI_MAX_IMAGE_SIDE=10), self.assertRaises(ValidationError):
            validate_upload(image_upload(size=(20, 20)))
        with override_settings(RUMI_MAX_IMAGE_PIXELS=100), self.assertRaises(ValidationError):
            validate_upload(image_upload(size=(20, 20)))

    def test_unsafe_filename_cannot_control_storage_and_missing_file_is_graceful(self):
        self.assertEqual(self.upload(file=image_upload('../../escape.png')).status_code, 302)
        attachment = Attachment.objects.get()
        self.assertNotIn('escape', attachment.storage_name)
        self.assertNotIn('..', attachment.storage_name)
        with self.assertRaises(ValidationError):
            stored_path('../../secret.key')
        stored_path(attachment.storage_name).unlink()
        response = self.client.get(f'/patients/{self.patient.pk}/attachments/{attachment.pk}/download/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'metadata has been preserved', status_code=404)
        self.assertContains(self.client.get(f'/patients/{self.patient.pk}/clinical/attachments/'), 'Original file unavailable')

    def test_failed_upload_rolls_back_database_and_removes_new_files(self):
        with patch('clinic.attachments.audit', side_effect=RuntimeError('sensitive clinical value')):
            response = self.upload()
        self.assertContains(response, 'No new attachment was retained')
        self.assertEqual(Attachment.objects.count(), 0)
        self.assertEqual([p for p in (Path(self.temporary.name) / 'attachments').rglob('*') if p.is_file()], [])

    def test_failed_thumbnail_processing_retains_no_original(self):
        file = image_upload()
        with patch('PIL.Image.Image.save', side_effect=OSError('processing failed')):
            response = self.upload(file=file)
        self.assertContains(response, 'cannot be processed safely')
        self.assertEqual(Attachment.objects.count(), 0)

    def test_csrf_mutations_and_audit_are_protected(self):
        visit = self.start()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.doctor)
        for url in [f'/patients/{self.patient.pk}/visits/new/', f'/patients/{self.patient.pk}/visits/{visit.pk}/draft/', f'/patients/{self.patient.pk}/chart/add/', f'/patients/{self.patient.pk}/attachments/upload/']:
            self.assertEqual(client.post(url, {}).status_code, 403)
        self.complete(visit)
        for action in ['medical_review', 'visit_create', 'visit_complete']:
            event = AuditEvent.objects.filter(action=action).first()
            self.assertEqual(event.actor, self.doctor)
            self.assertEqual(event.patient, self.patient)
        self.assertFalse(self.doctor.has_perm('clinic.change_auditevent'))

    def test_visit_medical_review_cross_patient_validation(self):
        first = self.start()
        other_review = MedicalReview.objects.create(patient=self.other, snapshot=current_medical(self.other), reason='Fictional', reviewed_by=self.doctor)
        first.medical_review = other_review
        with self.assertRaises(ValidationError):
            first.full_clean()
