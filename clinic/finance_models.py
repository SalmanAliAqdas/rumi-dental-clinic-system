import uuid
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

METHODS = [('cash', 'Cash'), ('bank', 'Bank transfer'), ('easypaisa', 'Easypaisa')]
KINDS = [('charge', 'Charge'), ('payment', 'Payment'), ('discount', 'Approved discount'), ('writeoff', 'Approved write-off'), ('refund', 'Refund'), ('reversal', 'Reversal')]

class PostedQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Posted records are immutable. Record an explicit correction.')
    def delete(self):
        raise ValidationError('Posted records cannot be deleted.')

class Posted(models.Model):
    objects = PostedQuerySet.as_manager()
    class Meta:
        abstract = True
    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Posted records are immutable.')
        super().save(*args, **kwargs)
    def delete(self, *args, **kwargs):
        raise ValidationError('Posted records cannot be deleted.')

class FinancialLock(models.Model):
    revision = models.PositiveBigIntegerField(default=0)

class TreatmentAccount(models.Model):
    patient = models.ForeignKey('Patient', on_delete=models.PROTECT, related_name='treatment_accounts')
    title = models.CharField(max_length=160)
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token = models.UUIDField(unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['-created_at', '-pk']
    @property
    def totals(self):
        from .finance_services import totals
        return totals(self)
    @property
    def status(self):
        t = self.totals
        if self.closed_at:
            return 'Closed - settled with adjustment' if t['reductions'] else 'Closed - fully paid'
        if t['balance'] == 0 and t['charges']:
            return 'Settled with adjustment' if t['reductions'] else 'Fully paid'
        return 'Outstanding' if t['balance'] > 0 else 'Awaiting charges'

class LedgerEntry(Posted):
    account = models.ForeignKey(TreatmentAccount, on_delete=models.PROTECT, related_name='entries')
    kind = models.CharField(max_length=12, choices=KINDS)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=240)
    method = models.CharField(max_length=12, choices=METHODS, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token = models.UUIDField(unique=True)
    original = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='corrections')
    plan_item = models.OneToOneField('PlanItem', on_delete=models.PROTECT, null=True, blank=True, related_name='charge')
    visit = models.ForeignKey('Visit', on_delete=models.PROTECT, null=True, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    recorded_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    def __str__(self):
        return f'{self.get_kind_display()} PKR {self.amount} / {self.reference}'
    class Meta:
        ordering = ['received_at', 'pk']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='ledger_positive_amount'),
                       models.CheckConstraint(condition=Q(balance_after__gte=0), name='ledger_nonnegative_balance')]

class Schedule(Posted):
    account = models.ForeignKey(TreatmentAccount, on_delete=models.PROTECT, related_name='schedules')
    reason = models.CharField(max_length=240)
    token = models.UUIDField(unique=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    # A new immutable schedule supersedes all earlier ones.
    class Meta:
        ordering = ['-pk']

class Installment(Posted):
    schedule = models.ForeignKey(Schedule, on_delete=models.PROTECT, related_name='items')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    due_on = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=240, blank=True)
    class Meta:
        ordering = ['pk']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='installment_positive_amount')]
    @property
    def allocated(self):
        return sum((a.amount for a in self.allocations.all()), Decimal('0.00'))
    @property
    def remaining(self):
        return self.amount - self.allocated
    @property
    def status(self):
        if self.remaining == 0:
            return 'Paid'
        from .finance_services import today
        if self.due_on and self.due_on < today():
            return 'Overdue'
        return 'Partially Paid' if self.allocated else 'Pending'

class Allocation(Posted):
    installment = models.ForeignKey(Installment, on_delete=models.PROTECT, related_name='allocations')
    entry = models.ForeignKey(LedgerEntry, on_delete=models.PROTECT, related_name='allocations')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['installment', 'entry'], name='unique_installment_entry')]

class CorrectionRequest(models.Model):
    account = models.ForeignKey(TreatmentAccount, on_delete=models.PROTECT, related_name='correction_requests')
    original = models.ForeignKey(LedgerEntry, on_delete=models.PROTECT)
    reason = models.CharField(max_length=240)
    token = models.UUIDField(unique=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=12, default='pending', choices=[('pending','Pending'),('approved','Approved'),('rejected','Rejected')])
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name='+')
    decided_at = models.DateTimeField(null=True)
    decision_reason = models.CharField(max_length=240, blank=True)

class AccountEvent(Posted):
    account = models.ForeignKey(TreatmentAccount, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=24)
    reason = models.CharField(max_length=240)
    token = models.UUIDField(unique=True)
    created_at = models.DateTimeField(default=timezone.now)

class Expense(Posted):
    spent_on = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=100)
    description = models.CharField(max_length=240)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=12, choices=METHODS)
    reference = models.CharField(max_length=120, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(default=timezone.now)
    token = models.UUIDField(unique=True)
    original = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True, related_name='reversal')
    class Meta:
        ordering = ['-spent_on', '-pk']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='expense_positive_amount')]
