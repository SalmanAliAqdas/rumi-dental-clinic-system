"""Phase 4 scheduling, personal work and prescription records."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, F
from django.utils import timezone
from .finance_models import Posted

STATUSES = [('scheduled','Scheduled'),('arrived','Arrived'),('in_treatment','In Treatment'),
            ('completed','Completed'),('cancelled','Cancelled'),('no_show','No-show')]
ACTIVE = ['scheduled','arrived','in_treatment']

class WorkflowLock(models.Model):
    revision = models.PositiveBigIntegerField(default=0)

class Appointment(models.Model):
    patient = models.ForeignKey('Patient', on_delete=models.PROTECT, related_name='appointments')
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()
    purpose = models.CharField(max_length=240)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default='scheduled', db_index=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    queue_at = models.DateTimeField(null=True, blank=True)
    is_walk_in = models.BooleanField(default=False)
    visit = models.OneToOneField('Visit', on_delete=models.PROTECT, null=True, blank=True, related_name='appointment')
    revision = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ['starts_at','pk']
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=F('starts_at')), name='appointment_valid_times')]
    def clean(self):
        if self.ends_at <= self.starts_at:
            raise ValidationError('End must be after start.')
        if self.visit_id and self.visit.patient_id != self.patient_id:
            raise ValidationError('Linked visit must belong to this patient.')
    def delete(self, *args, **kwargs):
        raise ValidationError('Appointment history must be retained.')
    @property
    def overdue(self):
        return self.status == 'scheduled' and self.starts_at < timezone.now()

class PersonalTask(models.Model):
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='personal_tasks')
    title = models.CharField(max_length=160)
    notes = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = [F('due_at').asc(nulls_last=True),'pk']
    @property
    def status(self):
        if self.completed_at: return 'Completed'
        if self.due_at and self.due_at < timezone.now(): return 'Overdue'
        from .finance_services import PK, today
        if self.due_at and self.due_at.astimezone(PK).date() == today(): return 'Due today'
        return 'Pending'

class ClinicPrintSettings(models.Model):
    name = models.CharField(max_length=160, default='Rumi Dental Care')
    address = models.CharField(max_length=240, blank=True)
    contact = models.CharField(max_length=160, blank=True)
    revision = models.PositiveIntegerField(default=0)

class PrescriberProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='prescriber_profile')
    display_name = models.CharField(max_length=160)
    qualifications = models.CharField(max_length=240, blank=True)
    registration = models.CharField(max_length=160, blank=True)
    contact = models.CharField(max_length=160, blank=True)
    revision = models.PositiveIntegerField(default=0)

class Prescription(models.Model):
    patient = models.ForeignKey('Patient', on_delete=models.PROTECT, related_name='prescriptions')
    visit = models.ForeignKey('Visit', on_delete=models.PROTECT, null=True, blank=True, related_name='prescriptions')
    prescriber = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='prescriptions')
    prescribed_on = models.DateField(default=timezone.localdate)
    medications = models.JSONField(default=list)
    advice = models.TextField(blank=True)
    follow_up = models.CharField(max_length=240, blank=True)
    revision = models.PositiveIntegerField(default=0)
    issued_at = models.DateTimeField(null=True, blank=True)
    snapshot = models.JSONField(default=dict, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ['-created_at','-pk']
    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, issued_at__isnull=False).exists():
            raise ValidationError('Issued prescriptions are immutable; create a reasoned replacement/void.')
        super().save(*args, **kwargs)
    def delete(self, *args, **kwargs):
        raise ValidationError('Prescription history must be retained.')
    def clean(self):
        if self.visit_id and self.visit.patient_id != self.patient_id:
            raise ValidationError('Visit must belong to this patient.')
    @property
    def state(self):
        if not self.issued_at: return 'Draft'
        return 'Voided / replaced' if PrescriptionCorrection.objects.filter(original=self).exists() else 'Issued'

class PrescriptionCorrection(Posted):
    original = models.OneToOneField(Prescription, on_delete=models.PROTECT, related_name='correction')
    replacement = models.OneToOneField(Prescription, on_delete=models.PROTECT, null=True, blank=True, related_name='replaces')
    reason = models.CharField(max_length=240)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)

class WorkflowEvent(Posted):
    token = models.UUIDField(unique=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=32)
    patient = models.ForeignKey('Patient', on_delete=models.PROTECT, null=True, blank=True)
    appointment = models.ForeignKey(Appointment, on_delete=models.PROTECT, null=True, blank=True, related_name='history')
    task = models.ForeignKey(PersonalTask, on_delete=models.PROTECT, null=True, blank=True, related_name='history')
    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT, null=True, blank=True, related_name='history')
    reason = models.CharField(max_length=240, blank=True)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ['created_at','pk']
