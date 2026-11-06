from datetime import datetime, timedelta, timezone as utc
from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase, Client
from django.utils import timezone
from .models import (Patient, Appointment, PersonalTask, WorkflowEvent, WorkflowLock, Prescription,
    PrescriptionCorrection, PrescriberProfile, ClinicPrintSettings, Visit, AuditEvent)
from .views import doctor_group
from . import workflow_services as s

class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=User.objects.create_superuser('workflowowner',password='Fictional-only-7362!')
        cls.doctor=User.objects.create_user('workflowdoctor',password='Fictional-only-7362!')
        cls.doctor.groups.add(doctor_group())
        cls.second=User.objects.create_user('workflowsecond',password='Fictional-only-7362!')
        cls.second.groups.add(doctor_group())
        cls.patient=Patient.objects.create(full_name='Fictional Workflow',phone='03001234567',allergies='Fictional allergy',created_by=cls.owner,updated_by=cls.owner)
        cls.other=Patient.objects.create(full_name='Fictional Other Workflow',phone='03007654321',created_by=cls.owner,updated_by=cls.owner)
    def setUp(self):
        self.client.force_login(self.doctor)
        self.now=timezone.now().replace(second=0,microsecond=0)
    def booking(self,offset=0,patient=None,actor=None,**kwargs):
        starts=self.now+timedelta(minutes=60+offset)
        return s.save_appointment(actor or self.doctor,patient or self.patient,
            dict(starts_at=starts,ends_at=starts+timedelta(minutes=30),purpose='Fictional review',notes='Fictional note'),uuid4(),**kwargs)
    def status(self,a,status,actor=None,**kwargs):
        a.refresh_from_db()
        return s.change_appointment(actor or self.doctor,a,a.revision,uuid4(),status,'Fictional status reason',**kwargs)
    def aurl(self,a,suffix='',patient=None):
        return f'/patients/{(patient or self.patient).pk}/appointments/{a.pk}/'+suffix
    def rx(self,**kwargs):
        data=dict(prescribed_on=s.today(),visit=None,advice='Fictional doctor-entered advice',follow_up='Fictional review',medications=[dict(name='Fictional medication',strength_form='Fictional form',dose='Fictional entered dose',route='Fictional route',frequency='Fictional frequency',duration='Fictional duration',quantity='Fictional quantity',instructions='Fictional instructions')])
        data.update(kwargs)
        return s.save_prescription(self.doctor,self.patient,data,uuid4())
    def issue(self,rx):
        PrescriberProfile.objects.get_or_create(user=self.doctor,defaults={'display_name':'Fictional Clinician'})
        return s.issue_prescription(self.doctor,rx,rx.revision,uuid4(),True)
    def rxurl(self,rx,suffix='',patient=None):
        return f'/patients/{(patient or self.patient).pk}/prescriptions/{rx.pk}/'+suffix
    def test_creation_times_overlap_confirmation_and_adjacent_bookings(self):
        a=self.booking()
        with self.assertRaises(s.Overlap):self.booking()
        with self.assertRaises(s.Overlap):self.booking(overlap_confirm=True)
        b=self.booking(overlap_confirm=True,overlap_reason='Fictional intentional overlap')
        self.assertTrue(b.history.first().after['overlap_confirmed'])
        self.booking(offset=30)
        with self.assertRaises(ValidationError):s.save_appointment(self.doctor,self.patient,dict(starts_at=self.now,ends_at=self.now,purpose='Bad',notes=''),uuid4())
        self.status(a,'cancelled');self.status(b,'no_show')
        self.booking()
    def test_duplicate_creation_stale_changes_and_reschedule_history(self):
        starts=self.now+timedelta(hours=1);data=dict(starts_at=starts,ends_at=starts+timedelta(minutes=30),purpose='Original purpose',notes='Original note')
        token=uuid4();a=s.save_appointment(self.doctor,self.patient,data,token)
        self.assertEqual(a.pk,s.save_appointment(self.doctor,self.patient,data,token).pk)
        oldrevision=a.revision
        updated={**data,'starts_at':starts+timedelta(hours=2),'ends_at':starts+timedelta(hours=3),'purpose':'Rescheduled'}
        a=s.save_appointment(self.owner,self.patient,updated,uuid4(),appointment=a,revision=a.revision,reason='Patient requested new time')
        self.assertEqual(a.history.last().before['purpose'],'Original purpose')
        self.assertEqual(a.history.last().before['notes'],'Original note')
        with self.assertRaises(s.Conflict):s.save_appointment(self.doctor,self.patient,data,uuid4(),appointment=a,revision=oldrevision,reason='Stale')
        with self.assertRaises(ValidationError):a.delete()
    def test_status_explicit_current_unique_and_no_clock_automation(self):
        a=self.booking(offset=-180);b=self.booking(offset=-240)
        self.assertEqual(a.status,'scheduled');self.assertTrue(a.overdue)
        self.status(a,'in_treatment')
        with self.assertRaises(ValidationError):self.status(b,'in_treatment')
        self.status(a,'completed');self.status(b,'in_treatment')
        a.refresh_from_db();self.assertEqual(a.status,'completed')
        self.assertEqual(s.queue_context(self.doctor)['current_appointment'].pk,b.pk)
    def test_walkin_arrival_queue_and_recorded_adjustment(self):
        a=self.booking(walk_in=True);b=self.booking(offset=30,walk_in=True)
        self.assertEqual(a.status,'arrived');self.assertTrue(a.is_walk_in)
        self.assertIsNotNone(a.arrived_at)
        self.assertEqual(s.queue_context(self.doctor)['next_appointment'].pk,a.pk)
        adjusted=self.now-timedelta(minutes=5)
        self.status(b,'arrived',queue_at=adjusted)
        self.assertEqual(s.queue_context(self.doctor)['next_appointment'].pk,b.pk)
        self.assertEqual(b.history.last().reason,'Fictional status reason')
        self.assertIsNotNone(b.history.last().before['queue_at'])
    def test_midnight_today_queue_and_overdue_separation(self):
        with patch('clinic.workflow_services.timezone.now',return_value=datetime(2026,11,6,18,59,tzinfo=utc.utc)):
            self.now=timezone.now();old=self.booking(offset=-100);future=self.booking(offset=0)
            context=s.queue_context(self.doctor)
            self.assertEqual(context['business_day'].isoformat(),'2026-11-06')
            self.assertIsNone(context['next_appointment'])
            self.assertIn(old.pk,[x.pk for x in context['overdue_appointments']])
        with patch('clinic.workflow_services.timezone.now',return_value=datetime(2026,11,6,19,0,tzinfo=utc.utc)):
            context=s.queue_context(self.doctor)
            self.assertEqual(context['business_day'].isoformat(),'2026-11-07')
            self.assertEqual(context['next_appointment'].pk,future.pk)
            old.refresh_from_db();self.assertEqual(old.status,'scheduled')
    def test_start_visit_idempotency_existing_link_and_status_independence(self):
        a=self.booking();token=uuid4()
        v=s.start_appointment_visit(self.doctor,a,a.revision,token,True)
        self.assertEqual(v.pk,s.start_appointment_visit(self.doctor,a,a.revision,token,True).pk)
        self.assertEqual(v.pk,s.start_appointment_visit(self.doctor,a,a.revision,uuid4(),True).pk)
        self.assertEqual(Visit.objects.count(),1)
        self.status(a,'completed');v.refresh_from_db();self.assertEqual(v.status,'in_progress')
        self.assertTrue(AuditEvent.objects.filter(action='appointment_visit').exists())
    def test_visit_link_cross_patient_and_cancelled_rejection(self):
        a=self.booking();b=self.booking(offset=60,patient=self.other)
        v=s.start_appointment_visit(self.doctor,b,b.revision,uuid4(),True)
        self.status(b,'completed')
        with self.assertRaises(ValidationError):s.start_appointment_visit(self.doctor,a,a.revision,uuid4(),True,existing_visit=v)
        self.status(a,'cancelled');a.refresh_from_db()
        with self.assertRaises(ValidationError):s.start_appointment_visit(self.doctor,a,a.revision,uuid4(),True)
    def test_reactivation_requires_explicit_overlap_confirmation(self):
        a=self.booking();self.status(a,'cancelled');self.booking()
        with self.assertRaises(s.Overlap):self.status(a,'scheduled')
        self.status(a,'scheduled',overlap_confirm=True,overlap_reason='Intentional reactivation')
    def test_personal_tasks_carry_forward_and_ownership(self):
        due=self.now-timedelta(days=2)
        task=s.save_task(self.doctor,dict(title='Fictional personal task',notes='Private notes',due_at=due),uuid4())
        self.assertEqual(task.status,'Overdue')
        self.assertIn(task.pk,[x.pk for x in s.queue_context(self.doctor)['personal_tasks']])
        self.client.force_login(self.owner)
        for suffix in ['', 'complete/','reopen/']:
            self.assertEqual(self.client.get(f'/tasks/{task.pk}/'+suffix).status_code,404)
            self.assertEqual(self.client.post(f'/tasks/{task.pk}/'+suffix,dict(token=uuid4(),revision=task.revision)).status_code,404)
        self.assertNotContains(self.client.get('/tasks/'),'Private notes')
        task=s.save_task(self.doctor,{},uuid4(),task,task.revision,'complete');self.assertEqual(task.status,'Completed')
        self.client.force_login(self.doctor);self.assertContains(self.client.get('/tasks/?view=completed'),'Fictional personal task')
        task=s.save_task(self.doctor,{},uuid4(),task,task.revision,'reopen');self.assertEqual(task.status,'Overdue');self.assertEqual(task.due_at,due)
    def test_task_duplicate_and_stale_edits(self):
        token=uuid4();data=dict(title='Fictional task',notes='',due_at=None)
        task=s.save_task(self.doctor,data,token);self.assertEqual(task.pk,s.save_task(self.doctor,data,token).pk)
        old=task.revision;task=s.save_task(self.doctor,{},uuid4(),task,old,'complete')
        with self.assertRaises(s.Conflict):s.save_task(self.doctor,data,uuid4(),task,old)
        self.assertEqual(task.history.count(),2)
    def test_prescription_draft_issue_snapshot_and_immutable_original(self):
        rx=self.rx();self.assertEqual(rx.state,'Draft')
        with self.assertRaises(ValidationError):s.issue_prescription(self.doctor,rx,rx.revision,uuid4(),False)
        with self.assertRaises(ValidationError):s.issue_prescription(self.doctor,rx,rx.revision,uuid4(),True)
        rx=self.issue(rx);self.assertEqual(rx.state,'Issued')
        original=rx.snapshot.copy();self.patient.full_name='Changed fictional name';self.patient.save()
        ClinicPrintSettings.objects.create(pk=1,name='Changed clinic')
        rx.refresh_from_db();self.assertEqual(rx.snapshot,original)
        self.assertEqual(rx.snapshot['clinician']['user_id'],self.doctor.pk)
        with self.assertRaises(ValidationError):rx.save()
        with self.assertRaises(ValidationError):rx.delete()
        self.assertContains(self.client.get(self.rxurl(rx,'print/')),'Fictional Workflow')
        self.assertNotContains(self.client.get(self.rxurl(rx,'print/')),'Changed clinic')
    def test_prescription_owner_only_and_other_clinician_impersonation_denied(self):
        rx=self.rx();self.client.force_login(self.owner)
        for path in [f'/patients/{self.patient.pk}/prescriptions/new/',self.rxurl(rx,'edit/'),self.rxurl(rx,'issue/'),self.rxurl(rx,'correct/'),'/my-clinician-details/']:
            self.assertEqual(self.client.get(path).status_code,403,path)
            self.assertEqual(self.client.post(path,dict(token=uuid4(),prescriber=self.doctor.pk)).status_code,403,path)
        self.assertEqual(self.client.get(self.rxurl(rx)).status_code,200)
        self.assertEqual(self.client.get(self.rxurl(rx,'print/')).status_code,200)
        self.client.force_login(self.second)
        self.assertEqual(self.client.get(self.rxurl(rx,'edit/')).status_code,404)
        self.assertEqual(self.client.get(self.rxurl(rx,'issue/')).status_code,403)
    def test_prescription_complete_fields_and_issue_retry(self):
        rx=self.rx(medications=[{'name':'Fictional incomplete'}])
        PrescriberProfile.objects.create(user=self.doctor,display_name='Fictional Clinician')
        with self.assertRaises(ValidationError):s.issue_prescription(self.doctor,rx,rx.revision,uuid4(),True)
        rx=self.rx();token=uuid4()
        s.issue_prescription(self.doctor,rx,rx.revision,token,True)
        self.assertEqual(s.issue_prescription(self.doctor,rx,rx.revision,token,True).pk,rx.pk)
        with self.assertRaises(s.Conflict):s.issue_prescription(self.doctor,rx,rx.revision,uuid4(),True)
    def test_replacement_and_void_history(self):
        rx=self.issue(self.rx());token=uuid4()
        replacement=s.correct_prescription(self.second,rx,token,'Fictional correction',True)
        self.assertEqual(replacement.prescriber_id,self.second.pk)
        self.assertEqual(replacement.state,'Draft')
        self.assertEqual(s.correct_prescription(self.second,rx,token,'Fictional correction',True).pk,replacement.pk)
        self.assertEqual(rx.state,'Voided / replaced')
        self.assertTrue(rx.snapshot)
        self.assertContains(self.client.get(self.rxurl(rx,'print/')),'VOIDED')
        with self.assertRaises(ValidationError):s.correct_prescription(self.doctor,rx,uuid4(),'Again')
        other=self.issue(self.rx());s.correct_prescription(self.doctor,other,uuid4(),'Fictional void')
        self.assertIsNone(other.correction.replacement)
    def test_rx_and_appointment_cross_patient_tampering(self):
        rx=self.rx();a=self.booking()
        for path in [self.rxurl(rx,patient=self.other),self.rxurl(rx,'print/',self.other),self.rxurl(rx,'issue/',self.other),self.aurl(a,patient=self.other),self.aurl(a,'visit/',self.other),self.aurl(a,'print/',self.other)]:
            self.assertEqual(self.client.get(path).status_code,404,path)
        b=self.booking(offset=60,patient=self.other);v=s.start_appointment_visit(self.doctor,b,b.revision,uuid4(),True)
        with self.assertRaises(ValidationError):self.rx(visit=v)
    def test_print_privacy_draft_labels_and_reminder_fallback(self):
        rx=self.rx();a=self.booking()
        response=self.client.get(self.rxurl(rx,'print/'))
        self.assertContains(response,'DRAFT')
        for text in [self.other.full_name,'Outstanding payments','personal tasks','Net collections']:
            self.assertNotContains(response,text)
        self.assertNotContains(self.client.get(self.aurl(a,'print/')),self.other.full_name)
        details=s.reminder_details(a)
        self.assertFalse(details['whatsapp_url'])
        details=s.reminder_details(a,True)
        self.assertTrue(details['whatsapp_url'].startswith('https://wa.me/923001234567?text='))
        for text in ['Fictional review','Fictional note','Fictional allergy',self.patient.full_name,'PKR']:
            self.assertNotIn(text,details['reminder_text'])
        before=a.history.count();self.client.get(self.aurl(a,'reminder/'));self.assertEqual(a.history.count(),before)
        with self.assertRaises(ValidationError):s.confirm_reminder(self.doctor,a,uuid4(),'sent',False)
        token=uuid4();s.confirm_reminder(self.doctor,a,token,'copied',True);s.confirm_reminder(self.doctor,a,token,'copied',True)
        self.assertEqual(a.history.last().after['activity'],'copied')
        self.assertEqual(a.history.count(),before+1)
    def test_validated_whatsapp_preferred_and_bad_number_rejected(self):
        self.patient.whatsapp='03007654321';self.patient.save();a=self.booking()
        self.assertEqual(s.reminder_details(a)['reminder_number'],'+923007654321')
        Patient.objects.filter(pk=self.patient.pk).update(whatsapp='bad')
        a=Appointment.objects.select_related('patient').get(pk=a.pk)
        with self.assertRaises(ValidationError):s.reminder_details(a)
    def test_anonymous_csrf_escaping_and_panel_privacy(self):
        a=self.booking();rx=self.rx()
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.doctor)
        for path in [self.aurl(a,'status/'),f'/patients/{self.patient.pk}/appointments/new/','/tasks/new/',self.rxurl(rx,'issue/')]:
            self.assertEqual(secure.post(path,dict(token=uuid4())).status_code,403,path)
        self.client.logout()
        for path in ['/schedule/','/dashboard/panels/','/tasks/',self.aurl(a),self.rxurl(rx,'print/')]:self.assertEqual(self.client.get(path).status_code,302,path)
        self.client.force_login(self.doctor)
        task=s.save_task(self.doctor,dict(title='<script>bad</script>',notes='<img src=x>',due_at=None),uuid4())
        self.assertContains(self.client.get('/tasks/'),'&lt;script&gt;')
        panel=self.client.get('/dashboard/panels/');self.assertIn('no-store',panel.headers['Cache-Control'])
        self.assertNotIn('net',panel.context);self.assertNotContains(panel,'combined')
        self.doctor.is_active=False;self.doctor.save();self.assertEqual(self.client.get('/dashboard/panels/').status_code,302)
    def test_print_configuration_permissions_and_stale_updates(self):
        with self.assertRaises(PermissionDenied):s.save_print_settings(self.doctor,dict(name='Clinic',address='',contact=''),uuid4(),0)
        s.save_print_settings(self.owner,dict(name='Fictional clinic',address='Fictional address',contact='Fictional contact'),uuid4(),0)
        with self.assertRaises(s.Conflict):s.save_print_settings(self.owner,dict(name='Stale',address='',contact=''),uuid4(),0)
        self.assertEqual(s.clinic_details()['name'],'Fictional clinic')
        s.save_print_settings(self.doctor,dict(display_name='Fictional Doctor',qualifications='',registration='',contact=''),uuid4(),0,True)
        self.assertEqual(PrescriberProfile.objects.get(user=self.doctor).display_name,'Fictional Doctor')
    def test_prescription_form_default_date_and_valid_draft_post(self):
        page=self.client.get(f'/patients/{self.patient.pk}/prescriptions/new/')
        self.assertContains(page,'value="'+s.today().isoformat()+'"')
        payload=dict(token=uuid4(),revision=0,prescribed_on=s.today().isoformat(),**{'meds-TOTAL_FORMS':1,'meds-INITIAL_FORMS':0,'meds-0-name':'Fictional HTTP medication','meds-0-dose':'Fictional dose','meds-0-route':'Fictional route','meds-0-frequency':'Fictional frequency','meds-0-duration':'Fictional duration'})
        response=self.client.post(f'/patients/{self.patient.pk}/prescriptions/new/',payload)
        self.assertEqual(response.status_code,302)
        rx=Prescription.objects.get()
        self.assertEqual(rx.prescriber_id,self.doctor.pk)
        self.assertContains(self.client.get(response.url),'Review and issue')

    def test_draft_edit_stale_revision_and_existing_visit_link(self):
        a=self.booking()
        from .clinical_services import ensure_medical_review
        visit=Visit.objects.create(patient=self.patient,clinician=self.doctor,created_by=self.doctor,updated_by=self.doctor,medical_review=ensure_medical_review(self.patient,self.doctor))
        self.assertEqual(s.start_appointment_visit(self.doctor,a,a.revision,uuid4(),True,visit).pk,visit.pk)
        self.assertEqual(Visit.objects.count(),1)
        rx=self.rx(visit=visit);old=rx.revision
        content=dict(prescribed_on=rx.prescribed_on,visit=visit,medications=rx.medications,advice='Fictional revised advice',follow_up='')
        rx=s.save_prescription(self.doctor,self.patient,content,uuid4(),rx,old)
        self.assertEqual(rx.advice,'Fictional revised advice')
        with self.assertRaises(s.Conflict):s.save_prescription(self.doctor,self.patient,content,uuid4(),rx,old)
        self.assertEqual(rx.history.count(),2)

    def test_due_today_task_and_rearrival_retains_old_history(self):
        fixed=datetime(2026,11,6,8,tzinfo=utc.utc)
        with patch('clinic.workflow_services.timezone.now',return_value=fixed):
            task=s.save_task(self.doctor,dict(title='Due today',notes='',due_at=fixed+timedelta(hours=1)),uuid4())
            self.assertEqual(task.status,'Due today')
            a=self.booking(walk_in=True);arrival=a.arrived_at
            self.status(a,'cancelled')
        with patch('clinic.workflow_services.timezone.now',return_value=fixed+timedelta(hours=2)):
            self.status(a,'arrived');a.refresh_from_db()
            self.assertGreater(a.arrived_at,arrival)
            self.assertEqual(a.history.last().before['arrived_at'],arrival.isoformat())

    def test_financial_boundaries_remain_on_new_dashboard(self):
        for path in ['/finance/reports/','/finance/export/','/finance/today/?date=2020-01-01']:
            self.assertEqual(self.client.get(path).status_code,403)
        response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,'Net collections')
        self.assertNotIn('combined_balance',response.context)
    def test_patient_booking_and_walkin_http_and_stale_status(self):
        values=dict(starts_at=(self.now+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),ends_at=(self.now+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),purpose='Fictional HTTP appointment',revision=0,token=uuid4())
        response=self.client.post(f'/patients/{self.patient.pk}/appointments/new/?walkin=1',values)
        self.assertEqual(response.status_code,302)
        a=Appointment.objects.get();self.assertEqual(a.status,'arrived')
        response=self.client.post(self.aurl(a,'status/'),dict(token=uuid4(),revision=0,status='completed',reason='Stale'))
        self.assertEqual(response.status_code,409)
    def test_prescription_form_medication_tampering_and_future_dates(self):
        a=self.booking(patient=self.other);v=s.start_appointment_visit(self.doctor,a,a.revision,uuid4(),True)
        values=dict(token=uuid4(),revision=0,prescribed_on=s.today().isoformat(),visit=v.pk,**{'meds-TOTAL_FORMS':1,'meds-INITIAL_FORMS':0,'meds-0-name':'Fictional'})
        self.assertEqual(self.client.post(f'/patients/{self.patient.pk}/prescriptions/new/',values).status_code,400)
        with self.assertRaises(ValidationError):self.rx(prescribed_on=s.today()+timedelta(days=1))
        self.assertEqual(self.client.get('/schedule/?date=bad').status_code,400)

from django.test import TransactionTestCase
from django.db import connection

class WorkflowConcurrencyTests(TransactionTestCase):
    def test_file_backed_concurrent_booking_and_visit_start(self):
        import os, subprocess, sys, tempfile, sqlite3
        from contextlib import closing
        from pathlib import Path
        from django.conf import settings
        WorkflowLock.objects.get_or_create(pk=1)
        actor=User.objects.create_user('workflowrace')
        actor.groups.add(doctor_group())
        Patient.objects.create(full_name='Fictional workflow race',phone='03001234567',created_by=actor,updated_by=actor)
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(Path(directory)/'clinic.sqlite3')) as target:connection.connection.backup(target)
            (Path(directory)/'secret.key').write_text('fictional-workflow-race-secret-not-used-elsewhere')
            env={**os.environ,'RUMI_DATA_DIR':directory,'DJANGO_SETTINGS_MODULE':'config.settings','PYTHONUTF8':'1'}
            script='''import django,sys
from datetime import timedelta
from uuid import UUID
django.setup()
from django.contrib.auth import get_user_model
from django.utils import timezone
from clinic import workflow_services as s
from clinic.models import Patient,Appointment
actor=get_user_model().objects.get(username='workflowrace')
patient=Patient.objects.get(full_name='Fictional workflow race')
token=UUID(sys.argv[2])
try:
    if sys.argv[1]=='book':
        start=timezone.now().replace(second=0,microsecond=0)+timedelta(hours=1)
        row=s.save_appointment(actor,patient,dict(starts_at=start,ends_at=start+timedelta(minutes=30),purpose='Fictional race',notes=''),token)
    else:
        a=Appointment.objects.get()
        row=s.start_appointment_visit(actor,a,a.revision,token,True)
    print('saved',row.pk)
except s.Overlap:
    print('overlap')
'''
            def race(mode,tokens):
                procs=[subprocess.Popen([sys.executable,'-c',script,mode,str(token)],cwd=settings.BASE_DIR,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for token in tokens]
                result=[]
                for p in procs:
                    out,err=p.communicate(timeout=40);self.assertEqual(p.returncode,0,err);result.append(out.strip())
                return result
            result=race('book',[uuid4(),uuid4()])
            self.assertEqual(result.count('overlap'),1,result)
            self.assertEqual(sum(r.startswith('saved') for r in result),1,result)
            result=race('visit',[uuid4(),uuid4()])
            self.assertEqual(result[0],result[1],result)
            with closing(sqlite3.connect(Path(directory)/'clinic.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM clinic_visit').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM clinic_appointment WHERE visit_id IS NOT NULL').fetchone()[0],1)
