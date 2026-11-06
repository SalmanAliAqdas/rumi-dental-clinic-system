from pathlib import Path
import uuid
from django.conf import settings
from django.core.paginator import Paginator
from django.http import FileResponse,Http404,JsonResponse
from django.shortcuts import render,redirect
from django.views.decorators.http import require_GET,require_http_methods
from .access import clinic_required
from .backup_forms import DestinationForm,AutomaticForm,BackupForm,VerifyForm,RestorePreviewForm
from .workflow_forms import RevisionForm
from .backups import jobs
from .backups.archive import BackupError,digest,no_links
from .backups.locks import Busy


def data_dir():return settings.DATA_DIR

def form_page(request,form,title,callback,**context):
    status=200
    if request.method=='POST' and form.is_valid():
        try:return callback(form.cleaned_data)
        except (BackupError,Busy) as exc:form.add_error(None,str(exc));status=400
        except OSError:form.add_error(None,'Local storage/path is unavailable or not writable. No alternate destination was substituted.');status=400
    elif request.method=='POST':status=400
    return render(request,'backups/form.html',dict(form=form,heading=title,**context),status=status)

@clinic_required(owner=True)
@require_GET
def centre(request):
    config=jobs.load_config(data_dir());destinations=[]
    for d in config['destinations']:
        row=dict(d)
        try:jobs.destination_folder(d['folder'],data_dir());row['available']=True
        except (OSError,BackupError):row['available']=False
        successes=[(j,r) for j in jobs.history(data_dir()) for r in j.get('results',[]) if r.get('destination_id')==d['id'] and r.get('status')=='verified' and j['kind']=='backup']
        row['last_success']=successes[0][1]['verified_at'] if successes else None
        last=successes[0][1] if successes else None
        try:
            path=no_links(Path(last['folder'])/last['filename']) if last else None
            row['last_available']=bool(path and path.is_file() and path.stat().st_size==last['size'])
        except (OSError,BackupError):row['last_available']=False
        row['overdue']=d['enabled'] and not jobs.completed_for(data_dir(),d['id'],jobs.due_slot(config)) if config['automatic'] else not bool(successes)
        destinations.append(row)
    warning=jobs.control(data_dir())/'scheduler-warning.json'
    return render(request,'backups/centre.html',dict(config=config,destinations=destinations,
        page=Paginator(jobs.history(data_dir()),20).get_page(request.GET.get('page')),scheduler_warning=jobs.read_json(warning) if warning.exists() else None))

@clinic_required(owner=True)
@require_http_methods(['GET','POST'])
def destination_new(request):
    config=jobs.load_config(data_dir());form=DestinationForm(request.POST or None,initial={'revision':config['revision']})
    def save(d):
        folder=jobs.destination_folder(d['folder'],data_dir())
        if d['kind']=='gdrive':jobs.google_staging(d['staging_folder'],folder,data_dir())
        destinations=config['destinations']+[dict(id=str(uuid.uuid4()),label=d['label'],kind=d['kind'],folder=str(folder),staging_folder=d['staging_folder'],enabled=True)]
        jobs.save_config(data_dir(),request.user.pk,{'destinations':destinations},d['revision'])
        return redirect('backup_centre')
    return form_page(request,form,'Add backup destination',save)

@clinic_required(owner=True)
@require_http_methods(['GET','POST'])
def destination_toggle(request,destination_id):
    config=jobs.load_config(data_dir());destination=next((d for d in config['destinations'] if d['id']==str(destination_id)),None)
    if not destination:raise Http404
    form=RevisionForm(request.POST or None,initial={'revision':config['revision']})
    def save(d):
        if not destination['enabled']:jobs.destination_folder(destination['folder'],data_dir())
        destination['enabled']=not destination['enabled']
        jobs.save_config(data_dir(),request.user.pk,{'destinations':config['destinations']},d['revision'])
        return redirect('backup_centre')
    return form_page(request,form,('Disable' if destination['enabled'] else 'Enable')+' destination: '+destination['label'],save)

@clinic_required(owner=True)
@require_http_methods(['GET','POST'])
def automatic_settings(request):
    config=jobs.load_config(data_dir());form=AutomaticForm(request.POST or None,initial=config)
    def save(d):
        jobs.configure_automatic(data_dir(),request.user.pk,d['revision'],d['automatic'],d['daily_time'].strftime('%H:%M'),d['keep_last'],d['recovery_password'])
        return redirect('backup_centre')
    return form_page(request,form,'Automatic backup settings',save)

@clinic_required(owner=True)
@require_http_methods(['GET','POST'])
def create(request,kind='backup',retry_id=None):
    previous=job_or_404(retry_id) if retry_id else None
    if previous and previous['kind'] not in ('backup','export'):raise Http404
    kind=previous['kind'] if previous else kind
    form=BackupForm(request.POST or None)
    def save(d):
        job=jobs.request_job(data_dir(),request.user.pk,kind,d['recovery_password'],d['token'],daily_slot=previous.get('daily_slot') if previous else None)
        return redirect('backup_job',job_id=job['id'])
    return form_page(request,form,'Back Up Now' if kind=='backup' else 'Encrypted portable migration export',save)

@clinic_required(owner=True)
@require_http_methods(['GET','POST'])
def verify(request,restore_preview=False):
    initial={'package':request.GET.get('package','')}
    form=(RestorePreviewForm if restore_preview else VerifyForm)(request.POST or None,initial=initial)
    def save(d):
        if restore_preview and not request.user.check_password(d['owner_password']):raise BackupError('Current Owner password is incorrect. No restore was authorized.')
        job=jobs.request_job(data_dir(),request.user.pk,'restore_preview' if restore_preview else 'verify',d['recovery_password'],d['token'],package=d['package'])
        return redirect('backup_job',job_id=job['id'])
    return form_page(request,form,'Re-authenticate and preview offline restore' if restore_preview else 'Verify encrypted package without replacing working data',save)


def job_or_404(identifier):
    try:return jobs.get_job(data_dir(),identifier)
    except (OSError,BackupError,ValueError):raise Http404 from None

@clinic_required(owner=True)
@require_GET
def job_detail(request,job_id):
    return render(request,'backups/job.html',{'job':job_or_404(job_id),'data_directory':str(data_dir())})

@clinic_required(owner=True)
@require_GET
def status(request,job_id):return JsonResponse(job_or_404(job_id))

@clinic_required(owner=True)
@require_GET
def download(request,job_id,destination_id):
    job=job_or_404(job_id)
    result=next((r for r in job['results'] if r.get('destination_id')==str(destination_id) and r.get('status')=='verified'),None)
    if not result:raise Http404
    try:
        name=result['filename']
        if Path(name).name!=name or Path(name).suffix not in ('.rumibak','.rumiexport'):raise BackupError('Invalid artifact.')
        path=no_links(Path(result['folder'])/name)
        if digest(path)!=result['sha256']:raise BackupError('Artifact changed.')
        response=FileResponse(path.open('rb'),as_attachment=True,filename=name,content_type='application/octet-stream')
        response['Content-Security-Policy']="default-src 'none'; sandbox"
        return response
    except (OSError,BackupError):raise Http404 from None
