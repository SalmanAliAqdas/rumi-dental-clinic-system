"""Reproducible 5,000-patient fictional trial; never opens the working database."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import json

ROOT = Path(__file__).resolve().parent.parent
CODE = r'''
import django, json, statistics, time, uuid
from datetime import timedelta
from decimal import Decimal
django.setup()
from django.contrib.auth.models import User
from django.test import Client
from django.db import connection
from django.utils import timezone
from clinic.models import Patient, TreatmentAccount, LedgerEntry, MedicalReview, Visit, Schedule, Installment, Allocation
from clinic import finance_services as service
owner=User.objects.create_superuser('fictional-volume-owner', password=__import__('secrets').token_urlsafe(32))
patients=Patient.objects.bulk_create([Patient(full_name=f'Fictional volume {i:05}',phone=f'+92300{i:07}',created_by=owner,updated_by=owner) for i in range(5000)])
reviews=MedicalReview.objects.bulk_create([MedicalReview(patient=p,snapshot={},reason='Fictional volume fixture',reviewed_by=owner) for p in patients])
Visit.objects.bulk_create([Visit(patient=p,clinician=owner,medical_review=r,created_by=owner,updated_by=owner,chief_complaint='Fictional volume visit') for p,r in zip(patients,reviews)])
accounts=TreatmentAccount.objects.bulk_create([TreatmentAccount(patient=p,title='Fictional account',token=uuid.uuid4(),created_by=owner) for p in patients])
old=timezone.now()-timedelta(days=1)
LedgerEntry.objects.bulk_create([LedgerEntry(account=a,kind='charge',amount=10000,balance_after=10000,token=uuid.uuid4(),actor=owner,recorded_at=old) for a in accounts])
payments=LedgerEntry.objects.bulk_create([LedgerEntry(account=a,kind='payment',amount=3000,balance_after=7000,method='cash',token=uuid.uuid4(),actor=owner) for a in accounts])
schedules=Schedule.objects.bulk_create([Schedule(account=a,reason='Fictional agreed schedule',token=uuid.uuid4(),actor=owner,created_at=old+timedelta(hours=1)) for a in accounts])
items=Installment.objects.bulk_create([Installment(schedule=s,amount=10000,due_on=service.today()-timedelta(days=1)) for s in schedules])
Allocation.objects.bulk_create([Allocation(installment=i,entry=p,amount=3000) for i,p in zip(items,payments)])
client=Client(HTTP_HOST='127.0.0.1');client.force_login(owner)
results={'volume':{'patients':5000,'visits':5000,'accounts':5000,'ledger_entries':10000,'installments':5000,'allocations':5000},'measurements':{}}
def measure(name, path, data=None, repeats=3):
    durations=[];counts=[]
    for _ in range(repeats):
        counter=[0]
        def count(execute,sql,params,many,context):
            counter[0]+=1
            return execute(sql,params,many,context)
        with connection.execute_wrapper(count):
            start=time.perf_counter()
            response=client.post(path,data) if data else client.get(path)
            assert response.status_code==200, (path,response.status_code)
            durations.append(round((time.perf_counter()-start)*1000,2));counts.append(counter[0])
    results['measurements'][name]={'median_ms':round(statistics.median(durations),2),'runs_ms':durations,'queries':counts,'response_bytes':len(response.content)}
    return response
# Reproduce the old per-account strategy on this same view/fixture.
batch=service.account_summaries
def legacy():
    result=[]
    for a in TreatmentAccount.objects.select_related('patient').iterator(chunk_size=250):
        totals=service.totals(a)
        schedule=service.active_schedule(a)
        pending=[i for i in schedule.items.all() if i.remaining>0] if schedule else []
        result.append(dict(account_id=a.pk,closed_at=a.closed_at,**{k:totals[k] for k in ('balance','charges','reductions')},schedule=schedule,had_schedule=a.schedules.exists(),next_due=min((i.due_on for i in pending if i.due_on),default=None),overdue=sum((i.remaining for i in pending if i.due_on and i.due_on<service.today()),service.ZERO)))
    return result
service.account_summaries=legacy
measure('outstanding_before','/finance/outstanding/',repeats=1)
measure('reports_before','/finance/reports/',repeats=1)
service.account_summaries=batch
measure('phone_search','/patients/',{'query':'03000000123'})
measure('dashboard','/')
r=measure('outstanding_after','/finance/outstanding/')
assert b'35000000' in r.content
r=measure('reports_after','/finance/reports/')
assert b'35000000' in r.content and b'15000000' in r.content
assert service.totals(TreatmentAccount.objects.first())['balance']==Decimal('7000')
print(json.dumps(results,indent=2))
'''


def run():
    runtime=ROOT/'runtime';runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='performance-fictional-',dir=runtime) as directory:
        env=dict(os.environ,RUMI_DATA_DIR=directory,DJANGO_SETTINGS_MODULE='config.settings')
        subprocess.run([sys.executable,'manage.py','migrate','--noinput'],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
        result=subprocess.run([sys.executable,'-c',CODE],cwd=ROOT,env=env,check=True,capture_output=True,text=True)
        payload=json.loads(result.stdout)
        (runtime/'performance-results.json').write_text(json.dumps(payload,indent=2))
        print(json.dumps(payload,indent=2))


if __name__=='__main__':run()
