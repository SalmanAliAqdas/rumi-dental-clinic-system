"""Offline directory activation with a retained verified rollback and journal."""
from contextlib import ExitStack,closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from .archive import (ROOT,BackupError,atomic_json,read_json,no_links,snapshot,inspect_database,check_attachments,
    verified_package,known_migrations,digest,require_space)
from .locks import lease,lock_path,runtime_access


def journal_path(target):
    target=Path(target).resolve()
    return target.parent/('.'+target.name+'.rumi-restore.json')

def authenticate_owner(data,username,password):
    try:
        with closing(sqlite3.connect((Path(data).resolve()/'clinic.sqlite3').as_uri()+'?mode=ro',uri=True)) as c:
            c.execute('PRAGMA trusted_schema=OFF')
            row=c.execute('SELECT password,is_active,is_superuser FROM auth_user WHERE username=?',(username,)).fetchone()
    except sqlite3.Error:raise BackupError('Existing installation cannot be re-authenticated safely.') from None
    from django.conf import settings,global_settings
    if not settings.configured:settings.configure(PASSWORD_HASHERS=global_settings.PASSWORD_HASHERS)
    from django.contrib.auth.hashers import check_password
    if not row or not row[1] or not row[2] or not check_password(password,row[0]):raise BackupError('Current active Owner authentication failed. No data replaced.')

def upgrade_stage(stage):
    info=inspect_database(stage/'clinic.sqlite3')
    if info['upgrade_required']:
        env={**os.environ,'DJANGO_SETTINGS_MODULE':'config.settings','RUMI_DATA_DIR':str(stage),'RUMI_DISABLE_BACKUP_SCHEDULER':'1'}
        result=subprocess.run([sys.executable,str(ROOT/'manage.py'),'migrate','--noinput'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=300)
        if result.returncode:raise BackupError('Trusted staged migrations failed. The original package and current installation are unchanged.')
    info=inspect_database(stage/'clinic.sqlite3')
    if info['upgrade_required']:raise BackupError('Staged schema upgrade did not reach this application version.')
    check_attachments(stage,info)
    return info

def activation_probe(target,expected):
    info=inspect_database(target/'clinic.sqlite3');check_attachments(target,info)
    for name,checksum in expected.items():
        if not (target/name).is_file() or digest(target/name)!=checksum:raise BackupError('Activated runtime did not match the verified staged files.')
    with closing(sqlite3.connect((target/'clinic.sqlite3').as_uri()+'?mode=ro',uri=True)) as c:
        if c.execute('SELECT COUNT(*) FROM django_session').fetchone()[0]:raise BackupError('Restored sessions were not cleared.')

def validate_journal(target,journal):
    if not isinstance(journal,dict) or journal.get('target')!=str(target):raise BackupError('Restore journal is invalid; manual inspection is required.')
    for key,prefix in [('stage','stage'),('rollback','rollback')]:
        value=journal.get(key)
        if value is None and key=='rollback':continue
        path=Path(value)
        if path.parent!=target.parent or not path.name.startswith('.'+target.name+'.rumi-'+prefix+'-') or len(path.name.split('-')[-1])!=32:
            raise BackupError('Restore journal paths are unsafe; no filesystem changes made.')
        no_links(path)
    if journal.get('state') not in ('prepared','old_moved','new_moved','committed'):raise BackupError('Restore journal state is invalid.')

def repair(target,username='',owner_password=''):
    target=Path(target).resolve();path=journal_path(target)
    if not path.exists():raise BackupError('No interrupted activation journal exists.')
    journal=read_json(path,65536);validate_journal(target,journal)
    rollback=Path(journal['rollback']) if journal['rollback'] else None
    old=rollback if rollback and (rollback/'clinic.sqlite3').is_file() else target
    if (old/'clinic.sqlite3').is_file():authenticate_owner(old,username,owner_password)
    with lease(lock_path(target,'server')),lease(lock_path(target,'job')),runtime_access(target,exclusive=True):
        if journal['state']=='committed':
            info=inspect_database(target/'clinic.sqlite3');check_attachments(target,info);path.unlink();return 'Verified committed restoration retained.'
        if rollback and rollback.exists():
            if target.exists():os.replace(target,target.parent/('.'+target.name+'.rumi-failed-'+uuid.uuid4().hex))
            os.replace(rollback,target)
        elif journal['state'] in ('old_moved','new_moved') and target.exists():
            os.replace(target,target.parent/('.'+target.name+'.rumi-failed-'+uuid.uuid4().hex))
        path.unlink()
        return 'Previous installation recovered. Retry restore only after reviewing the package.'

def restore(package,password,target,*,confirmed=False,username='',owner_password=''):
    if not confirmed:raise BackupError('Explicit restore confirmation is required.')
    target=no_links(Path(target).absolute())
    if not target.parent.is_dir():raise BackupError('Choose an existing parent folder for the explicit data directory.')
    target=target.resolve();journal_file=journal_path(target)
    if journal_file.exists():raise BackupError('An interrupted restore needs the repair command before startup/restoration.')
    exists=target.exists();has_database=(target/'clinic.sqlite3').is_file()
    if exists and (not target.is_dir() or (not has_database and any(target.iterdir()))):raise BackupError('Target is not an empty directory or initialized clinic runtime. Nothing overwritten.')
    package=no_links(Path(package).absolute()).resolve()
    if package.is_relative_to(target):raise BackupError('Move the encrypted package outside the directory being restored before activation.')
    # This is a separate helper operation. A running guarded Rumi server holds
    # the server lease for its entire lifetime, so ordinary requests cannot do this.
    with lease(lock_path(target,'server')),lease(lock_path(target,'job')),runtime_access(target,exclusive=True):
        exists=target.exists();has_database=(target/'clinic.sqlite3').is_file()
        if exists and (not target.is_dir() or (not has_database and any(target.iterdir()))):raise BackupError('Target changed before activation; nothing was replaced.')
        if has_database:authenticate_owner(target,username,owner_password)
        with verified_package(package,password,target.parent,'backup') as (verified,manifest):
            stage=target.parent/('.'+target.name+'.rumi-stage-'+uuid.uuid4().hex)
            rollback=target.parent/('.'+target.name+'.rumi-rollback-'+uuid.uuid4().hex) if exists else None
            require_space(target.parent,sum(p.stat().st_size for p in verified.rglob('*') if p.is_file())*3+16*1024**2)
            shutil.copytree(verified,stage)
            try:
                upgrade_stage(stage)
                with closing(sqlite3.connect(stage/'clinic.sqlite3')) as c:
                    c.execute('PRAGMA trusted_schema=OFF');c.execute('DELETE FROM django_session');c.commit()
                expected={p.relative_to(stage).as_posix():digest(p) for p in stage.rglob('*') if p.is_file()}
                if has_database:
                    with tempfile.TemporaryDirectory(prefix='rumi-pre-restore-',dir=target.parent) as temp:
                        snapshot(target,Path(temp))  # verified DB + secret + complete attachments before replacement
                journal={'target':str(target),'stage':str(stage),'rollback':str(rollback) if rollback else None,'state':'prepared','backup_id':manifest['backup_id']}
                atomic_json(journal_file,journal)
                try:
                    if exists:os.replace(target,rollback)
                    journal['state']='old_moved';atomic_json(journal_file,journal)
                    os.replace(stage,target)
                    journal['state']='new_moved';atomic_json(journal_file,journal)
                    activation_probe(target,expected)
                    journal['state']='committed';atomic_json(journal_file,journal)
                    journal_file.unlink()
                except BaseException:
                    if rollback and rollback.exists():
                        if target.exists():os.replace(target,target.parent/('.'+target.name+'.rumi-failed-'+uuid.uuid4().hex))
                        os.replace(rollback,target)
                    elif not exists and target.exists():os.replace(target,target.parent/('.'+target.name+'.rumi-failed-'+uuid.uuid4().hex))
                    journal_file.unlink(missing_ok=True)
                    raise
                return {'backup_id':manifest['backup_id'],'created_at':manifest['created_at'],'target':str(target),'rollback':str(rollback) if rollback else None,'sessions_cleared':True}
            finally:
                # Only a directory created by this invocation, with its checked
                # sibling/UUID boundary, may be removed here. Never remove target.
                if stage.exists() and stage.parent==target.parent and stage.name.startswith('.'+target.name+'.rumi-stage-'):
                    shutil.rmtree(stage)
