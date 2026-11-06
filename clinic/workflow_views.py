from datetime import date, timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import OperationalError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from django.utils import timezone
from .access import clinic_required
from .models import (Patient, Appointment, PersonalTask, Prescription, PrescriptionCorrection,
    PrescriberProfile, ClinicPrintSettings)
from . import workflow_services as s
from .workflow_forms import (AppointmentForm, StatusForm, StartVisitForm, TaskForm, RevisionForm,
    PrescriptionForm, MedicationFormSet, ConfirmForm, CorrectionForm, ClinicSettingsForm, PrescriberForm, ReminderForm)


def page_form(request,form,heading,save,patient=None,**context):
    status=200
    if request.method=='POST' and form.is_valid():
        try:return save(form.cleaned_data)
        except (s.Conflict,s.Overlap) as exc:
            form.add_error(None,exc);status=409
        except ValidationError as exc:
            form.add_error(None,exc);status=400
        except OperationalError:
            form.add_error(None,'Database busy. Retry this same submission; its reference prevents duplicate changes.');status=409
    elif request.method=='POST':status=400
    return render(request,'workflow/form.html',dict(form=form,heading=heading,patient=patient,**context),status=status)


def appointment_for(pk,appointment_id):
    patient=get_object_or_404(Patient,pk=pk)
    return patient,get_object_or_404(Appointment.objects.select_related('patient','visit'),pk=appointment_id,patient=patient)

@clinic_required()
@require_GET
def schedule(request,pk=None):
    patient=get_object_or_404(Patient,pk=pk) if pk else None
    try:
        day=date.fromisoformat(request.GET.get('date',s.today().isoformat()))
        if day in (date.min,date.max):raise ValueError
        lo,hi=s.boundaries(day,day)
    except (ValueError,OverflowError):return HttpResponse('Choose a valid date.',status=400)
    query=Appointment.objects.select_related('patient','visit')
    if patient:query=query.filter(patient=patient)
    mode='history' if patient else request.GET.get('view','day')
    if mode=='day':query=query.filter(starts_at__lt=hi,ends_at__gt=lo)
    elif mode=='upcoming':query=query.filter(starts_at__gte=timezone.now())
    elif mode!='history' or not patient:return HttpResponse('Invalid schedule view.',status=400)
    return render(request,'workflow/schedule.html',dict(patient=patient,page=Paginator(query,20).get_page(request.GET.get('page')),day=day,
        previous_day=day-timedelta(days=1),next_day=day+timedelta(days=1),mode=mode))

@clinic_required()
@require_http_methods(['GET','POST'])
def appointment_edit(request,pk,appointment_id=None):
    patient=get_object_or_404(Patient,pk=pk)
    a=get_object_or_404(Appointment,pk=appointment_id,patient=patient) if appointment_id else None
    walk_in=request.GET.get('walkin')=='1' if not a else a.is_walk_in
    now=timezone.localtime().replace(second=0,microsecond=0)
    initial={k:getattr(a,k) for k in ('starts_at','ends_at','purpose','notes','revision','arrived_at')} if a else dict(starts_at=now,ends_at=now+timedelta(minutes=30),revision=0)
    form=AppointmentForm(request.POST or None,initial=initial)
    if a or not walk_in:form.fields.pop('arrived_at')
    def save(data):
        values={k:data[k] for k in ('starts_at','ends_at','purpose','notes')}
        values['arrived_at']=data.get('arrived_at')
        result=s.save_appointment(request.user,patient,values,data['token'],appointment=a,revision=data['revision'],reason=data['reason'],
            overlap_confirm=data['overlap_confirm'],overlap_reason=data['overlap_reason'],walk_in=walk_in)
        return redirect('appointment_detail',pk=pk,appointment_id=result.pk)
    return page_form(request,form,'Reschedule / edit appointment' if a else 'Register walk-in' if walk_in else 'Book appointment',save,patient,appointment=a)

@clinic_required()
@require_GET
def appointment_detail(request,pk,appointment_id):
    patient,a=appointment_for(pk,appointment_id)
    s.audit(request.user,patient,'appointment_view',a)
    return render(request,'workflow/appointment.html',dict(patient=patient,appointment=a,history=a.history.select_related('actor')))

@clinic_required()
@require_http_methods(['GET','POST'])
def appointment_status(request,pk,appointment_id):
    patient,a=appointment_for(pk,appointment_id)
    initial=dict(revision=a.revision,status=request.GET.get('status',a.status))
    form=StatusForm(request.POST or None,initial=initial)
    def save(data):
        s.change_appointment(request.user,a,**data)
        return redirect('appointment_detail',pk=pk,appointment_id=a.pk)
    return page_form(request,form,'Change appointment status / queue order',save,patient,appointment=a)

@clinic_required('add_visit')
@require_http_methods(['GET','POST'])
def appointment_visit(request,pk,appointment_id):
    patient,a=appointment_for(pk,appointment_id)
    form=StartVisitForm(request.POST or None,patient=patient,initial={'revision':a.revision})
    def save(data):
        visit=s.start_appointment_visit(request.user,a,**data)
        return redirect('visit_detail',pk=pk,visit_id=visit.pk)
    return page_form(request,form,'Start Visit from appointment',save,patient,appointment=a)

@clinic_required()
@require_GET
def daily_panel(request):
    response=render(request,'workflow/panels.html',s.queue_context(request.user))
    response['X-Rumi-Panel']='1'
    return response

@clinic_required()
@require_GET
def tasks(request):
    completed=request.GET.get('view')=='completed'
    query=PersonalTask.objects.filter(creator=request.user,completed_at__isnull=not completed)
    return render(request,'workflow/tasks.html',dict(page=Paginator(query,20).get_page(request.GET.get('page')),completed=completed))

@clinic_required()
@require_http_methods(['GET','POST'])
def task_edit(request,task_id=None,action='save'):
    task=get_object_or_404(PersonalTask,pk=task_id,creator=request.user) if task_id else None
    if action not in ('save','complete','reopen') or (not task and action!='save'):return HttpResponse(status=404)
    initial={k:getattr(task,k) for k in ('title','notes','due_at','revision')} if task else {'revision':0}
    form=(TaskForm if action=='save' else RevisionForm)(request.POST or None,initial=initial)
    def save(data):
        s.save_task(request.user,{k:data[k] for k in ('title','notes','due_at')} if action=='save' else {},data['token'],task,data['revision'],action)
        return redirect('personal_tasks')
    return page_form(request,form,'Personal task: '+action,save,task=task,task_history=task.history.all() if task else [])


def rx_for(pk,rx_id):
    patient=get_object_or_404(Patient,pk=pk)
    return patient,get_object_or_404(Prescription.objects.select_related('prescriber','visit','patient'),pk=rx_id,patient=patient)

@clinic_required()
@require_GET
def prescriptions(request,pk):
    patient=get_object_or_404(Patient,pk=pk)
    return render(request,'workflow/prescriptions.html',dict(patient=patient,page=Paginator(patient.prescriptions.select_related('prescriber'),20).get_page(request.GET.get('page')),can_prescribe=s.is_prescriber(request.user)))

@clinic_required()
@require_http_methods(['GET','POST'])
def prescription_edit(request,pk,rx_id=None):
    s.prescriber_required(request.user)
    patient=get_object_or_404(Patient,pk=pk)
    rx=get_object_or_404(Prescription,pk=rx_id,patient=patient,prescriber=request.user) if rx_id else None
    if rx and rx.issued_at:raise PermissionDenied
    initial={k:getattr(rx,k) for k in ('prescribed_on','visit','advice','follow_up','revision')} if rx else {'revision':0}
    if not rx and request.GET.get('visit'):
        initial['visit']=get_object_or_404(patient.visits,pk=request.GET['visit'])
    form=PrescriptionForm(request.POST or None,patient=patient,initial=initial)
    medications=MedicationFormSet(request.POST or None,initial=rx.medications if rx else [],prefix='meds')
    if request.method=='POST' and not medications.is_valid():
        form.is_valid();form.add_error(None,'Review the medication rows below.')
    def save(data):
        content={k:data[k] for k in ('prescribed_on','visit','advice','follow_up')}
        content['medications']=[{k:v for k,v in row.items() if k!='DELETE'} for row in medications.cleaned_data if row and not row.get('DELETE') and row.get('name')]
        saved=s.save_prescription(request.user,patient,content,data['token'],rx,data['revision'])
        return redirect('prescription_detail',pk=pk,rx_id=saved.pk)
    return page_form(request,form,'Prescription draft (Doctor-entered content)',save,patient,rx=rx,medications=medications)

@clinic_required()
@require_GET
def prescription_detail(request,pk,rx_id):
    patient,rx=rx_for(pk,rx_id)
    s.audit(request.user,patient,'prescription_view',rx)
    doctor=s.is_prescriber(request.user)
    return render(request,'workflow/prescription.html',dict(patient=patient,rx=rx,can_edit=doctor and rx.prescriber_id==request.user.pk and not rx.issued_at,
        can_correct=doctor and rx.issued_at and not PrescriptionCorrection.objects.filter(original=rx).exists(),history=rx.history.select_related('actor')))

@clinic_required()
@require_http_methods(['GET','POST'])
def prescription_issue(request,pk,rx_id):
    s.prescriber_required(request.user)
    patient,rx=rx_for(pk,rx_id)
    if rx.prescriber_id!=request.user.pk:raise PermissionDenied
    form=ConfirmForm(request.POST or None,initial={'revision':rx.revision})
    def save(data):
        s.issue_prescription(request.user,rx,**data)
        return redirect('prescription_detail',pk=pk,rx_id=rx.pk)
    return page_form(request,form,'Review and issue prescription',save,patient,rx=rx,issuing=True)

@clinic_required()
@require_http_methods(['GET','POST'])
def prescription_correct(request,pk,rx_id):
    s.prescriber_required(request.user)
    patient,rx=rx_for(pk,rx_id)
    form=CorrectionForm(request.POST or None)
    def save(data):
        replacement=s.correct_prescription(request.user,rx,data['token'],data['reason'],data['action']=='replace')
        return redirect('prescription_edit',pk=pk,rx_id=replacement.pk) if replacement else redirect('prescription_detail',pk=pk,rx_id=rx.pk)
    return page_form(request,form,'Void / replace issued prescription',save,patient,rx=rx)

@clinic_required()
@require_GET
def prescription_print(request,pk,rx_id):
    patient,rx=rx_for(pk,rx_id)
    data=rx.snapshot if rx.issued_at else {**s.rx_content(rx),'clinic':s.clinic_details(),
        'patient':dict(name=patient.full_name,number=patient.number,age=patient.age_display),
        'clinician':dict(name=rx.prescriber.get_full_name() or rx.prescriber.username)}
    s.audit(request.user,patient,'prescription_print',rx)
    return render(request,'workflow/document.html',dict(document=data,rx=rx))

@clinic_required()
@require_GET
def appointment_print(request,pk,appointment_id):
    patient,a=appointment_for(pk,appointment_id)
    s.audit(request.user,patient,'appointment_print',a)
    return render(request,'workflow/document.html',dict(document={'clinic':s.clinic_details(),'patient':dict(name=patient.full_name,number=patient.number)},appointment=a))

@clinic_required()
@require_http_methods(['GET','POST'])
def print_settings(request,personal=False):
    if personal:s.prescriber_required(request.user)
    elif not request.user.is_superuser:raise PermissionDenied
    obj=PrescriberProfile.objects.filter(user=request.user).first() if personal else ClinicPrintSettings.objects.filter(pk=1).first()
    fields=('display_name','qualifications','registration','contact','revision') if personal else ('name','address','contact','revision')
    initial={k:getattr(obj,k) for k in fields} if obj else {'revision':0,'name':'Rumi Dental Care'}
    form=(PrescriberForm if personal else ClinicSettingsForm)(request.POST or None,initial=initial)
    def save(data):
        s.save_print_settings(request.user,{k:v for k,v in data.items() if k not in ('token','revision')},data['token'],data['revision'],personal)
        return redirect('dashboard')
    return page_form(request,form,'Your clinician print details' if personal else 'Clinic print details',save)

@clinic_required()
@require_http_methods(['GET','POST'])
def reminder(request,pk,appointment_id):
    patient,a=appointment_for(pk,appointment_id)
    form=ReminderForm(request.POST or None)
    details={};status=200
    try:
        fallback=False
        if request.method=='POST' and form.is_valid():
            fallback=form.cleaned_data['confirmed_fallback']
            if form.cleaned_data['activity']!='prepare':
                s.confirm_reminder(request.user,a,form.cleaned_data['token'],form.cleaned_data['activity'],fallback)
                return redirect('appointment_detail',pk=pk,appointment_id=a.pk)
        elif request.method=='POST':status=400
        details=s.reminder_details(a,fallback)
    except ValidationError as exc:form.add_error(None,exc);status=400
    except OperationalError:form.add_error(None,'Database busy; retry the same submission.');status=409
    return render(request,'workflow/reminder.html',dict(patient=patient,appointment=a,form=form,**details),status=status)
