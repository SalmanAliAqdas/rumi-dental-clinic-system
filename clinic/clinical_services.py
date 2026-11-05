from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone
from .clinical_forms import MEDICAL_FIELDS
from .models import AuditEvent, MedicalReview, Visit, PlanRevision

def audit(actor, patient, action, obj=None):
    AuditEvent.objects.create(actor=actor, patient=patient, action=action,
        object_type=type(obj).__name__ if obj else '', object_id=obj.pk if obj else None)


def current_medical(patient):
    result = {}
    for key in MEDICAL_FIELDS:
        text = getattr(patient, key).strip()
        state = 'not_recorded' if not text else ('none' if text.casefold() in ['none', 'none confirmed', 'patient reports none'] else 'details')
        result[key] = {'state': state, 'details': text if state == 'details' else ''}
    return result


def ensure_medical_review(patient, actor, reason='Medical status reviewed at visit start', force=False):
    snapshot = current_medical(patient)
    latest = patient.medical_reviews.first()
    if not force and latest and latest.snapshot == snapshot:
        return latest
    review = MedicalReview.objects.create(patient=patient, snapshot=snapshot, reason=reason, reviewed_by=actor)
    audit(actor, patient, 'medical_review', review)
    return review


def update_medical(patient, actor, snapshot, reason):
    with transaction.atomic():
        ensure_medical_review(patient, actor, 'Previous medical status retained before change')
        for key in MEDICAL_FIELDS:
            state = snapshot[key]['state']
            setattr(patient, key, snapshot[key]['details'] if state == 'details' else ('Patient reports none' if state == 'none' else ''))
        patient.updated_by = actor
        patient.save()
        review = MedicalReview.objects.create(patient=patient, snapshot=snapshot, reason=reason, reviewed_by=actor)
        audit(actor, patient, 'medical_review', review)
        return review


class StaleRevision(Exception):
    pass


def save_visit(visit, form, actor, complete=False):
    with transaction.atomic():
        # A conditional update is atomic on SQLite and PostgreSQL; no lost saves.
        values = {key: form.cleaned_data[key] for key in form.Meta.fields}
        values.pop('clinician')
        values['clinician_id'] = form.cleaned_data['clinician'].pk
        if complete:
            if not values['chief_complaint'].strip() or not values['performed_treatment'].strip():
                raise ValidationError('Record the chief complaint and treatment performed (or explicitly state none performed) before completion.')
            values.update(status='completed', completed_at=timezone.now())
        revision = form.cleaned_data['revision']
        values.update(revision=revision + 1, updated_at=timezone.now(), updated_by_id=actor.pk)
        changed = Visit.objects.filter(pk=visit.pk, patient_id=visit.patient_id, revision=revision).exclude(status='completed').update(**values)
        if not changed:
            raise StaleRevision
        visit.refresh_from_db()
        audit(actor, visit.patient, 'visit_complete' if complete else 'visit_update', visit)
        return visit


def plan_snapshot(plan, actor):
    value = {'title': plan.title, 'notes': plan.notes, 'revision': plan.revision,
             'items': list(plan.items.order_by('pk').values('id', 'procedure_id', 'teeth', 'area', 'notes', 'status', 'revision'))}
    for item, stored in zip(plan.items.order_by('pk'), value['items']):
        stored['target_date'] = item.target_date.isoformat() if item.target_date else None
    PlanRevision.objects.create(plan=plan, snapshot=value, author=actor)
