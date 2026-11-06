import uuid
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from .phones import normalize_phone

def patient_number():
    return 'RDC-' + uuid.uuid4().hex[:12].upper()

class Patient(models.Model):
    number = models.CharField(max_length=16, unique=True, default=patient_number, editable=False)
    full_name = models.CharField(max_length=160, db_index=True)
    phone = models.CharField(max_length=16, db_index=True)
    whatsapp = models.CharField(max_length=16, blank=True, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    approximate_age = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(120)])
    age_recorded_on = models.DateField(null=True, blank=True, editable=False)
    address = models.TextField(blank=True)
    occupation = models.CharField(max_length=160, blank=True)
    emergency_contact = models.CharField(max_length=240, blank=True)
    medical_history = models.TextField(blank=True, help_text='Leave blank if not recorded. Enter “None confirmed” only after checking.')
    current_medicines = models.TextField(blank=True, help_text='Blank means not recorded; use “None confirmed” when confirmed.')
    allergies = models.TextField(blank=True, help_text='Blank means not recorded; use “None confirmed” when confirmed.')
    medical_alerts = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='patients_created')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='patients_updated')

    class Meta:
        ordering = ['full_name', 'pk']

    def save(self, *args, **kwargs):
        self.phone = normalize_phone(self.phone)
        self.whatsapp = normalize_phone(self.whatsapp) if self.whatsapp else ''
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(number=self.number).exists():
            raise ValueError('Patient number is permanent.')
        super().save(*args, **kwargs)

    @property
    def age_display(self):
        if self.date_of_birth:
            return f'Born {self.date_of_birth:%d %b %Y}'
        if self.approximate_age is not None:
            return f'About {self.approximate_age} years (recorded {self.age_recorded_on:%d %b %Y})'
        return 'Age not recorded'

class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    action = models.CharField(max_length=32)
    object_type = models.CharField(max_length=32, blank=True)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    window_started = models.DateTimeField(default=timezone.now)

from .clinical_models import (MedicalReview, Visit, VisitAmendment, Procedure, TreatmentPlan,
    PlanItem, PlanRevision, PerformedWork, ToothObservation, Attachment)

from .finance_models import (FinancialLock, TreatmentAccount, LedgerEntry, Schedule, Installment, Allocation, CorrectionRequest, AccountEvent, Expense)

from .workflow_models import (WorkflowLock, Appointment, PersonalTask, ClinicPrintSettings, PrescriberProfile, Prescription, PrescriptionCorrection, WorkflowEvent)
