from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase,TestCase,Client,override_settings
from .views import doctor_group
from .backups import archive as a,jobs,recovery,dpapi
from .backups.crypto import encrypt,decrypt,BackupError
from .backups.locks import lease,lock_path,runtime_access,Busy

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from backup_fixture import seed

class BackupCoreTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root_temp=tempfile.TemporaryDirectory(prefix='rumi-backup-unit-')
        cls.root=Path(cls.root_temp.name).resolve();cls.source=cls.root/'fictional-source'
        cls.login_password=seed(cls.source);cls.recovery_password='Fictional-test-recovery-9837!'
        cls.package=cls.root/'complete.rumibak'
        cls.manifest=a.create_package(cls.source,cls.package,cls.recovery_password,work_parent=cls.root)
    @classmethod
    def tearDownClass(cls):
        cls.root_temp.cleanup();super().tearDownClass()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=self.root);self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name).resolve()
    def source_copy(self):
        target=self.work/'source';shutil.copytree(self.source,target);return target
    def tamper(self,change,compression=zipfile.ZIP_STORED,symlink=False):
        plain=self.work/('plain-'+uuid.uuid4().hex+'.zip');decrypt(self.package,plain,self.recovery_password)
        with zipfile.ZipFile(plain) as z:contents={n:z.read(n) for n in z.namelist()}
        change(contents)
        modified=self.work/('modified-'+uuid.uuid4().hex+'.zip')
        with zipfile.ZipFile(modified,'w',compression=compression) as z:
            for name,body in contents.items():
                if symlink and name=='secret.key':
                    info=zipfile.ZipInfo(name);info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,body)
                else:z.writestr(name,body)
        package=self.work/('modified-'+uuid.uuid4().hex+'.rumibak');encrypt(modified,package,self.recovery_password);return package
    def assert_invalid(self,package,password=None):
        with self.assertRaises(BackupError):
            with a.verified_package(package,password or self.recovery_password,self.work):pass
    def test_complete_snapshot_inventory_unicode_and_credentials(self):
        with a.verified_package(self.package,self.recovery_password,self.work,'backup') as (stage,m):
            self.assertEqual(m['row_counts']['clinic_patient'],2)
            self.assertEqual(a.digest(stage/'secret.key'),a.digest(self.source/'secret.key'))
            self.assertTrue(any(n.startswith('attachments/originals/') for n in m['files']))
            self.assertTrue(any(n.startswith('attachments/thumbnails/') for n in m['files']))
            self.assertFalse(any('backup-control' in n or 'fixture-' in n or 'log' in n for n in m['files']))
            with closing(sqlite3.connect(stage/'clinic.sqlite3')) as db:
                self.assertIn('عائشہ',db.execute('SELECT full_name FROM clinic_patient WHERE id=1').fetchone()[0])
                self.assertEqual(db.execute('SELECT COUNT(DISTINCT phone) FROM clinic_patient').fetchone()[0],1)
                self.assertTrue(db.execute('SELECT password FROM auth_user LIMIT 1').fetchone()[0].startswith('pbkdf2_'))
    def test_wrong_password_corruption_truncation_and_no_plaintext_left(self):
        self.assert_invalid(self.package,'Fictional-wrong-password')
        for suffix,data in [('truncated',self.package.read_bytes()[:30]),('corrupt',self.package.read_bytes()[:-1]+bytes([self.package.read_bytes()[-1]^1]))]:
            p=self.work/(suffix+'.rumibak');p.write_bytes(data);self.assert_invalid(p)
        self.assertFalse(list(self.work.glob('rumi-verify-*')))
    def test_missing_attachment_and_mismatched_inventory_rejected(self):
        package=self.tamper(lambda files:files.pop(next(n for n in files if n.startswith('attachments/originals/'))))
        self.assert_invalid(package)
        def remove_consistently(files):
            name=next(n for n in files if n.startswith('attachments/originals/'));files.pop(name)
            manifest=json.loads(files['manifest.json']);manifest['files'].pop(name);files['manifest.json']=json.dumps(manifest).encode()
        self.assert_invalid(self.tamper(remove_consistently))
        source=self.source_copy();next((source/'attachments/originals').iterdir()).unlink()
        with self.assertRaises(BackupError):a.create_package(source,self.work/'incomplete.rumibak',self.recovery_password,work_parent=self.work)
        self.assertFalse((self.work/'incomplete.rumibak').exists())
    def test_unsafe_archive_path_and_symlink_rejected(self):
        package=self.tamper(lambda files:files.update({'../escape.txt':b'bad'}));self.assert_invalid(package)
        self.assertFalse((self.work/'escape.txt').exists())
    def test_archive_symlink_rejected(self):self.assert_invalid(self.tamper(lambda files:None,symlink=True))
    def test_compression_and_resource_limits_rejected(self):
        self.assert_invalid(self.tamper(lambda files:None,compression=zipfile.ZIP_DEFLATED))
        with patch.object(a,'MAX_FILES',2):self.assert_invalid(self.package)
        with patch.object(a,'MAX_FILE',10):self.assert_invalid(self.package)
    def test_future_format_and_schema_rejected(self):
        def future(files):
            m=json.loads(files['manifest.json']);m['format_version']=999;files['manifest.json']=json.dumps(m).encode()
        self.assert_invalid(self.tamper(future))
        source=self.source_copy()
        with closing(sqlite3.connect(source/'clinic.sqlite3')) as db:
            db.execute("INSERT INTO django_migrations(app,name,applied) VALUES('clinic','9999_future','2026-01-01')");db.commit()
        with self.assertRaises(BackupError):a.create_package(source,self.work/'future.rumibak',self.recovery_password,work_parent=self.work)
    def test_snapshot_exclusive_boundary_blocks_writes_and_attachments(self):
        source=self.source_copy();results=[]
        with runtime_access(source,exclusive=True):
            def contender():
                try:
                    with runtime_access(source):results.append('unsafe')
                except Busy:results.append('blocked')
            t=threading.Thread(target=contender);t.start();t.join(timeout=5)
            self.assertEqual(results,['blocked'])
        with runtime_access(source):pass
    def test_fresh_restore_preserves_original_passwords_relationships_and_clears_sessions(self):
        target=self.work/'clean'
        result=recovery.restore(self.package,self.recovery_password,target,confirmed=True)
        self.assertTrue(result['sessions_cleared']);self.assertIsNone(result['rollback'])
        recovery.authenticate_owner(target,'recoveryowner',self.login_password)
        with closing(sqlite3.connect(target/'clinic.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM django_session').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT visit_id FROM clinic_appointment').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM clinic_prescription WHERE issued_at IS NOT NULL').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM clinic_personaltask').fetchone()[0],1)
        self.assertEqual(a.digest(target/'secret.key'),a.digest(self.source/'secret.key'))
        for p in (self.source/'attachments').rglob('*'):
            if p.is_file():self.assertEqual(a.digest(p),a.digest(target/p.relative_to(self.source)))
        self.assertFalse((target/'backup-control').exists())
    def test_existing_restore_requires_confirmation_and_current_owner(self):
        target=self.source_copy()
        before=a.digest(target/'clinic.sqlite3')
        with self.assertRaises(BackupError):recovery.restore(self.package,self.recovery_password,target)
        with self.assertRaises(BackupError):recovery.restore(self.package,self.recovery_password,target,confirmed=True,username='recoverydoctor',owner_password=self.login_password)
        with self.assertRaises(BackupError):recovery.restore(self.package,self.recovery_password,target,confirmed=True,username='recoveryowner',owner_password='bad')
        self.assertEqual(a.digest(target/'clinic.sqlite3'),before)
    def test_activation_failure_rolls_back_verified_original(self):
        target=self.source_copy();before=a.digest(target/'clinic.sqlite3');secret=a.digest(target/'secret.key')
        with patch.object(recovery,'activation_probe',side_effect=BackupError('Fictional activation failure')):
            with self.assertRaises(BackupError):recovery.restore(self.package,self.recovery_password,target,confirmed=True,username='recoveryowner',owner_password=self.login_password)
        self.assertEqual(a.digest(target/'clinic.sqlite3'),before);self.assertEqual(a.digest(target/'secret.key'),secret)
        self.assertFalse(recovery.journal_path(target).exists())
    def test_live_server_lease_prevents_restore_from_another_process(self):
        target=self.source_copy()
        script="from pathlib import Path;from clinic.backups.locks import lease,lock_path,Busy;import sys\ntry:\n with lease(lock_path(Path(sys.argv[1]),'server')):print('unsafe')\nexcept Busy:print('blocked')"
        with lease(lock_path(target,'server')):
            r=subprocess.run([sys.executable,'-c',script,str(target)],cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'blocked')
    def test_journal_repair_and_unsafe_journal_paths(self):
        target=self.source_copy();rollback=target.parent/('.'+target.name+'.rumi-rollback-'+uuid.uuid4().hex);stage=target.parent/('.'+target.name+'.rumi-stage-'+uuid.uuid4().hex)
        before=a.digest(target/'clinic.sqlite3');os.replace(target,rollback)
        a.atomic_json(recovery.journal_path(target),dict(target=str(target),stage=str(stage),rollback=str(rollback),state='old_moved'))
        recovery.repair(target,'recoveryowner',self.login_password)
        self.assertEqual(a.digest(target/'clinic.sqlite3'),before)
        a.atomic_json(recovery.journal_path(target),dict(target=str(target),stage='C:/unrelated',rollback=None,state='prepared'))
        with self.assertRaises(BackupError):recovery.repair(target,'recoveryowner',self.login_password)
    def test_export_all_business_modules_ids_unicode_and_excluded_secrets(self):
        package=self.work/'portable.rumiexport';a.create_package(self.source,package,self.recovery_password,kind='export',work_parent=self.work)
        with a.verified_package(package,self.recovery_password,self.work,'export') as (stage,m):
            records=a.read_json(stage/'records.json');tables=records['tables']
            for table in ['clinic_patient','clinic_visit','clinic_ledgerentry','clinic_schedule','clinic_appointment','clinic_prescription','clinic_personaltask','clinic_auditevent']:self.assertIn(table,tables)
            self.assertNotIn('django_session',tables);self.assertNotIn('clinic_loginattempt',tables)
            self.assertNotIn('password',tables['auth_user'][0]);self.assertNotIn('secret.key',m['files']);self.assertNotIn('clinic.sqlite3',m['files'])
            self.assertEqual(tables['clinic_appointment'][0]['visit_id'],tables['clinic_visit'][0]['id'])
            self.assertEqual(tables['clinic_ledgerentry'][0]['amount'],'10000.00')
            self.assertIn('عائشہ',tables['clinic_patient'][0]['full_name'])
            self.assertTrue(a.read_json(stage/'attachment-map.json')[0]['original_sha256'])
            self.assertIn("'=Fictional formula cell",(stage/'csv/clinic_expense.csv').read_text())
        with self.assertRaises(BackupError):recovery.restore(package,self.recovery_password,self.work/'not-a-backup',confirmed=True)
    def config(self,source,kind='local',missing=False):
        folder=self.work/('missing' if missing else 'destination')
        if not missing:folder.mkdir(exist_ok=True)
        d=dict(id=str(uuid.uuid4()),label='Fictional destination',kind=kind,folder=str(folder),enabled=True,staging_folder=str(self.work/'unsynced'))
        if kind=='gdrive':(self.work/'unsynced').mkdir(exist_ok=True)
        c=jobs.save_config(source,1,{'destinations':[d],'keep_last':2},0)
        return c,d
    def test_per_destination_failure_no_fallback_and_no_false_google_success(self):
        source=self.source_copy();config,d=self.config(source,'gdrive')
        missing={**d,'id':str(uuid.uuid4()),'label':'Disconnected external','kind':'external','folder':str(self.work/'missing')}
        jobs.save_config(source,1,{'destinations':[d,missing]},config['revision'])
        job=jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),background=False)
        self.assertEqual(job['status'],'partial')
        self.assertEqual([r['status'] for r in job['results']],['verified','failed'])
        self.assertEqual(job['results'][0]['message'],'Saved to Google Drive folder')
        self.assertFalse(list(Path(d['folder']).glob('*.part')));self.assertFalse((self.work/'missing').exists())
    def test_full_disk_and_disconnection_never_finalize(self):
        source=self.source_copy();config,d=self.config(source)
        with patch.object(jobs,'require_space',side_effect=BackupError('Insufficient free disk space')):
            job=jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),background=False)
        self.assertEqual(job['status'],'failed');self.assertFalse(list(Path(d['folder']).glob('*.rumibak')))
        self.assertFalse(list(Path(d['folder']).glob('*.part')))
    def test_daily_duplicate_and_retention_boundaries(self):
        source=self.source_copy();config,d=self.config(source);folder=Path(d['folder']);unrelated=folder/'unrelated.txt';unrelated.write_text('Keep me')
        first=jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),daily_slot='2026-11-01',background=False)
        self.assertEqual(first['status'],'completed')
        retry=jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),daily_slot='2026-11-01',background=False)
        self.assertEqual(retry['results'],[]);self.assertEqual(len(list(folder.glob('*.rumibak'))),1)
        jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),daily_slot='2026-11-02',background=False)
        jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),daily_slot='2026-11-03',background=False)
        self.assertEqual(len(list(folder.glob('*.rumibak'))),2);self.assertEqual(unrelated.read_text(),'Keep me')
    def test_failed_new_backup_does_not_prune_good_copies(self):
        source=self.source_copy();config,d=self.config(source)
        first=jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),background=False)
        path=Path(first['results'][0]['folder'])/first['results'][0]['filename']
        with patch.object(jobs,'publish',side_effect=OSError('Fictional disconnect')):
            job=jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),background=False)
        self.assertEqual(job['status'],'failed');self.assertTrue(path.exists())
    def test_automatic_due_startup_and_credential_failure(self):
        source=self.source_copy();config,d=self.config(source)
        config=jobs.save_config(source,1,{'automatic':True,'daily_time':'18:00'},config['revision'])
        self.assertEqual(jobs.due_slot(config,datetime(2026,11,6,12,tzinfo=timezone.utc)),'2026-11-05')
        self.assertEqual(jobs.due_slot(config,datetime(2026,11,6,13,tzinfo=timezone.utc)),'2026-11-06')
        jobs.scheduler_tick(source);self.assertTrue((jobs.control(source)/'scheduler-warning.json').exists())
        (jobs.control(source)/'automatic.dpapi').write_bytes(b'protected-only-fixture')
        with patch.object(jobs,'read_password',return_value=self.recovery_password),patch.object(jobs,'request_job') as submit:
            jobs.scheduler_tick(source);self.assertEqual(submit.call_count,1)
    def test_running_job_prevents_overlapping_backup(self):
        source=self.source_copy();config,d=self.config(source)
        ready=threading.Event();release=threading.Event()
        def holder():
            with lease(lock_path(source,'job')):ready.set();release.wait(10)
        thread=threading.Thread(target=holder);thread.start();ready.wait(5)
        try:
            job=jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),background=False)
            self.assertEqual(job['status'],'failed');self.assertFalse(list(Path(d['folder']).glob('*.rumibak')))
        finally:release.set();thread.join(5)

    def test_daily_crash_window_reuses_final_verified_file(self):
        source=self.source_copy();config,d=self.config(source)
        first=jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),daily_slot='2026-11-04',background=False)
        package=Path(d['folder'])/first['results'][0]['filename'];checksum=a.digest(package)
        jobs.job_file(source,first['id']).unlink()
        second=jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),daily_slot='2026-11-04',background=False)
        self.assertEqual(second['status'],'completed');self.assertEqual(a.digest(package),checksum)
        self.assertEqual(len(list(Path(d['folder']).glob('*.rumibak'))),1)

    def test_retention_preserves_unrelated_backup_like_filename(self):
        source=self.source_copy();config,d=self.config(source)
        fake=Path(d['folder'])/('rumi-backup-'+config['installation_id']+'-unrelated.rumibak');fake.write_bytes(b'Not a known verified package')
        for day in ('2026-10-01','2026-10-02','2026-10-03'):
            jobs.request_job(source,1,'backup',self.recovery_password,uuid.uuid4(),daily_slot=day,background=False)
        self.assertTrue(fake.exists());self.assertEqual(len(list(Path(d['folder']).glob('*.rumibak'))),3)

    def test_windows_atomic_metadata_waits_for_readers(self):
        import time
        path=self.work/'metadata.json';a.atomic_json(path,{'revision':1})
        errors=[]
        def writer():
            try:a.atomic_json(path,{'revision':2})
            except Exception as exc:errors.append(type(exc).__name__)
        with path.open('r') as reader:
            t=threading.Thread(target=writer);t.start();time.sleep(.1)
        t.join(5)
        self.assertFalse(errors);self.assertEqual(a.read_json(path)['revision'],2)

    def test_local_history_write_failure_is_visible_and_not_success(self):
        source=self.source_copy();config,d=self.config(source)
        identifier=str(uuid.uuid4())
        job={'id':identifier,'actor_id':1,'kind':'backup','created_at':jobs.now().isoformat(),'status':'running','stage':'Copying','results':[]}
        a.atomic_json(jobs.job_file(source,identifier),job)
        with patch.object(jobs,'atomic_json',side_effect=OSError('Fictional local disk full')):
            jobs.fail_job(source,job,'Failed backup')
        self.assertEqual(jobs.get_job(source,identifier)['status'],'failed')
        self.assertEqual(jobs.history(source)[0]['status'],'failed')

    def test_migration_labels_cannot_hide_an_unexpected_schema(self):
        source=self.source_copy()
        with closing(sqlite3.connect(source/'clinic.sqlite3')) as db:
            db.execute('ALTER TABLE clinic_patient ADD COLUMN unexpected TEXT');db.commit()
        with self.assertRaises(BackupError):a.create_package(source,self.work/'altered.rumibak',self.recovery_password,work_parent=self.work)

    def test_older_supported_tail_migration_runs_only_on_staged_copy(self):
        source=self.source_copy()
        with closing(sqlite3.connect(source/'clinic.sqlite3')) as db:
            db.execute("DELETE FROM django_migrations WHERE app='clinic' AND name='0007_workflow_lock'");db.commit()
        package=self.work/'older.rumibak'
        result=a.create_package(source,package,self.recovery_password,work_parent=self.work)
        self.assertTrue(result['upgrade_required'])
        checksum=a.digest(package)
        target=self.work/'upgraded';recovery.restore(package,self.recovery_password,target,confirmed=True)
        self.assertFalse(a.inspect_database(target/'clinic.sqlite3')['upgrade_required'])
        self.assertEqual(a.digest(package),checksum)
        with closing(sqlite3.connect(source/'clinic.sqlite3')) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM django_migrations WHERE name='0007_workflow_lock'").fetchone()[0],0)

    def test_dpapi_no_plaintext_fallback(self):
        with patch.object(dpapi.os,'name','posix'):
            with self.assertRaises(BackupError):dpapi.protect_password('Fictional secret')
    def test_paths_do_not_silently_create_missing_drives(self):
        source=self.source_copy()
        for path in ['relative-folder',str(self.work/'missing'),str(source),str(source/'attachments')]:
            with self.assertRaises(BackupError):jobs.destination_folder(path,source)
        self.assertFalse((self.work/'missing').exists())

class BackupPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=User.objects.create_superuser('backupowner',password='Fictional-only-7362!')
        cls.doctor=User.objects.create_user('backupdoctor',password='Fictional-only-7362!');cls.doctor.groups.add(doctor_group())
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='rumi-backup-permissions-');self.addCleanup(self.temp.cleanup)
        self.override=override_settings(DATA_DIR=Path(self.temp.name));self.override.enable();self.addCleanup(self.override.disable)
    def paths(self):
        jid=str(uuid.uuid4());did=str(uuid.uuid4())
        return ['/backups/','/backups/destinations/new/','/backups/settings/','/backups/create/','/backups/export/','/backups/verify/','/backups/restore/',f'/backups/jobs/{jid}/',f'/backups/jobs/{jid}/status/',f'/backups/jobs/{jid}/download/{did}/',f'/backups/jobs/{jid}/retry/',f'/backups/destinations/{did}/toggle/']
    def test_anonymous_doctor_denial_all_pages_posts_and_downloads(self):
        for path in self.paths():self.assertEqual(self.client.get(path).status_code,302,path)
        self.client.force_login(self.doctor)
        for path in self.paths():
            self.assertEqual(self.client.get(path).status_code,403,path)
            self.assertEqual(self.client.post(path,dict(token=uuid.uuid4())).status_code,403,path)
    def test_owner_centre_csrf_escaping_and_restore_reauthentication(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/backups/'),'Back Up Now')
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.owner)
        self.assertEqual(secure.post('/backups/settings/',{}).status_code,403)
        with patch.object(jobs,'request_job') as submit:
            response=self.client.post('/backups/restore/',dict(package='fixture.rumibak',recovery_password='Fictional password',owner_password='wrong',confirmed='on',token=uuid.uuid4()))
            self.assertEqual(response.status_code,400);submit.assert_not_called()
        destination=Path(self.temp.name).parent/('destination-'+uuid.uuid4().hex);destination.mkdir();self.addCleanup(destination.rmdir)
        response=self.client.post('/backups/destinations/new/',dict(revision=0,token=uuid.uuid4(),label='<script>bad</script>',kind='local',folder=str(destination)))
        self.assertEqual(response.status_code,302);self.assertContains(self.client.get('/backups/'),'&lt;script&gt;')
        self.assertIn('no-store',self.client.get('/backups/').headers['Cache-Control'])
    def test_paused_requests_apply_no_changes(self):
        self.client.force_login(self.doctor);result=[]
        with runtime_access(Path(self.temp.name),exclusive=True):
            def request():result.append(self.client.get('/patients/').status_code)
            t=threading.Thread(target=request);t.start();t.join(timeout=5)
        self.assertEqual(result,[503])

    def test_status_poll_does_not_extend_idle_session(self):
        self.client.force_login(self.owner)
        from django.contrib.sessions.models import Session
        token=str(uuid.uuid4())
        a.atomic_json(jobs.job_file(settings.DATA_DIR,token),{'id':token,'created_at':'2026-11-06','kind':'backup','status':'completed','stage':'Done','actor_id':self.owner.pk,'results':[]})
        before=Session.objects.get(session_key=self.client.session.session_key).expire_date
        response=self.client.get(f'/backups/jobs/{token}/status/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(Session.objects.get(session_key=self.client.session.session_key).expire_date,before)
