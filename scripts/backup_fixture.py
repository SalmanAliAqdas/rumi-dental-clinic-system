"""Trusted fictional fixture for backup/recovery tests and the isolated drill."""
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent

SEED=r'''
import os,django,hashlib,json
from pathlib import Path
from uuid import uuid4
from datetime import timedelta
django.setup()
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO
from PIL import Image
from clinic.views import doctor_group
from clinic.models import Patient,Visit,Attachment,PrescriberProfile,ClinicPrintSettings,AuditEvent,Procedure,TreatmentPlan,PlanItem
from clinic.clinical_services import ensure_medical_review
from clinic.attachments import store_attachment
from clinic import finance_services as f,workflow_services as w
owner=User.objects.create_superuser('recoveryowner',password=os.environ['RUMI_FIXTURE_LOGIN'])
doctor=User.objects.create_user('recoverydoctor',password=os.environ['RUMI_FIXTURE_LOGIN']);doctor.groups.add(doctor_group())
p=Patient.objects.create(full_name='Fictional Unicode: Ayesha عائشہ',phone='03001234567',allergies='Fictional allergy',created_by=owner,updated_by=doctor)
other=Patient.objects.create(full_name='Fictional shared phone family',phone='03001234567',created_by=owner,updated_by=owner)
v=Visit.objects.create(patient=p,clinician=doctor,created_by=doctor,updated_by=doctor,chief_complaint='Fictional clinical history',medical_review=ensure_medical_review(p,doctor,force=True))
buffer=BytesIO();Image.new('L',(40,30),color=80).save(buffer,format='PNG')
attachment=Attachment(patient=p,visit=v,uploader=doctor,category='xray',title='Fictional X-ray only')
class Form:
 def save(self,commit=False):return attachment
image=store_attachment(Form(),SimpleUploadedFile('fictional.png',buffer.getvalue(),content_type='image/png'),p,doctor)
a=f.create_account(doctor,p,'Fictional recovery account',uuid4())
plan=TreatmentPlan.objects.create(patient=p,title='Fictional recovery plan',created_by=doctor)
item=PlanItem.objects.create(plan=plan,procedure=Procedure.objects.first())
f.post(doctor,a,'charge','10000',uuid4(),description='Fictional agreed total',plan_item=item,visit=v)
f.post(doctor,a,'payment','3000',uuid4(),method='cash')
f.schedule_account(doctor,a,[{'amount':'2000'},{'amount':'5000'}],'Fictional agreed installments',uuid4())
f.post(doctor,a,'payment','2000',uuid4(),method='bank')
f.expense(owner,dict(spent_on=f.today(),category='Fictional supplies',description='=Fictional formula cell',amount='125.50',method='cash',reference=''),uuid4())
start=timezone.now()+timedelta(hours=1)
appointment=w.save_appointment(doctor,p,dict(starts_at=start,ends_at=start+timedelta(minutes=30),purpose='Fictional recovery appointment',notes=''),uuid4())
w.start_appointment_visit(doctor,appointment,appointment.revision,uuid4(),True,v)
PrescriberProfile.objects.create(user=doctor,display_name='Fictional Recovery Clinician')
ClinicPrintSettings.objects.create(pk=1,name='Fictional Rumi trial',contact='Fictional contact')
rx=w.save_prescription(doctor,p,dict(prescribed_on=f.today(),visit=v,medications=[dict(name='Fictional medication',strength_form='Fictional form',dose='Fictional dose',route='Fictional route',frequency='Fictional frequency',duration='Fictional duration',quantity='',instructions='Fictional instructions')],advice='Fictional advice',follow_up='Fictional follow-up'),uuid4())
w.issue_prescription(doctor,rx,rx.revision,uuid4(),True)
task=w.save_task(doctor,dict(title='Fictional personal recovery task',notes='Fictional notes',due_at=None),uuid4())
from django.test import Client
client=Client(HTTP_HOST='127.0.0.1');assert client.login(username='recoveryowner',password=os.environ['RUMI_FIXTURE_LOGIN'])
assert client.post('/patients/',{'query':'00923001234567'}).status_code==200
expect=dict(patient_id=p.pk,patient_number=p.number,visit_id=v.pk,attachment_id=image.pk,account_id=a.pk,appointment_id=appointment.pk,rx_id=rx.pk,task_id=task.pk,image_path=image.storage_name,image_sha256=hashlib.sha256((settings.DATA_DIR/'attachments'/image.storage_name).read_bytes()).hexdigest(),secret_sha256=hashlib.sha256((settings.DATA_DIR/'secret.key').read_bytes()).hexdigest())
(settings.DATA_DIR/'fixture-expectations.json').write_text(json.dumps(expect),encoding='utf-8')
'''

def seed(data,password=None):
    data=Path(data).resolve();password=password or secrets.token_urlsafe(24)
    env={**os.environ,'RUMI_DATA_DIR':str(data),'DJANGO_SETTINGS_MODULE':'config.settings','RUMI_FIXTURE_LOGIN':password,'RUMI_DISABLE_BACKUP_SCHEDULER':'1'}
    for command in ([sys.executable,str(ROOT/'manage.py'),'migrate','--noinput'],[sys.executable,'-c',SEED]):
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
        if result.returncode:raise RuntimeError('Isolated fixture creation failed: '+result.stderr)
    return password
