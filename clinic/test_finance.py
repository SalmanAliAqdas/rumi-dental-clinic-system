from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase, Client, TransactionTestCase
from django.db import connection, close_old_connections, OperationalError
from .models import Patient, TreatmentAccount, LedgerEntry, AuditEvent, FinancialLock, Expense, CorrectionRequest, Procedure, TreatmentPlan, PlanItem
from .views import doctor_group
from . import finance_services as s
from .finance_views import collection_data, report_range, safe_cell

class FinanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=User.objects.create_superuser('financeowner',password='Fictional-test-only-7362!')
        cls.doctor=User.objects.create_user('financedoctor',password='Fictional-test-only-7362!')
        cls.doctor.groups.add(doctor_group())
        cls.patient=Patient.objects.create(full_name='Fictional Finance',phone='03001234567',created_by=cls.owner,updated_by=cls.owner)
        cls.other=Patient.objects.create(full_name='Fictional Other Finance',phone='03007654321',created_by=cls.owner,updated_by=cls.owner)
    def setUp(self):
        self.a=s.create_account(self.doctor,self.patient,'Fictional treatment',uuid4())
        self.client.force_login(self.doctor)
    def post(self,kind,amount,actor=None,account=None,**kwargs):
        return s.post(actor or self.doctor,account or self.a,kind,amount,uuid4(),description='Fictional reason',method='cash',**kwargs)
    def url(self,suffix='',patient=None,account=None):
        return f'/patients/{(patient or self.patient).pk}/payments/{(account or self.a).pk}/'+suffix
    def charge(self,amount='10000'):
        return self.post('charge',amount)
    def test_decimal_validation(self):
        for value in ['0','-1','1.001','NaN','Infinity','1.000','1000000000000','garbage']:
            with self.subTest(value=value),self.assertRaises(ValidationError): s.money(value)
        self.assertEqual(s.money('0.10')+s.money('0.20'),Decimal('.30'))
    def test_partial_multiple_full_and_no_visit(self):
        self.charge(); self.post('payment','3000'); self.assertEqual(s.totals(self.a)['balance'],7000)
        self.post('payment','2000'); self.post('payment','5000')
        self.assertEqual(s.totals(self.a)['balance'],0)
        self.assertEqual(self.a.entries.count(),4)
    def test_overpayment_and_invalid_methods(self):
        self.charge('100')
        with self.assertRaises(ValidationError): self.post('payment','100.01')
        with self.assertRaises(ValidationError): s.post(self.doctor,self.a,'payment','1',uuid4(),method='card')
        self.assertEqual(self.a.entries.count(),1)
    def test_idempotent_retry_and_account_tampering(self):
        self.charge(); token=uuid4()
        first=s.post(self.doctor,self.a,'payment','3000',token,method='cash')
        again=s.post(self.doctor,self.a,'payment','3000',token,method='cash')
        self.assertEqual(first.pk,again.pk)
        second=s.create_account(self.doctor,self.other,'Other treatment',uuid4())
        with self.assertRaises(ValidationError): s.post(self.doctor,second,'payment','3000',token,method='cash')
        self.assertEqual(s.totals(self.a)['balance'],7000)
    def test_many_accounts_preserved_closed_history(self):
        self.charge(); self.post('payment','10000')
        s.account_action(self.doctor,self.a,'close','Paid',uuid4())
        new=s.create_account(self.doctor,self.patient,'New treatment',uuid4())
        self.post('charge','500',account=new)
        response=self.client.get(f'/patients/{self.patient.pk}/payments/')
        self.assertContains(response,'Closed - fully paid')
        self.assertContains(response,'New treatment')
        self.assertContains(self.client.get(self.url()),'10000.00')
        self.assertEqual(collection_data(s.today(),s.today())['gross'],10000)
    def test_no_unpaid_or_empty_closure_and_no_duplicate_payment(self):
        with self.assertRaises(ValidationError): s.account_action(self.doctor,self.a,'close','Paid',uuid4())
        self.charge()
        with self.assertRaises(ValidationError): s.account_action(self.doctor,self.a,'close','Paid',uuid4())
        self.post('payment','10000'); token=uuid4()
        s.account_action(self.doctor,self.a,'close','Paid',token); s.account_action(self.doctor,self.a,'close','Paid',token)
        self.assertEqual(self.a.entries.filter(kind='payment').count(),1)
        with self.assertRaises(ValidationError): self.post('charge','1')
        with self.assertRaises(PermissionDenied): s.account_action(self.doctor,self.a,'reopen','Reason',uuid4())
        s.account_action(self.owner,self.a,'reopen','Returning patient',uuid4())
        self.a.refresh_from_db(); self.assertIsNone(self.a.closed_at)
    def test_linked_charge_reuse_and_cross_patient(self):
        plan=TreatmentPlan.objects.create(patient=self.patient,title='Plan',created_by=self.doctor)
        procedure=Procedure.objects.first()
        item=PlanItem.objects.create(plan=plan,procedure=procedure)
        self.post('charge','100',plan_item=item)
        with self.assertRaises(ValidationError): self.post('charge','100',plan_item=item)
        other=s.create_account(self.doctor,self.other,'Other',uuid4())
        with self.assertRaises(ValidationError): self.post('charge','100',account=other,plan_item=item)
        self.assertEqual(s.totals(self.a)['charges'],100)
    def test_installment_allocation_and_early_settlement(self):
        self.charge();self.post('payment','3000')
        schedule=s.schedule_account(self.doctor,self.a,[{'amount':'2000','due_on':s.today()-timedelta(days=1)},{'amount':'5000'}],'Agreement',uuid4())
        items=list(schedule.items.all())
        self.assertEqual(items[0].status,'Overdue'); self.assertEqual(items[1].status,'Pending')
        self.post('payment','1000'); self.assertEqual(schedule.items.first().remaining,1000)
        self.post('payment','6000')
        self.assertEqual([i.status for i in schedule.items.all()],['Paid','Paid'])
        self.assertEqual(s.totals(self.a)['payments'],10000)
    def test_schedule_sum_revisions_and_history(self):
        self.charge()
        with self.assertRaises(ValidationError): s.schedule_account(self.doctor,self.a,[{'amount':'9000'}],'Agreement',uuid4())
        old=s.schedule_account(self.doctor,self.a,[{'amount':'10000'}],'Agreement',uuid4())
        with self.assertRaises(PermissionDenied): s.schedule_account(self.doctor,self.a,[{'amount':'10000'}],'Revision',uuid4())
        self.post('payment','3000')
        new=s.schedule_account(self.owner,self.a,[{'amount':'7000'}],'Owner revised',uuid4())
        self.assertEqual(old.items.first().allocated,3000);self.assertEqual(new.items.first().remaining,7000)
        self.assertIsNone(new.items.first().due_on)
    def test_refunds_reversals_limits_and_allocations(self):
        self.charge(); schedule=s.schedule_account(self.doctor,self.a,[{'amount':'10000'}],'Agreed',uuid4())
        p=self.post('payment','3000')
        self.post('refund','1000',actor=self.owner,original=p)
        self.assertEqual(schedule.items.first().allocated,2000)
        with self.assertRaises(ValidationError): self.post('refund','2000.01',actor=self.owner,original=p)
        with self.assertRaises(ValidationError): self.post('reversal','3000',actor=self.owner,original=p)
        self.post('refund','2000',actor=self.owner,original=p)
        self.assertEqual(s.totals(self.a)['balance'],10000)
        p=self.post('payment','1000');self.post('reversal','1000',actor=self.owner,original=p)
        self.assertEqual(schedule.items.first().allocated,0)
        with self.assertRaises(ValidationError): self.post('reversal','1000',actor=self.owner,original=p)
    def test_discount_writeoff_are_not_cash(self):
        self.charge();self.post('payment','7000')
        self.post('discount','1000',actor=self.owner);self.post('writeoff','2000',actor=self.owner)
        self.assertEqual(self.a.status,'Settled with adjustment')
        self.assertEqual(collection_data(s.today(),s.today())['gross'],7000)
        with self.assertRaises(PermissionDenied): s.account_action(self.doctor,self.a,'close','Settled',uuid4())
        s.account_action(self.owner,self.a,'close','Approved settlement',uuid4())
        for kind in ('discount','writeoff','refund','reversal'):
            with self.assertRaises(PermissionDenied): self.post(kind,'1')
    def test_correction_decisions_audit_and_duplicate_approval(self):
        self.charge();p=self.post('payment','3000')
        request=s.request_correction(self.doctor,self.a,p,'Wrong amount',uuid4())
        with self.assertRaises(PermissionDenied): s.decide(self.doctor,self.a,request,True,'Approve',uuid4())
        token=uuid4();s.decide(self.owner,self.a,request,True,'Approved correction',token)
        s.decide(self.owner,self.a,request,True,'Approved correction',token)
        request.refresh_from_db();self.assertEqual(request.status,'approved')
        with self.assertRaises(ValidationError): s.decide(self.owner,self.a,request,True,'Again',uuid4())
        self.assertEqual(s.totals(self.a)['balance'],10000)
        self.assertTrue(AuditEvent.objects.filter(action='correction_decision',patient=self.patient).exists())
        request=s.request_correction(self.doctor,self.a,self.a.entries.first(),'Review charge',uuid4())
        s.decide(self.owner,self.a,request,False,'Charge correct',uuid4());request.refresh_from_db();self.assertEqual(request.status,'rejected')
    def test_immutable_posted_records(self):
        e=self.charge()
        for fn in [lambda:e.save(), lambda:e.delete(), lambda:LedgerEntry.objects.filter(pk=e.pk).update(amount=1),lambda:LedgerEntry.objects.all().delete()]:
            with self.assertRaises(ValidationError):fn()
    def test_cross_patient_urls_and_form_identifiers(self):
        self.charge();p=self.post('payment','100')
        self.assertEqual(self.client.get(self.url(patient=self.other)).status_code,404)
        self.assertEqual(self.client.get(self.url(f'receipt/{p.pk}/',patient=self.other)).status_code,404)
        other=s.create_account(self.doctor,self.other,'Other',uuid4())
        self.post('charge','100',account=other)
        foreign=self.post('payment','1',account=other)
        self.assertEqual(self.client.get(self.url(f'receipt/{foreign.pk}/')).status_code,404)
        r=self.client.post(self.url('corrections/'),dict(token=uuid4(),reason='Bad original',original=foreign.pk))
        self.assertEqual(r.status_code,400)
    def test_doctor_global_permissions_all_parameters(self):
        for path in ['/finance/reports/','/finance/export/','/finance/expenses/new/','/finance/reports/?period=annual','/finance/today/?date=2020-01-01','/finance/today/?page=2','/finance/outstanding/?start=2020-01-01']:
            self.assertEqual(self.client.get(path).status_code,403,path)
        self.charge()
        r=self.client.get('/finance/outstanding/')
        self.assertNotIn('combined_balance',r.context)
        self.assertNotContains(r,'Combined balance')
        for path in ['/finance/today/','/finance/outstanding/?filter=settled',self.url()]:self.assertEqual(self.client.get(path).status_code,200)
    def test_doctor_date_is_forced_today_even_raw_post(self):
        self.charge()
        r=self.client.post(self.url('entry/'),dict(token=uuid4(),kind='payment',amount='100',method='cash',received_at='2001-01-01T00:00'))
        self.assertEqual(r.status_code,302)
        self.assertEqual(self.a.entries.get(kind='payment').received_at.astimezone(s.PK).date(),s.today())
    def test_pakistan_midnight_boundaries(self):
        self.charge()
        with patch('clinic.finance_services.timezone.now',return_value=datetime(2026,11,6,20,tzinfo=dt_timezone.utc)):
            self.post('payment','100',actor=self.owner,received_at=datetime(2026,11,5,18,59,59,tzinfo=dt_timezone.utc))
            self.post('payment','200',actor=self.owner,received_at=datetime(2026,11,5,19,0,tzinfo=dt_timezone.utc))
            self.post('payment','300',actor=self.owner,received_at=datetime(2026,11,6,18,59,59,tzinfo=dt_timezone.utc))
            self.post('payment','400',actor=self.owner,received_at=datetime(2026,11,6,19,0,tzinfo=dt_timezone.utc))
            self.assertEqual(collection_data(date(2026,11,6),date(2026,11,6))['gross'],500)
            self.assertEqual(s.today(),date(2026,11,7))
    def test_owner_reports_expenses_and_reconciliation(self):
        self.charge();p=self.post('payment','3000');self.post('refund','500',actor=self.owner,original=p)
        data=dict(spent_on=s.today(),category='Supplies',description='Fictional expense',amount='200',method='bank',reference='Ref')
        with self.assertRaises(PermissionDenied):s.expense(self.doctor,data,uuid4())
        expense=s.expense(self.owner,data,uuid4());self.client.force_login(self.owner)
        r=self.client.get('/finance/reports/')
        self.assertEqual(r.context['cash_movement'],2300);self.assertEqual(r.context['outstanding_total'],7500)
        s.expense(self.owner,{'description':'Incorrect expense'},uuid4(),expense)
        with self.assertRaises(ValidationError):s.expense(self.owner,{'description':'Again'},uuid4(),expense)
        r=self.client.get('/finance/reports/');self.assertEqual(r.context['expense_total'],0);self.assertEqual(r.context['cash_movement'],2500)
    def test_owner_ranges_and_export_safety(self):
        self.charge();s.post(self.doctor,self.a,'payment','100',uuid4(),method='cash',description='=HYPERLINK("bad")')
        for period in ['daily','weekly','monthly','annual','custom']:
            self.client.force_login(self.owner)
            r=self.client.get('/finance/reports/',dict(period=period,start='2026-01-01',end='2026-12-31'))
            self.assertEqual(r.status_code,200,period)
        r=self.client.get('/finance/export/');self.assertContains(r,"'=HYPERLINK")
        self.assertNotContains(r,'medical_history')
        for text in ['=1',' +1','-1','@cmd','\t=1'] : self.assertTrue(safe_cell(text).startswith("'"))
        self.assertEqual(self.client.get('/finance/reports/?period=custom&start=bad').status_code,400)
    def test_receipt_privacy_escaping_csrf_and_no_get_mutation(self):
        self.charge();p=self.post('payment','100')
        r=self.client.get(self.url(f'receipt/{p.pk}/'))
        self.assertContains(r,self.patient.number);self.assertNotContains(r,self.other.full_name)
        self.assertIn('no-store',r.headers['Cache-Control'])
        self.client.force_login(self.owner)
        s.post(self.owner,self.a,'charge','1',uuid4(),description='<script>alert(1)</script>')
        self.assertContains(self.client.get(self.url()),'&lt;script&gt;')
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.doctor)
        self.assertEqual(secure.post(self.url('entry/'),dict(kind='payment',amount=1,method='cash',token=uuid4())).status_code,403)
        count=self.a.entries.count(); self.client.get(self.url('entry/'));self.assertEqual(self.a.entries.count(),count)
    def test_outstanding_filters_and_settled(self):
        self.charge();s.schedule_account(self.doctor,self.a,[{'amount':'10000','due_on':s.today()-timedelta(days=1)}],'Agreed',uuid4())
        for choice in ['outstanding','due','overdue']:self.assertContains(self.client.get('/finance/outstanding/',{'filter':choice}),'Fictional treatment')
        self.post('payment','10000');s.account_action(self.doctor,self.a,'close','Paid',uuid4())
        self.assertNotContains(self.client.get('/finance/outstanding/'),'Fictional treatment')
        self.assertContains(self.client.get('/finance/outstanding/?filter=settled'),'Fictional treatment')

    def test_all_finance_pages_require_auth_and_owner_mutations_are_denied(self):
        self.charge();p=self.post('payment','10')
        self.client.logout()
        for path in ['/finance/outstanding/','/finance/today/','/finance/reports/','/finance/export/',self.url(),self.url('entry/'),self.url('installments/'),self.url(f'receipt/{p.pk}/')]:
            self.assertEqual(self.client.get(path).status_code,302,path)
        self.client.force_login(self.doctor)
        for path in ['/finance/expenses/new/','/finance/expenses/1/reverse/',self.url('action/reopen/')]:
            self.assertEqual(self.client.post(path,{'reason':'Forged','token':uuid4()}).status_code,403,path)
        self.assertEqual(self.client.post(self.url('entry/'),dict(kind='refund',amount='10',method='cash',original=p.pk,token=uuid4(),description='Forged')).status_code,400)

    def test_duplicate_account_schedule_requests_and_expenses(self):
        token=uuid4();first=s.create_account(self.doctor,self.patient,'New account',token)
        self.assertEqual(first.pk,s.create_account(self.doctor,self.patient,'New account',token).pk)
        self.charge();token=uuid4();args=(self.doctor,self.a,[{'amount':'10000'}],'Agreed',token)
        self.assertEqual(s.schedule_account(*args).pk,s.schedule_account(*args).pk)
        p=self.post('payment','1');token=uuid4();args=(self.doctor,self.a,p,'Correction',token)
        self.assertEqual(s.request_correction(*args).pk,s.request_correction(*args).pk)
        token=uuid4();data=dict(spent_on=s.today(),category='Fictional',description='Fictional expense',amount='10',method='easypaisa',reference='')
        self.assertEqual(s.expense(self.owner,data,token).pk,s.expense(self.owner,data,token).pk)

    def test_adjustment_invalidates_schedule_until_owner_revision(self):
        self.charge();old=s.schedule_account(self.doctor,self.a,[{'amount':'10000'}],'Original schedule',uuid4())
        self.post('discount','1000',actor=self.owner)
        self.assertIsNone(s.active_schedule(self.a))
        self.assertEqual(old.items.first().amount,10000)
        new=s.schedule_account(self.owner,self.a,[{'amount':'9000'}],'Owner approved revised balance',uuid4())
        self.assertEqual(s.active_schedule(self.a).pk,new.pk)
        self.post('payment','9000')
        self.assertEqual(new.items.first().status,'Paid')

    def test_refund_of_pre_schedule_payment_requires_revision_when_needed(self):
        self.charge();p=self.post('payment','3000')
        s.schedule_account(self.doctor,self.a,[{'amount':'7000'}],'Remaining amount',uuid4())
        self.post('refund','1000',actor=self.owner,original=p)
        self.assertIsNone(s.active_schedule(self.a))
        self.assertEqual(s.totals(self.a)['balance'],8000)

    def test_owner_form_and_report_invalid_date_boundaries(self):
        self.client.force_login(self.owner)
        for path in ['/finance/reports/?period=annual&date=9999-01-01','/finance/reports/?period=bad','/finance/reports/?period=custom&start=2026-12-01&end=2026-01-01']:
            self.assertEqual(self.client.get(path).status_code,400,path)
        r=self.client.post('/finance/expenses/new/',dict(token=uuid4(),spent_on=s.today().isoformat(),category='Fictional',description='Fictional supplies',amount='10.50',method='bank'))
        self.assertEqual(r.status_code,302)
        self.assertEqual(Expense.objects.get().amount,Decimal('10.50'))


class FinanceConcurrencyTests(TransactionTestCase):
    def test_sqlite_first_write_and_concurrent_retry(self):
        import os, subprocess, sys, tempfile
        from pathlib import Path
        from django.conf import settings
        from django.test.utils import CaptureQueriesContext
        FinancialLock.objects.get_or_create(pk=1)
        actor=User.objects.create_superuser('raceowner',password='Fictional-test-only-7362!')
        patient=Patient.objects.create(full_name='Fictional Race',phone='03001234567',created_by=actor,updated_by=actor)
        account=s.create_account(actor,patient,'Race treatment',uuid4())
        s.post(actor,account,'charge','100',uuid4(),description='Fictional charge')
        with CaptureQueriesContext(connection) as captured:
            with s.serialized(): pass
        statements=[q['sql'] for q in captured if q['sql'] not in ('BEGIN','COMMIT')]
        self.assertTrue(statements[0].startswith('UPDATE "clinic_financiallock"'))
        import sqlite3
        from contextlib import closing
        with tempfile.TemporaryDirectory() as directory:
            with closing(sqlite3.connect(Path(directory)/'clinic.sqlite3')) as target:
                connection.connection.backup(target)
            (Path(directory)/'secret.key').write_text('fictional-isolated-race-secret-not-used-elsewhere')
            env={**os.environ,'RUMI_DATA_DIR':directory,'DJANGO_SETTINGS_MODULE':'config.settings','PYTHONUTF8':'1'}
            script = """import django,sys,time
from uuid import UUID
django.setup()
from clinic import finance_services as s
from clinic.models import TreatmentAccount
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
actor=get_user_model().objects.get(username='raceowner')
a=TreatmentAccount.objects.get(title='Race treatment')
try:
    e=s.post(actor,a,'payment',sys.argv[1],UUID(sys.argv[2]),method='cash')
    print('posted',e.pk)
except ValidationError:
    print('rejected')
"""
            def race(amount,tokens):
                processes=[subprocess.Popen([sys.executable,'-c',script,amount,str(t)],cwd=settings.BASE_DIR,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for t in tokens]
                results=[]
                for process in processes:
                    out,err=process.communicate(timeout=40)
                    self.assertEqual(process.returncode,0,err)
                    results.append(out.strip())
                return results
            results=race('80',[uuid4(),uuid4()])
            self.assertEqual(sum(r.startswith('posted') for r in results),1,results)
            self.assertEqual(results.count('rejected'),1,results)
            token=uuid4();results=race('20',[token,token])
            self.assertEqual(results[0],results[1],results)
            with closing(sqlite3.connect(Path(directory)/'clinic.sqlite3')) as target:
                self.assertEqual(target.execute("SELECT COUNT(*) FROM clinic_ledgerentry WHERE kind='payment'").fetchone()[0],2)
