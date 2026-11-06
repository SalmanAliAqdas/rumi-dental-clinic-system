"""Regressions for streaming shutdown, read batching and local setup status."""
from decimal import Decimal
import secrets
from uuid import uuid4
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from clinic.local_server import RequestGate
from clinic.trial_identity import identity_proof
from clinic import finance_services as f
from clinic.models import Patient, TreatmentAccount


class ShutdownTests(SimpleTestCase):
    def test_shutdown_tracks_a_worker_before_it_has_a_job_lease(self):
        import tempfile
        import threading
        from pathlib import Path
        from unittest.mock import patch
        from clinic.backups import jobs
        entered=threading.Event();release=threading.Event();drained=threading.Event()
        def pending(*args):
            entered.set();release.wait(5)
        with tempfile.TemporaryDirectory() as temp, patch.object(jobs,'run_job',side_effect=pending):
            data=Path(temp)
            jobs.request_job(data,None,'backup',secrets.token_urlsafe(32),uuid4())
            self.assertTrue(entered.wait(2))
            waiter=threading.Thread(target=lambda:(jobs.wait_for_jobs(data),drained.set()))
            waiter.start()
            self.assertFalse(drained.wait(.05))
            release.set();waiter.join(timeout=2)
            self.assertTrue(drained.is_set())

    def test_streaming_response_stays_active_until_closed_and_new_work_refused(self):
        closed = []
        def application(environ, start):
            start('200 OK', [])
            try:
                yield b'first'
                yield b'last'
            finally:
                closed.append(True)
        gate = RequestGate(application)
        status=[]
        response=gate({}, lambda value, headers: status.append(value))
        self.assertEqual(next(response),b'first')
        self.assertEqual(gate.active,1)
        gate.closing=True
        refused=gate({}, lambda value, headers: status.append(value))
        self.assertIn(b'stopping safely',b''.join(refused))
        self.assertEqual(status[-1],'503 Service Unavailable')
        response.close()
        self.assertEqual(gate.active,0)
        self.assertEqual(closed,[True])

    def test_failed_application_releases_active_count(self):
        def application(environ,start):
            raise RuntimeError('fictional failure')
        gate=RequestGate(application)
        with self.assertRaises(RuntimeError):
            list(gate({},lambda *_:None))
        self.assertEqual(gate.active,0)

    def test_pythonw_and_python_same_environment_identity(self):
        args=('private test secret','a'*64,'/project','/data/clinic.sqlite3')
        self.assertEqual(identity_proof(*args,'/env/Scripts/python.exe'),identity_proof(*args,'/env/Scripts/pythonw.exe'))
        self.assertNotEqual(identity_proof(*args,'/other/Scripts/pythonw.exe'),identity_proof(*args,'/env/Scripts/python.exe'))


class ReadBatchTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_superuser('fictional-batch-owner',password=secrets.token_urlsafe(32))
        self.patient=Patient.objects.create(full_name='Fictional batch',phone='03001234567',created_by=self.owner,updated_by=self.owner)
        self.accounts=[]
        for i in range(3):
            account=f.create_account(self.owner,self.patient,'Fictional account',uuid4())
            f.post(self.owner,account,'charge','10000',uuid4(),description='Fictional agreed total')
            f.schedule_account(self.owner,account,[{'amount':'10000'}],'Fictional agreement',uuid4())
            payment=f.post(self.owner,account,'payment','3000',uuid4(),method='cash')
            if i==1:
                f.post(self.owner,account,'refund','1000',uuid4(),original=payment,description='Fictional refund',method='cash')
            if i==2:
                f.post(self.owner,account,'discount','1000',uuid4(),description='Fictional approved adjustment')
            self.accounts.append(account)

    def test_batched_finances_match_original_and_avoid_per_account_queries(self):
        expected={a.pk:(f.totals(a),bool(f.active_schedule(a))) for a in self.accounts}
        self.assertEqual(expected[self.accounts[0].pk][0]['balance'],Decimal('7000'))
        with self.assertNumQueries(6):
            summaries=f.account_summaries()
        for summary in summaries:
            total,active=expected[summary['account_id']]
            self.assertEqual(summary['balance'],total['balance'])
            self.assertEqual(summary['charges'],total['charges'])
            self.assertEqual(summary['reductions'],total['reductions'])
            self.assertEqual(bool(summary['schedule']),active)

    def test_cent_reversals_and_latest_overdue_schedule_match_authoritative_history(self):
        from datetime import timedelta
        account=self.accounts[0]
        payment=account.entries.get(kind='payment')
        f.post(self.owner,account,'reversal','3000',uuid4(),original=payment,description='Fictional payment reversal')
        charge=f.post(self.owner,account,'charge','0.31',uuid4(),description='Fictional extra charge')
        discount=f.post(self.owner,account,'discount','0.11',uuid4(),description='Fictional reduction')
        writeoff=f.post(self.owner,account,'writeoff','0.10',uuid4(),description='Fictional writeoff')
        for entry in (discount,writeoff,charge):
            f.post(self.owner,account,'reversal',entry.amount,uuid4(),original=entry,description='Fictional explicit correction')
        f.schedule_account(self.owner,account,[{'amount':'10000','due_on':f.today()-timedelta(days=1)}],'Fictional revised schedule',uuid4())
        f.post(self.owner,account,'payment','0.01',uuid4(),method='cash')
        summary=next(r for r in f.account_summaries() if r['account_id']==account.pk)
        self.assertEqual(summary['balance'],Decimal('9999.99'))
        self.assertEqual(summary['balance'],f.totals(account)['balance'])
        self.assertEqual(summary['charges'],f.totals(account)['charges'])
        self.assertEqual(summary['reductions'],f.totals(account)['reductions'])
        self.assertEqual(summary['overdue'],sum((i.remaining for i in f.active_schedule(account).items.all()),f.ZERO))

    def test_owner_status_is_honest_and_doctor_denied(self):
        self.client.force_login(self.owner)
        response=self.client.get('/backups/')
        self.assertContains(response,'No completed operational drill recorded')
        self.assertContains(response,'Missing — configure and verify')
        self.assertNotContains(response,'protected')
        self.owner.is_superuser=False
        self.owner.save()
        self.assertEqual(self.client.get('/backups/').status_code,403)
