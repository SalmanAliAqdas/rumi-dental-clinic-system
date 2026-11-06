"""Allowlisted, bounded packages. Only trusted application code is executed."""
from contextlib import closing,contextmanager
from datetime import datetime,timezone
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
import time
import uuid
import zipfile
from .crypto import BackupError,encrypt,decrypt,CHUNK,MAX_PACKAGE
from .locks import runtime_access,snapshot_access

ROOT=Path(__file__).resolve().parents[2]
APP_VERSION='5.0-trial'
FORMAT=1
MAX_FILES=100000
MAX_FILE=2*1024**3
MAX_MANIFEST=16*1024**2
STORAGE=re.compile(r'attachments/(originals|thumbnails)/[0-9a-f]{32}\.(png|jpg|pdf)\Z')
LIMITS={'RUMI_MAX_UPLOAD_BYTES':10*1024**2,'RUMI_MAX_IMAGE_SIDE':10000,'RUMI_MAX_IMAGE_PIXELS':25000000,'RUMI_MAX_PDF_PAGES':200}


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as handle:
        while block:=handle.read(CHUNK):result.update(block)
    return result.hexdigest()

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.part')
    try:
        with temporary.open('x',encoding='utf-8') as handle:
            os.chmod(temporary,0o600);json.dump(value,handle,ensure_ascii=False,sort_keys=True);handle.flush();os.fsync(handle.fileno())
        for attempt in range(80):
            try:
                os.replace(temporary,path);break
            except PermissionError as exc:
                if os.name!='nt' or getattr(exc,'winerror',None) not in (5,32,33) or attempt==79:raise
                time.sleep(.025)  # Windows readers may briefly deny replacement.
    finally:temporary.unlink(missing_ok=True)

def read_json(path,max_bytes=MAX_MANIFEST):
    path=Path(path)
    if path.stat().st_size>max_bytes:raise BackupError('JSON metadata exceeds the supported limit.')
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError,RecursionError):raise BackupError('Package/configuration metadata is invalid.') from None

def no_links(path):
    path=Path(path)
    for part in [path,*path.parents]:
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):raise BackupError('Symlinks and junctions are not allowed in backup/recovery paths.')
    return path

def known_migrations():
    import django
    django_root=Path(django.__file__).parent
    locations={'clinic':ROOT/'clinic/migrations',**{app:django_root/'contrib'/app/'migrations' for app in ('auth','contenttypes','sessions')}}
    return sorted([app,p.stem] for app,folder in locations.items() for p in folder.glob('[0-9]*.py'))

def schema_digest(migrations):return hashlib.sha256(json.dumps(sorted(migrations),separators=(',',':')).encode()).hexdigest()

def database_structure(connection):
    result={}
    for name,sql in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        if not sql or 'CREATE VIRTUAL TABLE' in sql.upper():raise BackupError('Virtual/unrecognized tables are not supported.')
        quoted='"'+name.replace('"','""')+'"'
        result[name]={'columns':[list(row)[1:] for row in connection.execute('PRAGMA table_info('+quoted+')')],
                      'foreign_keys':sorted([list(row) for row in connection.execute('PRAGMA foreign_key_list('+quoted+')')]),
                      'definition':re.sub(r'\s+',' ',sql).strip()}
    return result

def check_migration_history(applied):
    known=known_migrations()
    for app in ('clinic','auth','contenttypes','sessions'):
        have=[m for a,m in applied if a==app];supported=[m for a,m in known if a==app]
        if have!=supported[:len(have)]:raise BackupError('Migration history is inconsistent; a verified staged upgrade cannot be assumed.')
    if any(app=='clinic' for app,_ in applied) and any([m for a,m in applied if a==app]!=[m for a,m in known if a==app] for app in ('auth','contenttypes','sessions')):
        raise BackupError('This framework schema needs a separately supported migration before recovery.')


def inspect_database(database):
    try:
        with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as c:
            c.execute('PRAGMA trusted_schema=OFF');c.execute('PRAGMA query_only=ON')
            deadline=time.monotonic()+60
            c.set_progress_handler(lambda: int(time.monotonic()>deadline),10000)
            if c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type IN ('trigger','view')").fetchone()[0]:raise BackupError('Database contains unsupported executable views/triggers.')
            if c.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or c.execute('PRAGMA foreign_key_check').fetchall():raise BackupError('Database integrity or foreign-key verification failed.')
            migrations=sorted([a,b] for a,b in c.execute('SELECT app,name FROM django_migrations'))
            if not set(map(tuple,migrations)).issubset(set(map(tuple,known_migrations()))):raise BackupError('Backup requires unsupported future/unknown schema migrations. Install compatible source first.')
            check_migration_history(migrations)
            if migrations==known_migrations():
                trusted=read_json(ROOT/'clinic/backups/schema.json')
                if database_structure(c)!=trusted['tables']:raise BackupError('Database structure does not match the trusted application schema.')
            tables=[t for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            required={'auth_user','auth_group','django_session','django_migrations','clinic_patient','clinic_attachment'}
            if not required.issubset(tables):raise BackupError('Required clinic/account tables are missing.')
            counts={table:c.execute('SELECT COUNT(*) FROM "'+table.replace('"','""')+'"').fetchone()[0] for table in tables}
            attachments=[dict(storage_name=row[0],thumbnail_name=row[1],size=row[2]) for row in c.execute('SELECT storage_name,thumbnail_name,size FROM clinic_attachment')]
            return dict(migrations=migrations,schema_version=schema_digest(migrations),row_counts=counts,attachments=attachments,
                        upgrade_required=migrations!=known_migrations())
    except sqlite3.Error:raise BackupError('The database cannot be safely verified.') from None

def portable_settings(data):
    path=Path(data)/'portable.json'
    value=read_json(path,65536) if path.exists() else {'timezone':'Asia/Karachi','limits':LIMITS.copy()}
    # Use effective allowlisted settings when creating a backup inside the app.
    from django.conf import settings
    if settings.configured and getattr(settings,'DATA_DIR',None) and Path(settings.DATA_DIR).resolve()==Path(data).resolve():
        value={'timezone':'Asia/Karachi','limits':{key:getattr(settings,key,default) for key,default in LIMITS.items()}}
    validate_portable(value)
    return value

def validate_portable(value):
    if not isinstance(value,dict) or set(value)!= {'timezone','limits'} or value['timezone']!='Asia/Karachi' or not isinstance(value['limits'],dict) or set(value['limits'])!=set(LIMITS):raise BackupError('Portable configuration is unsupported.')
    if any(type(n)!=int or not 1<=n<=1024**3 for n in value['limits'].values()):raise BackupError('Portable upload limits are invalid.')

def check_attachments(root,info):
    root=Path(root)
    for a in info['attachments']:
        for name in (a['storage_name'],a['thumbnail_name']):
            if not name:continue
            relative='attachments/'+name
            if not STORAGE.fullmatch(relative):raise BackupError('Database contains an unsafe attachment reference.')
            path=no_links(root/relative)
            if not path.is_file():raise BackupError('An original/thumbnail referenced by the database is missing. Backup cannot be marked complete.')
            if name==a['storage_name'] and path.stat().st_size!=a['size']:raise BackupError('Original attachment size does not match its database record.')

def require_space(folder,amount):
    if shutil.disk_usage(folder).free < amount:raise BackupError('Insufficient free disk space for a verified complete package/staging copy.')

def source_files(data):
    data=no_links(Path(data).absolute()).resolve()
    database,secret=data/'clinic.sqlite3',data/'secret.key'
    if not database.is_file() or not database.stat().st_size or not secret.is_file() or not secret.read_bytes().strip():raise BackupError('Existing clinic database and matching secret are required; nothing was initialized.')
    files=[no_links(database),no_links(secret)]
    attachments=data/'attachments'
    if attachments.exists():
        no_links(attachments)
        for path in attachments.rglob('*'):
            no_links(path)
            if path.is_file():
                if not STORAGE.fullmatch(path.relative_to(data).as_posix()):raise BackupError('Attachment folder contains an unsupported file; review it before backup.')
                files.append(path)
            elif not path.is_dir():raise BackupError('Unsupported attachment filesystem entry.')
    if len(files)>MAX_FILES-10 or any(p.stat().st_size>MAX_FILE for p in files):raise BackupError('Clinic files exceed the supported count/file-size limit.')
    return files

def snapshot(data,stage):
    """Request/file lease + SQLite reserved write lock cover DB and file copies."""
    data,stage=no_links(Path(data).absolute()).resolve(),Path(stage)
    with snapshot_access(data):
        files=source_files(data)
        estimate=sum(p.stat().st_size for p in files)
        if estimate>MAX_PACKAGE-16*1024**2:raise BackupError('Complete data exceeds the supported package limit.')
        require_space(stage,estimate*3+16*1024**2)
        try:
            with closing(sqlite3.connect((data/'clinic.sqlite3').as_uri()+'?mode=rw',uri=True,timeout=10)) as writer:
                writer.execute('BEGIN IMMEDIATE')
                try:
                    with closing(sqlite3.connect((data/'clinic.sqlite3').as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(stage/'clinic.sqlite3')) as target:
                        source.backup(target)
                    for path in files:
                        if path.name=='clinic.sqlite3':continue
                        destination=stage/path.relative_to(data);destination.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(path,destination);os.chmod(destination,0o600)
                    atomic_json(stage/'portable.json',portable_settings(data))
                finally:writer.rollback()
        except sqlite3.Error:raise BackupError('SQLite snapshot could not be completed; no package was finalized.') from None
    info=inspect_database(stage/'clinic.sqlite3');check_attachments(stage,info)
    return info

def safe_csv(value):
    text=str(value) if value is not None else ''
    return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else text

def migration_export(stage,info):
    """All business rows, stable PK/FK values and a machine-readable dictionary."""
    stage=Path(stage)
    dictionary={};tables={};export_bytes=0
    with closing(sqlite3.connect((stage/'clinic.sqlite3').as_uri()+'?mode=ro',uri=True)) as c:
        c.row_factory=sqlite3.Row
        for table in sorted(info['row_counts']):
            if not table.startswith('clinic_') and table not in ('auth_user','auth_group','auth_user_groups','auth_permission','auth_group_permissions','auth_user_user_permissions','django_content_type'):continue
            quoted='"'+table.replace('"','""')+'"'
            columns=list(c.execute('PRAGMA table_info('+quoted+')'))
            excluded={'password','last_login'} if table=='auth_user' else set()
            # Login throttles are technical state, not patient/business records.
            if table=='clinic_loginattempt':continue
            names=[row['name'] for row in columns if row['name'] not in excluded]
            from decimal import Decimal
            money_columns={r['name'] for r in columns if 'decimal' in r['type'].lower()}
            rows=[]
            for row in c.execute('SELECT * FROM '+quoted+' ORDER BY rowid'):
                value={k:(format(Decimal(str(row[k])),'.2f') if k in money_columns and row[k] is not None else row[k]) for k in names}
                export_bytes+=len(json.dumps(value,ensure_ascii=False).encode('utf-8'))
                if export_bytes>MAX_MANIFEST-1024**2:raise BackupError('Structured migration export exceeds the supported 15 MiB record limit; use complete recovery backup and plan a larger-volume migration.')
                rows.append(value)
            tables[table]=rows
            dictionary[table]={'fields':[{'name':r['name'],'sqlite_type':r['type'],'primary_key':bool(r['pk']),'nullable':not bool(r['notnull']) and not bool(r['pk'])} for r in columns if r['name'] in names],
                'foreign_keys':[dict(row) for row in c.execute('PRAGMA foreign_key_list('+quoted+')')]}
            out=stage/'csv'/ (table+'.csv');out.parent.mkdir(exist_ok=True)
            with out.open('w',encoding='utf-8',newline='') as handle:
                w=csv.writer(handle);w.writerow(names)
                for row in rows:w.writerow([safe_csv(row[k]) for k in names])
    # Historical JSON may contain entered clinical text; retain it as data,
    # never executable code. Password hashes only live in auth_user.password.
    mappings=[]
    for a in tables.get('clinic_attachment',[]):
        original='attachments/'+a['storage_name'];thumbnail='attachments/'+a['thumbnail_name'] if a['thumbnail_name'] else None
        mappings.append(dict(attachment_id=a['id'],patient_id=a['patient_id'],visit_id=a['visit_id'],original=original,original_sha256=digest(stage/original),thumbnail=thumbnail,thumbnail_sha256=digest(stage/thumbnail) if thumbnail else None))
    atomic_json(stage/'attachment-map.json',mappings)
    atomic_json(stage/'records.json',{'format_version':1,'exported_at':datetime.now(timezone.utc).isoformat(),'tables':tables})
    atomic_json(stage/'dictionary.json',{'format_version':1,'tables':dictionary,'notes':'JSON-valued SQLite columns remain JSON strings. Money is stored as decimal text in records below. CSV is formula-neutralized; records.json preserves original Unicode values. No login passwords/sessions/secret included.'})
    for name in ('clinic.sqlite3','secret.key','portable.json'):(stage/name).unlink(missing_ok=True)

def pack_stage(stage,package,password,kind,installation_id,daily_slot=None,info=None):
    stage,package=Path(stage),Path(package)
    info=info or inspect_database(stage/'clinic.sqlite3')
    files={}
    for path in sorted(stage.rglob('*')):
        if path.is_file():files[path.relative_to(stage).as_posix()]={'size':path.stat().st_size,'sha256':digest(path)}
    manifest={'format_version':FORMAT,'application':'Rumi Dental Care','app_version':APP_VERSION,'kind':kind,
        'backup_id':str(uuid.uuid4()),'installation_id':installation_id,'created_at':datetime.now(timezone.utc).isoformat(),
        'daily_slot':daily_slot,'schema_version':info['schema_version'],'migrations':info['migrations'],'row_counts':info['row_counts'],'files':files}
    atomic_json(stage/'manifest.json',manifest)
    archive=stage.parent/(stage.name+'.zip')
    try:
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            for name in [*files,'manifest.json']:z.write(stage/name,name)
        encrypt(archive,package,password)
    finally:archive.unlink(missing_ok=True)
    return manifest

def allowed_name(name,kind):
    if '\\' in name or ':' in name or name.startswith('/') or str(PurePosixPath(name))!=name or '..' in PurePosixPath(name).parts:return False
    common=name=='manifest.json' or bool(STORAGE.fullmatch(name))
    if kind=='backup':return common or name in ('clinic.sqlite3','secret.key','portable.json')
    if kind=='export':return common or name in ('records.json','dictionary.json','attachment-map.json') or bool(re.fullmatch(r'csv/(clinic|auth|django)_[a-z0-9_]+\.csv',name))
    return False

@contextmanager
def verified_package(package,password,work_parent=None,expected_kind=None):
    package=no_links(Path(package).absolute()).resolve()
    if not package.is_file():raise BackupError('Selected encrypted package is unavailable.')
    parent=Path(work_parent) if work_parent else None
    if parent:require_space(parent,package.stat().st_size*2+16*1024**2)
    with tempfile.TemporaryDirectory(prefix='rumi-verify-',dir=parent) as temp:
        root=Path(temp);plain=root/'authenticated.zip';stage=root/'data';stage.mkdir()
        decrypt(package,plain,password)  # Never parse/extract unauthenticated plaintext.
        try:
            with zipfile.ZipFile(plain) as z:
                entries=z.infolist()
                if len(entries)>MAX_FILES or len({e.filename.casefold() for e in entries})!=len(entries):raise BackupError('Archive contains too many or duplicate filenames.')
                if sum(e.file_size for e in entries)>MAX_PACKAGE:raise BackupError('Archive expands beyond the supported limit.')
                for e in entries:
                    mode=e.external_attr>>16
                    if e.is_dir() or stat.S_IFMT(mode) not in (0,stat.S_IFREG) or e.compress_type!=zipfile.ZIP_STORED or e.file_size!=e.compress_size or e.file_size>MAX_FILE:
                        raise BackupError('Archive contains links, unsupported compression or oversized files.')
                    if not allowed_name(e.filename,'backup') and not allowed_name(e.filename,'export'):raise BackupError('Archive contains an unsafe or unsupported path.')
                mi=z.getinfo('manifest.json')
                if mi.file_size>MAX_MANIFEST:raise BackupError('Manifest exceeds the supported limit.')
                manifest=json.loads(z.read(mi).decode('utf-8'))
                if not isinstance(manifest,dict) or manifest.get('format_version')!=FORMAT or manifest.get('application')!='Rumi Dental Care' or manifest.get('app_version')!=APP_VERSION:
                    raise BackupError('Unsupported future/unknown package or application version.')
                kind=manifest.get('kind')
                if kind not in ('backup','export') or (expected_kind and kind!=expected_kind):raise BackupError('This is a migration export, not a disaster-recovery backup.')
                files=manifest.get('files')
                if not isinstance(files,dict) or set(files)!={e.filename for e in entries}-{'manifest.json'} or any(not allowed_name(n,kind) for n in files):raise BackupError('Manifest/file inventory does not match the archive.')
                for name,metadata in files.items():
                    if not isinstance(metadata,dict) or metadata.get('size')!=z.getinfo(name).file_size or not re.fullmatch('[0-9a-f]{64}',str(metadata.get('sha256',''))):raise BackupError('Manifest file metadata is invalid.')
                    destination=stage/name;destination.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(name) as incoming,destination.open('xb') as outgoing:
                        os.chmod(destination,0o600);shutil.copyfileobj(incoming,outgoing,CHUNK)
                    if digest(destination)!=metadata['sha256']:raise BackupError('Package file checksum verification failed.')
            if kind=='backup':
                if not {'clinic.sqlite3','secret.key','portable.json'}.issubset(files):raise BackupError('Complete database, matching secret and portable configuration are required.')
                if not 16<=(stage/'secret.key').stat().st_size<=4096 or not (stage/'secret.key').read_bytes().strip():raise BackupError('Application secret is missing or invalid.')
                validate_portable(read_json(stage/'portable.json',65536))
                info=inspect_database(stage/'clinic.sqlite3');check_attachments(stage,info)
                if manifest.get('migrations')!=info['migrations'] or manifest.get('schema_version')!=info['schema_version'] or manifest.get('row_counts')!=info['row_counts']:raise BackupError('Database schema/row inventory does not match the manifest.')
                manifest['upgrade_required']=info['upgrade_required']
                if info['upgrade_required']:
                    require_space(root,package.stat().st_size+16*1024**2)
                    upgrade=root/'compatibility-check';shutil.copytree(stage,upgrade)
                    from .recovery import upgrade_stage
                    upgrade_stage(upgrade)  # Runs only this checkout's trusted migration code.
                    shutil.rmtree(upgrade)
            else:
                if not {'records.json','dictionary.json','attachment-map.json'}.issubset(files) or {'clinic.sqlite3','secret.key'}&files.keys():raise BackupError('Migration export is incomplete or contains excluded credentials.')
                records=read_json(stage/'records.json')
                if not isinstance(records.get('tables'),dict) or any('password' in row for row in records['tables'].get('auth_user',[])):raise BackupError('Migration export contains invalid user records.')
            yield stage,manifest
        except (zipfile.BadZipFile,KeyError,ValueError,TypeError,UnicodeError,RecursionError,OverflowError):raise BackupError('Package structure or manifest is invalid.') from None

def create_package(data,package,password,kind='backup',installation_id=None,daily_slot=None,work_parent=None):
    package=Path(package)
    with tempfile.TemporaryDirectory(prefix='rumi-snapshot-',dir=work_parent) as temp:
        stage=Path(temp)/'data';stage.mkdir()
        info=snapshot(data,stage)
        if kind=='export':migration_export(stage,info)
        manifest=pack_stage(stage,package,password,kind,installation_id or str(uuid.uuid4()),daily_slot,info)
    try:
        with verified_package(package,password,work_parent,kind) as (_,verified):return verified
    except BaseException:
        package.unlink(missing_ok=True)
        raise
