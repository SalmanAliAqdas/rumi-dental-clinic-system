from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from .models import Patient
from .teeth import validate_teeth

USER = settings.AUTH_USER_MODEL
STAGES = [('planned', 'Planned'), ('in_progress', 'In Progress'), ('completed', 'Completed'), ('cancelled', 'Cancelled')]

class ImmutableRecord(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('This dated clinical record is immutable; add a new record or amendment.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Clinical records cannot be routinely deleted.')


class MedicalReview(ImmutableRecord):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='medical_reviews')
    snapshot = models.JSONField()
    reason = models.CharField(max_length=240)
    reviewed_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-reviewed_at', '-pk']


class Visit(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='visits')
    visit_at = models.DateTimeField(default=timezone.now)
    clinician = models.ForeignKey(USER, on_delete=models.PROTECT, related_name='clinical_visits')
    medical_review = models.ForeignKey(MedicalReview, on_delete=models.PROTECT)
    chief_complaint = models.TextField(blank=True)
    examination = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    teeth = models.JSONField(default=list, validators=[validate_teeth], blank=True)
    area = models.CharField(max_length=200, blank=True)
    planned_treatment = models.TextField(blank=True)
    performed_treatment = models.TextField(blank=True)
    advice = models.TextField(blank=True)
    remaining_work = models.TextField(blank=True)
    follow_up = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=[('draft', 'Draft'), ('in_progress', 'In Progress'), ('completed', 'Completed')], default='in_progress')
    revision = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name='visits_created')
    updated_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name='visits_updated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-visit_at', '-pk']

    def clean(self):
        if self.medical_review_id and self.medical_review.patient_id != self.patient_id:
            raise ValidationError('Medical review must belong to this patient.')

    def save(self, *args, **kwargs):
        if self.pk and Visit.objects.filter(pk=self.pk, status='completed').exists():
            raise ValidationError('Completed visits require an amendment; originals cannot be overwritten.')
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Visit {self.pk} · {timezone.localtime(self.visit_at):%d %b %Y %H:%M}'


class VisitAmendment(ImmutableRecord):
    visit = models.ForeignKey(Visit, on_delete=models.PROTECT, related_name='amendments')
    reason = models.CharField(max_length=240)
    content = models.TextField()
    author = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at', 'pk']


class Procedure(models.Model):
    name = models.CharField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    is_example = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name + (' (example)' if self.is_example else '')


class TreatmentPlan(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='treatment_plans')
    title = models.CharField(max_length=160)
    notes = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']


class PlanItem(models.Model):
    plan = models.ForeignKey(TreatmentPlan, on_delete=models.PROTECT, related_name='items')
    procedure = models.ForeignKey(Procedure, on_delete=models.PROTECT)
    teeth = models.JSONField(default=list, blank=True, validators=[validate_teeth])
    area = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STAGES, default='planned')
    target_date = models.DateField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f'{self.plan.title} · {self.procedure} · {self.get_status_display()}'


class PlanRevision(ImmutableRecord):
    plan = models.ForeignKey(TreatmentPlan, on_delete=models.PROTECT, related_name='history')
    snapshot = models.JSONField()
    author = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)


class PerformedWork(ImmutableRecord):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    visit = models.ForeignKey(Visit, on_delete=models.PROTECT, related_name='work')
    procedure = models.ForeignKey(Procedure, on_delete=models.PROTECT)
    procedure_label = models.CharField(max_length=200, editable=False)
    plan_item = models.ForeignKey(PlanItem, on_delete=models.PROTECT, related_name='work', null=True, blank=True)
    teeth = models.JSONField(default=list, blank=True, validators=[validate_teeth])
    area = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    performed_at = models.DateTimeField(default=timezone.now)
    author = models.ForeignKey(USER, on_delete=models.PROTECT)

    class Meta:
        ordering = ['-performed_at', '-pk']

    def clean(self):
        if self.visit_id and (self.visit.patient_id != self.patient_id or self.visit.status == 'completed'):
            raise ValidationError('Work must belong to an editable visit for this patient.')
        if self.plan_item_id and (self.plan_item.plan.patient_id != self.patient_id or self.plan_item.procedure_id != self.procedure_id):
            raise ValidationError('Plan item must belong to this patient and match the procedure.')


class ToothObservation(ImmutableRecord):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='observations')
    visit = models.ForeignKey(Visit, on_delete=models.PROTECT, null=True, blank=True)
    teeth = models.JSONField(default=list, blank=True, validators=[validate_teeth])
    area = models.CharField(max_length=200, blank=True)
    observation = models.TextField()
    observed_at = models.DateTimeField(default=timezone.now)
    author = models.ForeignKey(USER, on_delete=models.PROTECT)

    class Meta:
        ordering = ['-observed_at', '-pk']

    def clean(self):
        if self.visit_id and (self.visit.patient_id != self.patient_id or self.visit.status == 'completed'):
            raise ValidationError('Chart observation must use an editable visit for this patient.')


class Attachment(ImmutableRecord):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='attachments')
    visit = models.ForeignKey(Visit, on_delete=models.PROTECT, related_name='attachments', null=True, blank=True)
    teeth = models.JSONField(default=list, blank=True, validators=[validate_teeth])
    area = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=16, choices=[('xray', 'X-ray'), ('photo', 'Clinical photograph'), ('document', 'Document')])
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    taken_on = models.DateField(null=True, blank=True)
    uploaded_at = models.DateTimeField(default=timezone.now)
    uploader = models.ForeignKey(USER, on_delete=models.PROTECT)
    storage_name = models.CharField(max_length=80, editable=False)
    thumbnail_name = models.CharField(max_length=80, blank=True, editable=False)
    content_type = models.CharField(max_length=32, editable=False)
    size = models.PositiveIntegerField(editable=False)

    class Meta:
        ordering = ['-uploaded_at', '-pk']

    def clean(self):
        if self.visit_id and self.visit.patient_id != self.patient_id:
            raise ValidationError('Attachment visit must belong to this patient.')
