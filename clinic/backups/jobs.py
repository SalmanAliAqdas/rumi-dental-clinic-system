"""Owner-only background jobs, per-destination results and in-process scheduling."""
from datetime import datetime,time as clock_time,timedelta,timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import uuid
from zoneinfo import ZoneInfo
from .archive import (BackupError,ROOT,atomic_json,read_json,no_links,digest,require_space,create_package,verified_package)
from .locks import lease,lock_path,Busy
from .dpapi import protect_password,read_password

PK=ZoneInfo('Asia/Karachi')
_volatile_failures={}
_worker_condition=threading.Condition()
_workers={}
KINDS={'local':'Saved to local folder','external':'Saved to external folder','gdrive':'Saved to Google Drive folder'}


def now():return datetime.now(timezone.utc)
def control(data):return Path(data)/'backup-control'
def default_config():return {'revision':0,'installation_id':None,'destinations':[],'automatic':False,'daily_time':'18:00','keep_last':7}
def load_config(data):
    path=control(data)/'config.json'
    return read_json(path,1024**2) if path.exists() else default_config()

def save_config(data,actor,changes,revision):
    with lease(lock_path(data,'backup-config')):
        config=load_config(data)
        if config['revision']!=revision:raise BackupError('Backup settings changed in another tab. Reload before saving.')
        config.update(changes);config['revision']+=1
        config['installation_id']=config['installation_id'] or str(uuid.uuid4())
        atomic_json(control(data)/'config.json',config)
        folder=control(data)/'events';folder.mkdir(parents=True,exist_ok=True)
        atomic_json(folder/(uuid.uuid4().hex+'.json'),{'actor_id':actor,'at':now().isoformat(),'action':'backup_configuration','revision':config['revision'],'changed_keys':sorted(changes)})
        return config

def destination_folder(path,data):
    path=Path(path)
    if not path.is_absolute():raise BackupError('Enter an absolute existing folder path. Create/select the folder in Windows Explorer first.')
    no_links(path)
    folder=path.resolve();data=Path(data).resolve()
    if not folder.is_dir():raise BackupError('Destination folder/drive is unavailable. No other folder was substituted.')
    if folder==data or folder.is_relative_to(data):raise BackupError('Choose a backup folder outside the live data directory.')
    if folder.is_relative_to(ROOT) and not folder.is_relative_to(ROOT/'runtime'):raise BackupError('Do not store backups in application source folders; use a folder under runtime or another drive.')
    return folder

def google_staging(path,folder,data):
    if not path:raise BackupError('Google Drive requires an explicitly selected unsynchronized staging folder on the same volume.')
    staging=destination_folder(path,data)
    if staging==folder or staging.is_relative_to(folder) or folder.is_relative_to(staging):raise BackupError('Choose a separate staging folder outside the synchronized destination tree.')
    if staging.stat().st_dev!=folder.stat().st_dev:raise BackupError('Google Drive staging and destination must be on the same volume for atomic completion.')
    return staging


def configure_automatic(data,actor,revision,automatic,daily_time,keep_last,password=''):
    try:clock_time.fromisoformat(daily_time)
    except ValueError:raise BackupError('Choose a valid daily Pakistan time.') from None
    if not 2<=keep_last<=365:raise BackupError('Keep between 2 and 365 dated verified versions per destination.')
    credential=control(data)/'automatic.dpapi'
    if automatic:
        if password:
            if len(password)<12:raise BackupError('Use a recovery password of at least 12 characters.')
            protected=protect_password(password)
        elif credential.is_file():read_password(credential.read_bytes());protected=None
        else:raise BackupError('Set a recovery password before enabling automatic backups.')
    else:protected=None
    # Lock settings and credential together; DPAPI cannot silently fall back.
    with lease(lock_path(data,'backup-config')):
        if load_config(data)['revision']!=revision:raise BackupError('Backup settings changed. Reload before saving.')
        if protected is not None:
            credential.parent.mkdir(parents=True,exist_ok=True)
            temporary=credential.with_suffix('.part')
            try:
                with temporary.open('wb') as handle:os.chmod(temporary,0o600);handle.write(protected);handle.flush();os.fsync(handle.fileno())
                os.replace(temporary,credential)
            finally:temporary.unlink(missing_ok=True)
        return save_config(data,actor,{'automatic':automatic,'daily_time':daily_time,'keep_last':keep_last},revision)

def history(data):
    folder=control(data)/'jobs'
    if not folder.exists():return []
    jobs=[]
    for p in folder.glob('*.json'):
        try:
            value=read_json(p,4*1024**2);jobs.append(_volatile_failures.get((str(Path(data).resolve()),value['id']),value))
        except (OSError,BackupError):continue
    return sorted(jobs,key=lambda j:j['created_at'],reverse=True)

def job_file(data,identifier):
    try:identifier=str(uuid.UUID(str(identifier)))
    except (ValueError,TypeError,AttributeError):raise BackupError('Invalid backup job reference.') from None
    return control(data)/'jobs'/(identifier+'.json')

def get_job(data,identifier):
    path=job_file(data,identifier)
    return _volatile_failures.get((str(Path(data).resolve()),str(uuid.UUID(str(identifier))))) or read_json(path,4*1024**2)

def update_job(data,job,**changes):
    job.update(changes)
    try:atomic_json(job_file(data,job['id']),job)
    except OSError:
        failed={**job,'status':'failed','stage':'Local job history could not be saved (disk full/unavailable). No package is claimed successful; free space and retry.'}
        _volatile_failures[(str(Path(data).resolve()),job['id'])]=failed
        if len(_volatile_failures)>100:_volatile_failures.pop(next(iter(_volatile_failures)))
        raise BackupError(failed['stage']) from None

def fail_job(data,job,message):
    try:update_job(data,job,status='failed',stage=message)
    except BackupError:pass  # The in-memory failure remains visible if disk is full.


def completed_for(data,destination_id,slot):
    for job in history(data):
        if job.get('daily_slot')!=slot:continue
        for result in job.get('results',[]):
            if result.get('destination_id')!=destination_id or result.get('status')!='verified':continue
            try:
                path=no_links(Path(result['folder'])/result['filename'])
                if path.is_file() and path.stat().st_size==result['size']:return True
            except (OSError,BackupError):pass
    return False


def due_slot(config,instant=None):
    instant=(instant or now()).astimezone(PK)
    when=clock_time.fromisoformat(config['daily_time'])
    return (instant.date() if instant.time().replace(tzinfo=None)>=when else instant.date()-timedelta(days=1)).isoformat()

def publish(package,password,destination,data,filename,kind):
    folder=destination_folder(destination['folder'],data)
    identity=(folder.stat().st_dev,folder.stat().st_ino)
    final=folder/filename
    if final.exists():raise BackupError('Destination filename already exists; it was not overwritten.')
    require_space(folder,package.stat().st_size+1024**2)
    staging=google_staging(destination.get('staging_folder',''),folder,data) if destination['kind']=='gdrive' else folder
    require_space(staging,package.stat().st_size+1024**2)
    temporary=staging/(filename+'.'+uuid.uuid4().hex+'.part')
    try:
        with package.open('rb') as incoming,temporary.open('xb') as outgoing:
            os.chmod(temporary,0o600);shutil.copyfileobj(incoming,outgoing,1024**2);outgoing.flush();os.fsync(outgoing.fileno())
        if digest(temporary)!=digest(package):raise BackupError('Destination copy checksum differs from the verified package.')
        with verified_package(temporary,password,control(data)/'work',kind):pass
        check=destination_folder(destination['folder'],data)
        if (check.stat().st_dev,check.stat().st_ino)!=identity:raise BackupError('Destination drive/folder changed during the backup.')
        if final.exists():raise BackupError('Destination filename was claimed by another operation.')
        os.replace(temporary,final)
        return {'destination_id':destination['id'],'label':destination['label'],'folder':str(folder),'filename':filename,
                'status':'verified','sha256':digest(final),'size':final.stat().st_size,'message':KINDS[destination['kind']],'verified_at':now().isoformat()}
    finally:temporary.unlink(missing_ok=True)

def retention(data,config,destination):
    folder=destination_folder(destination['folder'],data)
    candidates=[];seen=set()
    for job in history(data):
        if job['kind']!='backup':continue
        for result in job.get('results',[]):
            if result.get('destination_id')==destination['id'] and result.get('status')=='verified' and result['filename'] not in seen:
                seen.add(result['filename']);candidates.append((job,result))
    confirmed=[]
    identity=(folder.stat().st_dev,folder.stat().st_ino)
    for job,result in candidates:
        path=folder/result['filename']
        if Path(result['filename']).name!=result['filename'] or not result['filename'].startswith('rumi-backup-'+config['installation_id']+'-') or path.suffix!='.rumibak':continue
        no_links(path)
        if path.is_file() and digest(path)==result['sha256']:confirmed.append((job,result,path))
    # Count only present, checksum-matching copies when protecting generations.
    # History for a missing drive/file cannot justify deleting the last good copy.
    for job,result,path in confirmed[max(2,config['keep_last']):]:
        current=destination_folder(destination['folder'],data)
        if (current.stat().st_dev,current.stat().st_ino)!=identity:raise BackupError('Destination changed; older copies were retained.')
        if path.is_file() and digest(path)==result['sha256']:
            path.unlink();result['status']='pruned';atomic_json(job_file(data,job['id']),job)


def run_job(data,identifier,password):
    data=Path(data).resolve();job=get_job(data,identifier)
    try:
        with lease(lock_path(data,'job')):
            # A dead worker cannot retain an OS lease. Mark its retained status
            # accurately before a retry, without deleting its destination files.
            for previous in history(data):
                if previous['id']!=identifier and previous['status'] in ('queued','running'):
                    update_job(data,previous,status='interrupted',stage='Interrupted before completion; retry with the recovery password.')
            update_job(data,job,status='running',stage='Preparing')
            work=control(data)/'work';work.mkdir(parents=True,exist_ok=True)
            if job['kind'] in ('verify','restore_preview'):
                with verified_package(job['package'],password,work,'backup' if job['kind']=='restore_preview' else None) as (_,manifest):
                    summary={k:manifest[k] for k in ('backup_id','created_at','app_version','kind','schema_version','row_counts')}
                    summary['upgrade_required']=manifest.get('upgrade_required',False)
                update_job(data,job,status='completed',stage='Verified without replacing working data',preview=summary)
                return
            config=load_config(data)
            if not config['installation_id']:config=save_config(data,job['actor_id'],{},config['revision'])
            destinations=[d for d in config['destinations'] if d['enabled']]
            if not destinations:raise BackupError('Configure at least one enabled destination first.')
            slot=job.get('daily_slot')
            destinations=[d for d in destinations if not slot or not completed_for(data,d['id'],slot)]
            if not destinations:
                update_job(data,job,status='completed',stage='Daily backup already verified for all enabled destinations');return
            order={d['id']:i for i,d in enumerate(destinations)}
            available=[]
            for destination in destinations:
                try:
                    folder=destination_folder(destination['folder'],data)
                    if destination['kind']=='gdrive':google_staging(destination.get('staging_folder',''),folder,data)
                    available.append(destination)
                except (OSError,BackupError):
                    job['results'].append({'destination_id':destination['id'],'label':destination['label'],'status':'failed','message':'Configured folder/drive or unsynchronized staging is unavailable. No alternate folder was used.'})
            update_job(data,job)
            if not available:
                update_job(data,job,status='failed',stage='No configured destination is available. Reconnect the drive/folder and retry.');return
            suffix='.rumibak' if job['kind']=='backup' else '.rumiexport'
            label='daily-'+slot if slot else now().strftime('%Y%m%dT%H%M%SZ')+'-'+job['id']
            filename='rumi-'+job['kind']+'-'+config['installation_id']+'-'+label+suffix
            with tempfile.TemporaryDirectory(prefix='job-',dir=work) as temp:
                package=Path(temp)/('package'+suffix)
                update_job(data,job,stage='Coordinated database/attachment snapshot, then encryption and verification')
                create_package(data,package,password,job['kind'],config['installation_id'],slot,work)
                for destination in available:
                    update_job(data,job,stage='Verifying destination: '+destination['label'])
                    try:
                        existing=destination_folder(destination['folder'],data)/filename
                        if slot and existing.exists():
                            with verified_package(existing,password,work,'backup') as (_,manifest):
                                if manifest['installation_id']!=config['installation_id'] or manifest['daily_slot']!=slot:raise BackupError('Existing daily package does not match this installation/day.')
                            result=dict(destination_id=destination['id'],label=destination['label'],folder=str(existing.parent),filename=filename,status='verified',sha256=digest(existing),size=existing.stat().st_size,message=KINDS[destination['kind']],verified_at=now().isoformat())
                        else:result=publish(package,password,destination,data,filename,job['kind'])
                    except (OSError,BackupError) as exc:
                        result={'destination_id':destination['id'],'label':destination['label'],'status':'failed','message':str(exc) if isinstance(exc,BackupError) else 'Destination disconnected, unavailable, full or not writable. No alternate folder was used.'}
                    job['results'].append(result);job['results'].sort(key=lambda r:order[r['destination_id']]);update_job(data,job)
            failures=any(r['status']=='failed' for r in job['results'])
            status='partial' if failures and any(r['status']=='verified' for r in job['results']) else 'failed' if failures else 'completed'
            update_job(data,job,status=status,stage='Some/all destinations failed; retry available' if failures else 'Completed and verified')
            if not failures and job['kind']=='backup':
                for destination in destinations:
                    try:retention(data,config,destination)
                    except (OSError,BackupError):update_job(data,job,retention_warning='Some older copies were retained because pruning could not be completed safely.')
    except (Busy,BackupError,OSError) as exc:
        if not isinstance(exc,BackupError):
            import logging
            logging.getLogger('django.request').error('backup_storage_or_lease_failure',exc_info=True)
        fail_job(data,job,str(exc) if isinstance(exc,BackupError) else 'Another job is running or local storage is unavailable. Retry when ready.')
    except Exception:
        import logging
        logging.getLogger('django.request').error('backup_job_failed',exc_info=True)
        fail_job(data,job,'Backup operation failed safely. No incomplete package is considered verified.')
    finally:password=None

def request_job(data,actor,kind,password,token,package=None,daily_slot=None,background=True):
    if kind not in ('backup','export','verify','restore_preview'):raise BackupError('Unknown backup operation.')
    if kind in ('backup','export') and len(password)<12:raise BackupError('Use a recovery password of at least 12 characters.')
    identifier=str(uuid.UUID(str(token)));path=job_file(data,identifier)
    with lease(lock_path(data,'backup-config')):
        if path.exists():
            job=get_job(data,identifier)
            if job['actor_id']!=actor or job['kind']!=kind:raise BackupError('Submission reference belongs to another operation.')
            return job
        job={'id':identifier,'actor_id':actor,'kind':kind,'created_at':now().isoformat(),'status':'queued','stage':'Queued','daily_slot':daily_slot,'results':[]}
        if package:
            candidate=no_links(Path(package).absolute())
            if not candidate.is_file() or candidate.suffix not in ('.rumibak','.rumiexport'):raise BackupError('Select an existing encrypted .rumibak/.rumiexport package path.')
            job['package']=str(candidate.resolve())
        atomic_json(path,job)
    if background:
        key=str(Path(data).resolve())
        def worker():
            try:run_job(Path(data),identifier,password)
            finally:
                with _worker_condition:
                    _workers[key].discard(threading.current_thread())
                    if not _workers[key]:_workers.pop(key,None)
                    _worker_condition.notify_all()
        thread=threading.Thread(target=worker,daemon=True,name='rumi-backup-job')
        with _worker_condition:
            _workers.setdefault(key,set()).add(thread)
            try:thread.start()
            except Exception:
                _workers[key].discard(thread)
                raise
    else:run_job(data,identifier,password)
    return get_job(data,identifier)


def wait_for_jobs(data):
    """Called after request/scheduler admission stops; includes not-yet-leased workers."""
    key=str(Path(data).resolve())
    with _worker_condition:
        while _workers.get(key):_worker_condition.wait(.2)

def scheduler_tick(data):
    config=load_config(data)
    if not config['automatic']:return
    slot=due_slot(config)
    pending=[d for d in config['destinations'] if d['enabled'] and not completed_for(data,d['id'],slot)]
    if not pending:return
    try:
        with lease(lock_path(data,'job')):pass
    except Busy:return
    try:
        password=read_password((control(data)/'automatic.dpapi').read_bytes())
        request_job(data,None,'backup',password,uuid.uuid4(),daily_slot=slot)
    except (OSError,BackupError):
        atomic_json(control(data)/'scheduler-warning.json',{'at':now().isoformat(),'message':'Automatic backup credential is unavailable for this Windows user. Reconfigure it; backups have not succeeded.'})

def start_scheduler(data):
    stop=threading.Event()
    def worker():
        try:
            with lease(lock_path(data,'job')):
                for job in history(data):
                    if job['status'] in ('queued','running'):fail_job(data,job,'Interrupted before completion. No success recorded; retry the verified operation.')
        except (OSError,BackupError,Busy):pass
        while not stop.is_set():
            try:scheduler_tick(data)
            except (OSError,BackupError,Busy):pass
            stop.wait(60)
    thread=threading.Thread(target=worker,daemon=True,name='rumi-daily-backup');thread.start()
    return stop,thread
