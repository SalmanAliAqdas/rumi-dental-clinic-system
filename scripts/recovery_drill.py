"""Executable isolated recovery drill. Does not copy/restore the working clinic."""
from pathlib import Path
import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from backup_fixture import seed
from clinic.backups.archive import create_package,verified_package,read_json

CHECK=r'''
import os,django,hashlib,json
django.setup()
from django.conf import settings
from django.test import Client
from clinic.models import Patient,Visit,Attachment,Appointment,Prescription,PersonalTask,TreatmentAccount
from clinic.finance_services import totals
expected=json.loads(os.environ['RUMI_FIXTURE_EXPECTATIONS'])
client=Client(HTTP_HOST='127.0.0.1');assert client.login(username='recoveryowner',password=os.environ['RUMI_FIXTURE_LOGIN'])
r=client.post('/patients/',{'query':'+923001234567'});assert r.status_code==200
assert Patient.objects.filter(phone='+923001234567').count()==2
p=Patient.objects.get(pk=expected['patient_id']);assert p.number==expected['patient_number'] and 'عائشہ' in p.full_name
v=Visit.objects.get(pk=expected['visit_id'],patient=p);assert v.chief_complaint=='Fictional clinical history'
a=TreatmentAccount.objects.get(pk=expected['account_id'],patient=p);assert totals(a)['balance']==5000 and a.entries.filter(kind='payment').count()==2
assert a.schedules.first().items.first().allocated==2000
assert Appointment.objects.get(pk=expected['appointment_id']).visit_id==v.pk
rx=Prescription.objects.get(pk=expected['rx_id'],patient=p);assert rx.state=='Issued' and rx.snapshot['clinician']['name']=='Fictional Recovery Clinician'
assert PersonalTask.objects.get(pk=expected['task_id']).creator.username=='recoverydoctor'
image=Attachment.objects.get(pk=expected['attachment_id'],patient=p)
assert hashlib.sha256((settings.DATA_DIR/'attachments'/image.storage_name).read_bytes()).hexdigest()==expected['image_sha256']
assert hashlib.sha256((settings.DATA_DIR/'secret.key').read_bytes()).hexdigest()==expected['secret_sha256']
assert client.get(f'/patients/{p.pk}/attachments/{image.pk}/thumbnail/').status_code==200
assert client.get(f'/patients/{p.pk}/prescriptions/{rx.pk}/print/').status_code==200
assert client.login(username='recoverydoctor',password=os.environ['RUMI_FIXTURE_LOGIN'])
assert client.get('/backups/').status_code==403 and client.get('/finance/reports/').status_code==403
print('PASS: restored original Owner/Doctor logins, Unicode/shared-phone search, clinical/X-ray, PKR 5000 balance/installments, appointment visit link, issued prescription, task ownership, secret and image checksum, permissions')
'''

def run():
    runtime=ROOT/'runtime';runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='recovery-drill-',dir=runtime) as temp:
        base=Path(temp);source=base/'fictional-source';target=base/'clean-recovery';password=seed(source)
        expected=read_json(source/'fixture-expectations.json');recovery=secrets.token_urlsafe(32)
        package=base/'fictional.rumibak'
        create_package(source,package,recovery,work_parent=base)
        with verified_package(package,recovery,base,'backup') as (_,manifest):
            assert manifest['row_counts']['clinic_patient']==2
            print('PASS: encrypted complete package decrypted, manifest/checksums/schema/database/attachments verified')
        cli=subprocess.run([sys.executable,str(ROOT/'scripts/recovery.py'),'restore','--package',str(package),'--data-dir',str(target)],cwd=ROOT,input=recovery+'\nRESTORE\n',capture_output=True,text=True,timeout=120)
        if cli.returncode:raise RuntimeError('Isolated recovery helper failed: '+cli.stdout+cli.stderr)
        assert recovery not in cli.stdout and recovery not in cli.stderr
        print('PASS: standalone recovery CLI restored a clean directory with generated prompt input; recovery password was not a command argument or log value')
        with closing(sqlite3.connect(target/'clinic.sqlite3')) as db:assert db.execute('SELECT COUNT(*) FROM django_session').fetchone()[0]==0
        env={**os.environ,'RUMI_DATA_DIR':str(target),'DJANGO_SETTINGS_MODULE':'config.settings','RUMI_FIXTURE_LOGIN':password,'RUMI_FIXTURE_EXPECTATIONS':json.dumps(expected)}
        subprocess.run([sys.executable,'-c',CHECK],cwd=ROOT,env=env,check=True,timeout=60)
        print('PASS: real isolated fresh-directory recovery drill; working clinic never restored over, no default/replacement accounts')

if __name__=='__main__':run()
