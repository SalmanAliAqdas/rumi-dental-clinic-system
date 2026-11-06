"""Serialized, revision-safe Phase 4 mutations. No clinical text in logs."""
from contextlib import contextmanager
from datetime import timedelta
from uuid import UUID
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from .models import (WorkflowLock, Appointment, PersonalTask, WorkflowEvent, Prescription,
    PrescriptionCorrection, ClinicPrintSettings, PrescriberProfile, Visit)
from .workflow_models import ACTIVE, STATUSES
from .clinical_services import audit, ensure_medical_review
from .finance_services import PK, today, boundaries, clinician, owner

class Conflict(ValidationError):
    pass

class Overlap(ValidationError):
    pass

def is_prescriber(actor):
    return actor.is_active and actor.groups.filter(name='Doctor').exists() and actor.has_perm('clinic.add_visit')

def prescriber_required(actor):
    if not is_prescriber(actor): raise PermissionDenied

@contextmanager
def serialized():
    with transaction.atomic():
        if WorkflowLock.objects.filter(pk=1).update(revision=F('revision')+1) != 1:
            raise ValidationError('Complete workflow migrations before saving.')
        yield

def previous(actor, token, action, **scope):
    try: token=UUID(str(token))
    except (ValueError, TypeError, AttributeError): raise ValidationError('Invalid submission reference. Reload the form.')
    event=WorkflowEvent.objects.filter(token=token).first()
    if event and (event.actor_id != actor.pk or event.action != action or any(getattr(event,k)!=v for k,v in scope.items())):
        raise ValidationError('Submission reference belongs to another operation.')
    return event

def record(actor, token, action, reason='', before=None, after=None, **objects):
    event=WorkflowEvent.objects.create(actor=actor,token=token,action=action,reason=reason,
        before=before or {},after=after or {},**objects)
    if objects.get('patient'):
        audit(actor,objects['patient'],action,event)
    return event

def appointment_snapshot(a):
    return dict(patient_id=a.patient_id,starts_at=a.starts_at.isoformat(),ends_at=a.ends_at.isoformat(),
        purpose=a.purpose,notes=a.notes,status=a.status,arrived_at=a.arrived_at.isoformat() if a.arrived_at else None,
        queue_at=a.queue_at.isoformat() if a.queue_at else None,visit_id=a.visit_id,revision=a.revision,is_walk_in=a.is_walk_in)

def check_revision(obj, revision):
    if obj.revision != revision: raise Conflict('This record changed in another tab. Reload before saving; your submission has not overwritten it.')

def check_overlap(a, confirmed, reason):
    if a.status not in ACTIVE: return
    others=Appointment.objects.filter(status__in=ACTIVE,starts_at__lt=a.ends_at,ends_at__gt=a.starts_at).exclude(pk=a.pk)
    if others.exists() and (not confirmed or not reason.strip()):
        raise Overlap('This overlaps an active booking. Review the schedule, then explicitly confirm the overlap and give a reason to save intentionally.')

def save_appointment(actor, patient, data, token, appointment=None, revision=0, reason='', overlap_confirm=False, overlap_reason='', walk_in=False):
    clinician(actor)
    with serialized():
        action='appointment_update' if appointment else 'appointment_create'
        scope=dict(patient_id=patient.pk)
        if appointment: scope['appointment_id']=appointment.pk
        prior=previous(actor,token,action,**scope)
        if prior: return prior.appointment
        before={}
        if appointment:
            a=Appointment.objects.get(pk=appointment.pk,patient=patient)
            check_revision(a,revision)
            if not reason.strip(): raise ValidationError('Give a reason for appointment changes/rescheduling.')
            before=appointment_snapshot(a)
        else:
            a=Appointment(patient=patient,created_by=actor,updated_by=actor)
        for key in ('starts_at','ends_at','purpose','notes'): setattr(a,key,data[key])
        if not a.purpose.strip(): raise ValidationError('Enter the purpose.')
        if walk_in and not a.pk:
            a.is_walk_in=True
            a.arrived_at=data.get('arrived_at') or timezone.now()
            if a.arrived_at > timezone.now(): raise ValidationError('Walk-in arrival cannot be in the future.')
            a.queue_at=a.arrived_at
            a.status='arrived'
        a.full_clean()
        check_overlap(a,overlap_confirm,overlap_reason)
        a.revision+=1
        a.updated_by=actor; a.updated_at=timezone.now(); a.save()
        record(actor,token,action,reason=reason or 'New booking',before=before,
               after={**appointment_snapshot(a),'overlap_confirmed':overlap_confirm,'overlap_reason':overlap_reason},patient=patient,appointment=a)
        return a

def change_appointment(actor, appointment, revision, token, status, reason, queue_at=None, overlap_confirm=False, overlap_reason=''):
    clinician(actor)
    with serialized():
        a=Appointment.objects.get(pk=appointment.pk,patient_id=appointment.patient_id)
        prior=previous(actor,token,'appointment_status',appointment_id=a.pk,patient_id=a.patient_id)
        if prior: return a
        check_revision(a,revision)
        if status not in dict(STATUSES) or not reason.strip(): raise ValidationError('Choose a status and record a reason.')
        before=appointment_snapshot(a)
        if status=='in_treatment' and Appointment.objects.filter(status='in_treatment').exclude(pk=a.pk).exists():
            raise ValidationError('Another patient is In Treatment. Update that appointment first.')
        # No clock-driven status changes. Reopening a cancelled/no-show booking
        # requires fresh overlap confirmation through rescheduling first.
        if a.status not in ACTIVE and status in ACTIVE:
            old=a.status; a.status=status
            check_overlap(a,overlap_confirm,overlap_reason)
            a.status=old
        a.status=status
        if status in ('arrived','in_treatment') and (not a.arrived_at or before['status'] not in ('arrived','in_treatment')):
            a.arrived_at=timezone.now(); a.queue_at=a.arrived_at
        if queue_at:
            if status!='arrived' or queue_at > timezone.now(): raise ValidationError('Queue adjustment requires an arrived patient and a time no later than now.')
            a.queue_at=queue_at
        a.revision+=1; a.updated_by=actor; a.updated_at=timezone.now();a.save()
        record(actor,token,'appointment_status',reason,before,{**appointment_snapshot(a),'overlap_confirmed':overlap_confirm,'overlap_reason':overlap_reason},patient=a.patient,appointment=a)
        return a

def start_appointment_visit(actor, appointment, revision, token, reviewed, existing_visit=None):
    if not actor.is_active or not actor.has_perm('clinic.add_visit'): raise PermissionDenied
    with serialized():
        a=Appointment.objects.get(pk=appointment.pk,patient_id=appointment.patient_id)
        prior=previous(actor,token,'appointment_visit',appointment_id=a.pk,patient_id=a.patient_id)
        if prior: return prior.appointment.visit
        if a.visit_id: return a.visit  # New token or double-click still reuses the link.
        check_revision(a,revision)
        if a.status not in ('scheduled','arrived','in_treatment'): raise ValidationError('A cancelled, completed or no-show appointment cannot start a visit.')
        if Appointment.objects.filter(status='in_treatment').exclude(pk=a.pk).exists(): raise ValidationError('Another patient is In Treatment.')
        if not reviewed: raise ValidationError('Review the patient medical history and alerts first.')
        before=appointment_snapshot(a)
        if existing_visit:
            if existing_visit.patient_id != a.patient_id or Appointment.objects.filter(visit=existing_visit).exists():
                raise ValidationError('Choose an unlinked visit belonging to this patient.')
            if existing_visit.status=='completed': raise ValidationError('Link an editable visit; completed notes remain unchanged.')
            visit=existing_visit
        else:
            visit=Visit.objects.create(patient=a.patient,clinician=actor,created_by=actor,updated_by=actor,
                medical_review=ensure_medical_review(a.patient,actor,force=True))
            audit(actor,a.patient,'visit_create',visit)
        a.visit=visit; a.status='in_treatment'
        if not a.arrived_at or before['status'] not in ('arrived','in_treatment'): a.arrived_at=timezone.now();a.queue_at=a.arrived_at
        a.revision+=1;a.updated_by=actor;a.updated_at=timezone.now();a.save()
        record(actor,token,'appointment_visit','Explicit Start Visit',before,appointment_snapshot(a),patient=a.patient,appointment=a)
        return visit

def queue_context(actor, now=None):
    now=now or timezone.now();day=now.astimezone(PK).date();lo,hi=boundaries(day,day)
    active=Appointment.objects.filter(status__in=ACTIVE).select_related('patient','visit')
    current=active.filter(status='in_treatment').order_by('starts_at','pk').first()
    arrived=list(active.filter(status='arrived').order_by('queue_at','arrived_at','pk')[:20])
    upcoming=list(active.filter(status='scheduled',starts_at__gte=now,starts_at__lt=hi)[:20])
    overdue=list(active.filter(status='scheduled',starts_at__lt=now)[:20])
    remaining=list(active.filter(starts_at__lt=hi,ends_at__gt=lo).exclude(status='scheduled',starts_at__lt=now)[:20])
    tasks=PersonalTask.objects.filter(creator=actor,completed_at__isnull=True)
    return dict(business_day=day,current_appointment=current,next_appointment=arrived[0] if arrived else (upcoming[0] if upcoming else None),
        arrived_queue=arrived,remaining_appointments=remaining,overdue_appointments=overdue,personal_tasks=tasks[:12])

def task_snapshot(task):
    return dict(title=task.title,notes=task.notes,due_at=task.due_at.isoformat() if task.due_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,revision=task.revision)

def save_task(actor,data,token,task=None,revision=0,action='save'):
    clinician(actor)
    with serialized():
        task=PersonalTask.objects.get(pk=task.pk,creator=actor) if task else None
        kind='task_'+action
        scope={'task_id':task.pk} if task else {}
        prior=previous(actor,token,kind,**scope)
        if prior: return prior.task
        before={}
        if task:
            check_revision(task,revision);before=task_snapshot(task)
        else: task=PersonalTask(creator=actor)
        if action=='save':
            for key in ('title','notes','due_at'):setattr(task,key,data[key])
        elif action=='complete':task.completed_at=timezone.now()
        elif action=='reopen':task.completed_at=None
        else:raise ValidationError('Invalid task action.')
        task.revision+=1;task.updated_at=timezone.now();task.full_clean();task.save()
        record(actor,token,kind,before=before,after=task_snapshot(task),task=task)
        return task

def clinic_details():
    obj=ClinicPrintSettings.objects.filter(pk=1).first()
    return dict(name=obj.name if obj else 'Rumi Dental Care',address=obj.address if obj else '',contact=obj.contact if obj else '')

def rx_content(rx):
    return dict(prescribed_on=rx.prescribed_on.isoformat(),visit_id=rx.visit_id,medications=rx.medications,advice=rx.advice,follow_up=rx.follow_up)

def save_prescription(actor,patient,data,token,rx=None,revision=0):
    prescriber_required(actor)
    with serialized():
        scope=dict(patient_id=patient.pk)
        if rx:scope['prescription_id']=rx.pk
        prior=previous(actor,token,'prescription_save',**scope)
        if prior:return prior.prescription
        before={}
        if rx:
            rx=Prescription.objects.get(pk=rx.pk,patient=patient,prescriber=actor)
            check_revision(rx,revision)
            if rx.issued_at:raise ValidationError('Issued content cannot be overwritten. Use replacement/void.')
            before=rx_content(rx)
        else:rx=Prescription(patient=patient,prescriber=actor)
        for key in ('prescribed_on','visit','medications','advice','follow_up'):setattr(rx,key,data[key])
        if rx.prescribed_on>today():raise ValidationError('Prescription date cannot be in the future.')
        rx.revision+=1;rx.updated_at=timezone.now();rx.full_clean();rx.save()
        record(actor,token,'prescription_save',before=before,after=rx_content(rx),patient=patient,prescription=rx)
        return rx

def issue_prescription(actor,rx,revision,token,confirmed):
    prescriber_required(actor)
    with serialized():
        rx=Prescription.objects.select_related('patient').get(pk=rx.pk,prescriber=actor)
        prior=previous(actor,token,'prescription_issue',prescription_id=rx.pk,patient_id=rx.patient_id)
        if prior:return rx
        check_revision(rx,revision)
        if rx.issued_at:raise ValidationError('Prescription already issued.')
        if not confirmed:raise ValidationError('Explicitly confirm review and issuance.')
        profile=PrescriberProfile.objects.filter(user=actor).first()
        if not profile or not profile.display_name.strip():raise ValidationError('Complete your own clinician print details before issuing.')
        required=('name','dose','route','frequency','duration')
        if not rx.medications or any(not all(str(m.get(k,'')).strip() for k in required) for m in rx.medications):
            raise ValidationError('Complete medication name, dose, route, frequency and duration for every row before issuing. No values are generated.')
        rx.snapshot={**rx_content(rx),'clinic':clinic_details(),'patient':dict(name=rx.patient.full_name,number=rx.patient.number,age=rx.patient.age_display),
            'clinician':dict(user_id=actor.pk,name=profile.display_name,qualifications=profile.qualifications,registration=profile.registration,contact=profile.contact)}
        rx.issued_at=timezone.now();rx.revision+=1;rx.updated_at=timezone.now();rx.save()
        record(actor,token,'prescription_issue','Doctor reviewed and issued',after=rx.snapshot,patient=rx.patient,prescription=rx)
        return rx

def correct_prescription(actor,rx,token,reason,replace=False):
    prescriber_required(actor)
    with serialized():
        rx=Prescription.objects.select_related('patient').get(pk=rx.pk)
        prior=previous(actor,token,'prescription_correct',prescription_id=rx.pk,patient_id=rx.patient_id)
        if prior:return rx.correction.replacement
        if not rx.issued_at or PrescriptionCorrection.objects.filter(original=rx).exists() or not reason.strip():
            raise ValidationError('Choose an issued, uncorrected prescription and give a reason.')
        replacement=None
        if replace:
            replacement=Prescription.objects.create(patient=rx.patient,visit=rx.visit,prescriber=actor,
                prescribed_on=today(),medications=rx.medications,advice=rx.advice,follow_up=rx.follow_up)
        correction=PrescriptionCorrection.objects.create(original=rx,replacement=replacement,reason=reason,actor=actor)
        record(actor,token,'prescription_correct',reason,after={'replacement_id':replacement.pk if replacement else None},patient=rx.patient,prescription=rx)
        audit(actor,rx.patient,'prescription_void',correction)
        return replacement

def save_print_settings(actor,data,token,revision,personal=False):
    if personal:prescriber_required(actor)
    else:owner(actor)
    with serialized():
        action='prescriber_settings' if personal else 'clinic_print_settings'
        prior=previous(actor,token,action)
        if prior:return
        if personal:
            obj=PrescriberProfile.objects.filter(user=actor).first() or PrescriberProfile(user=actor)
        else:obj=ClinicPrintSettings.objects.filter(pk=1).first() or ClinicPrintSettings(pk=1)
        check_revision(obj,revision)
        fields=('display_name','qualifications','registration','contact') if personal else ('name','address','contact')
        before={k:getattr(obj,k) for k in fields}
        for k in fields:setattr(obj,k,data[k])
        obj.revision+=1;obj.full_clean();obj.save()
        record(actor,token,action,before=before,after={k:getattr(obj,k) for k in fields})


def reminder_details(appointment,confirmed_fallback=False):
    from urllib.parse import urlencode
    from .phones import normalize_phone
    patient=appointment.patient
    text=f"Appointment reminder from {clinic_details()['name']}: {appointment.starts_at.astimezone(PK):%d %b %Y at %H:%M} (Pakistan time). Please contact the clinic if you need to reschedule."
    raw=patient.whatsapp or (patient.phone if confirmed_fallback else '')
    number=normalize_phone(raw) if raw else ''
    url='https://wa.me/'+number.lstrip('+')+'?'+urlencode({'text':text}) if number else ''
    return dict(reminder_text=text,reminder_number=number,whatsapp_url=url,needs_fallback=not bool(patient.whatsapp))

def confirm_reminder(actor,appointment,token,activity,confirmed_fallback):
    clinician(actor)
    with serialized():
        a=Appointment.objects.select_related('patient').get(pk=appointment.pk)
        prior=previous(actor,token,'reminder_activity',appointment_id=a.pk,patient_id=a.patient_id)
        if prior:return prior.after
        details=reminder_details(a,confirmed_fallback)
        if activity not in ('copied','sent'):raise ValidationError('Choose a user-confirmed activity.')
        if not details['reminder_number']:raise ValidationError('Confirm the primary-phone fallback before recording reminder activity.')
        record(actor,token,'reminder_activity',after={'activity':activity,'number':details['reminder_number'],'appointment_time':a.starts_at.isoformat()},patient=a.patient,appointment=a)
        return details
