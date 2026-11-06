"""All financial writes serialize before reading state (including on SQLite)."""
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import (FinancialLock, TreatmentAccount, LedgerEntry, Schedule, Installment,
                     Allocation, CorrectionRequest, AccountEvent, Expense, AuditEvent)
from .finance_models import METHODS, KINDS

ZERO = Decimal('0.00')
PK = ZoneInfo('Asia/Karachi')

def today():
    return timezone.now().astimezone(PK).date()

def boundaries(start, end):
    return datetime.combine(start, time.min, PK), datetime.combine(end + timedelta(days=1), time.min, PK)

def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result <= 0 or result.as_tuple().exponent < -2 or result > Decimal('999999999999.99'):
            raise ValueError
        return result.quantize(Decimal('.01'))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError('Enter a positive PKR amount with at most two decimal places.')

def owner(actor):
    if not actor.is_active or not actor.is_superuser:
        raise PermissionDenied

def clinician(actor):
    if not actor.is_active or not actor.has_perm('clinic.view_patient'):
        raise PermissionDenied

@contextmanager
def serialized():
    with transaction.atomic():
        # First SQL statement acquires SQLite's write reservation. Never rely on
        # select_for_update(), which does not lock rows on SQLite.
        if FinancialLock.objects.filter(pk=1).update(revision=F('revision') + 1) != 1:
            raise ValidationError('Financial lock missing. Complete migrations before posting.')
        yield

def audit(actor, account, action, obj):
    AuditEvent.objects.create(actor=actor, patient=account.patient, action=action,
                              object_type=type(obj).__name__, object_id=obj.pk)

def totals(account):
    charges = original_charges = reversed_charges = payments = reductions = refunds = ZERO
    for e in account.entries.select_related('original'):
        if e.kind == 'charge':
            charges += e.amount
            original_charges += e.amount
        elif e.kind == 'payment': payments += e.amount
        elif e.kind in ('discount', 'writeoff'): reductions += e.amount
        elif e.kind == 'refund': refunds += e.amount
        elif e.kind == 'reversal':
            if e.original.kind == 'payment': refunds += e.amount
            elif e.original.kind == 'charge':
                charges -= e.amount
                reversed_charges += e.amount
            else: reductions -= e.amount
    return dict(charges=charges, original_charges=original_charges, reversed_charges=reversed_charges, payments=payments, reductions=reductions, refunds=refunds,
                net_paid=payments-refunds, balance=charges-reductions-payments+refunds)

def existing(model, token, **scope):
    try:
        token = UUID(str(token))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('Invalid submission reference. Reload the form.')
    row = model.objects.filter(token=token).first()
    if row and any(getattr(row, key) != value for key, value in scope.items()):
        raise ValidationError('Submission reference belongs to another operation.')
    return row

def create_account(actor, patient, title, token):
    clinician(actor)
    with serialized():
        prior = existing(TreatmentAccount, token, patient_id=patient.pk)
        if prior: return prior
        if not title.strip(): raise ValidationError('Enter an account title.')
        a = TreatmentAccount.objects.create(patient=patient, title=title.strip()[:160], token=token, created_by=actor)
        audit(actor, a, 'account_create', a)
        return a

def active_schedule(account):
    schedule = account.schedules.first()
    if not schedule: return None
    # Charges/adjustments after a schedule require an explicit Owner revision.
    if account.entries.filter(recorded_at__gt=schedule.created_at).exclude(kind__in=['payment','refund']).exclude(kind='reversal', original__kind='payment').exists():
        return None
    if account.events.filter(action='schedule_invalidated', created_at__gt=schedule.created_at).exists(): return None
    return schedule

def allocate(entry):
    schedule = active_schedule(entry.account)
    if not schedule: return
    amount = entry.amount
    items = list(schedule.items.prefetch_related('allocations'))
    if entry.kind == 'payment':
        for item in items:
            part = min(amount, item.remaining)
            if part > 0:
                Allocation.objects.create(installment=item, entry=entry, amount=part)
                amount -= part
    elif entry.kind == 'refund' or (entry.kind == 'reversal' and entry.original.kind == 'payment'):
        for item in reversed(items):
            part = min(amount, item.allocated)
            if part > 0:
                Allocation.objects.create(installment=item, entry=entry, amount=-part)
                amount -= part
        if amount > 0:
            AccountEvent.objects.create(account=entry.account, actor=entry.actor, action='schedule_invalidated', reason='Refund exceeds allocations on current schedule; Owner revision required.', token=entry.reference)

def post(actor, account, kind, amount, token, description='', method='', received_at=None,
         payment_reference='', original=None, plan_item=None, visit=None):
    clinician(actor)
    if kind not in ('charge','payment'): owner(actor)
    with serialized():
        account = TreatmentAccount.objects.get(pk=account.pk)
        prior = existing(LedgerEntry, token, account_id=account.pk, kind=kind)
        if prior: return prior
        if account.closed_at: raise ValidationError('Owner must reopen this account with a reason first.')
        amount = money(amount)
        if kind not in dict(KINDS):
            raise ValidationError('Unknown transaction type.')
        if kind != 'payment' and not description.strip(): raise ValidationError('A description/reason is required.')
        if kind in ('payment','refund') and method not in dict(METHODS): raise ValidationError('Choose cash, bank transfer or Easypaisa.')
        if plan_item and (kind != 'charge' or plan_item.plan.patient_id != account.patient_id):
            raise ValidationError('Charge item must belong to this patient.')
        if plan_item and LedgerEntry.objects.filter(plan_item=plan_item).exists():
            raise ValidationError('This treatment item is already charged. Open its existing account.')
        if visit and visit.patient_id != account.patient_id: raise ValidationError('Visit belongs to another patient.')
        now = timezone.now()
        if not actor.is_superuser:
            received_at = now  # Ignore all client-supplied Doctor dates.
        elif received_at is None: received_at = now
        if received_at > now: raise ValidationError('Future receipt dates are not allowed.')
        t = totals(account)
        effect = amount if kind in ('charge','refund') else -amount
        if kind in ('refund','reversal'):
            if not original or original.account_id != account.pk:
                raise ValidationError('Choose an original entry in this account.')
            original = LedgerEntry.objects.get(pk=original.pk)
            if original.kind not in ('payment','charge','discount','writeoff') or (kind == 'refund' and original.kind != 'payment'):
                raise ValidationError('This entry cannot be refunded/reversed.')
            used = sum((e.amount for e in original.corrections.all()), ZERO)
            if used + amount > original.amount: raise ValidationError('Correction exceeds the uncorrected original amount.')
            if kind == 'reversal' and (used or amount != original.amount):
                raise ValidationError('A reversal must reverse the complete uncorrected original entry.')
            if original.kind == 'payment':
                effect = amount
                method = original.method
            elif original.kind == 'charge': effect = -amount
            else: effect = amount
        elif original:
            raise ValidationError('Original entry is only valid for refunds/reversals.')
        balance = t['balance'] + effect
        if balance < 0: raise ValidationError('Amount exceeds the remaining balance; overpayments are not allowed.')
        if balance > Decimal('999999999999.99'): raise ValidationError('Account balance exceeds the supported amount.')
        entry = LedgerEntry.objects.create(account=account, kind=kind, amount=amount, token=token,
            description=description.strip()[:240] or 'Payment received', method=method,
            received_at=received_at, recorded_at=now, actor=actor, original=original,
            plan_item=plan_item, visit=visit, payment_reference=payment_reference[:120], balance_after=balance)
        allocate(entry)
        audit(actor, account, 'finance_' + kind, entry)
        return entry

def schedule_account(actor, account, rows, reason, token):
    clinician(actor)
    with serialized():
        account = TreatmentAccount.objects.get(pk=account.pk)
        prior = existing(Schedule, token, account_id=account.pk)
        if prior: return prior
        if account.closed_at: raise ValidationError('Reopen the account before changing installments.')
        if account.schedules.exists(): owner(actor)
        if not reason.strip(): raise ValidationError('Enter schedule notes or a revision reason.')
        amounts = [money(row['amount']) for row in rows]
        if not amounts or sum(amounts, ZERO) != totals(account)['balance']:
            raise ValidationError('Installments must add up exactly to the current remaining balance.')
        schedule = Schedule.objects.create(account=account, actor=actor, reason=reason, token=token)
        for row, amount in zip(rows, amounts):
            Installment.objects.create(schedule=schedule, amount=amount, due_on=row.get('due_on'), notes=row.get('notes',''))
        audit(actor, account, 'schedule_create', schedule)
        return schedule

def account_action(actor, account, action, reason, token):
    clinician(actor)
    with serialized():
        account = TreatmentAccount.objects.get(pk=account.pk)
        prior = existing(AccountEvent, token, account_id=account.pk, action=action)
        if prior: return prior
        if action == 'reopen':
            owner(actor)
            if not account.closed_at or not reason.strip(): raise ValidationError('A closed account and reopening reason are required.')
            account.closed_at = None
        elif action == 'close':
            t = totals(account)
            if account.closed_at or t['balance'] != 0 or t['charges'] <= 0:
                raise ValidationError('Only an open zero-balance account with charges can be closed.')
            if t['reductions']: owner(actor)
            account.closed_at = timezone.now()
        else: raise ValidationError('Invalid account action.')
        account.save(update_fields=['closed_at'])
        event = AccountEvent.objects.create(account=account, action=action, actor=actor, reason=reason or 'Full payment received', token=token)
        audit(actor, account, 'account_' + action, event)
        return event

def request_correction(actor, account, original, reason, token):
    clinician(actor)
    with serialized():
        prior = existing(CorrectionRequest, token, account_id=account.pk, original_id=original.pk)
        if prior: return prior
        if original.account_id != account.pk or not reason.strip(): raise ValidationError('Choose an account entry and give a reason.')
        if original.kind not in ('payment','charge','discount','writeoff'): raise ValidationError('This entry cannot be reversed.')
        row = CorrectionRequest.objects.create(account=account, original=original, reason=reason, token=token, requested_by=actor)
        audit(actor, account, 'correction_request', row)
        return row

def decide(actor, account, correction, approved, reason, token):
    owner(actor)
    with serialized():
        correction = CorrectionRequest.objects.get(pk=correction.pk, account=account)
        prior = existing(AccountEvent, token, account_id=account.pk, action='correction_decision')
        if prior: return prior
        if correction.status != 'pending' or not reason.strip(): raise ValidationError('Pending request and decision reason required.')
        if approved:
            post(actor, account, 'reversal', correction.original.amount, token, reason, original=correction.original)
        correction.status = 'approved' if approved else 'rejected'
        correction.decided_by = actor
        correction.decided_at = timezone.now()
        correction.decision_reason = reason
        correction.save()
        event = AccountEvent.objects.create(account=account, actor=actor, token=token, action='correction_decision', reason=reason)
        audit(actor, account, 'correction_decision', correction)
        return event

def expense(actor, data, token, original=None):
    owner(actor)
    with serialized():
        prior = existing(Expense, token)
        if prior: return prior
        if original:
            original = Expense.objects.get(pk=original.pk)
            if original.original_id or Expense.objects.filter(original=original).exists(): raise ValidationError('Expense already reversed or is a reversal.')
            if not data.get('description','').strip(): raise ValidationError('A correction reason is required.')
            data = dict(spent_on=today(), category=original.category, description=data['description'],
                        amount=original.amount, method=original.method, reference=original.reference)
        if data['method'] not in dict(METHODS): raise ValidationError('Invalid expense method.')
        if data['spent_on'] > today(): raise ValidationError('Future expenses are not allowed.')
        return Expense.objects.create(actor=actor, token=token, original=original, **{**data, 'amount': money(data['amount'])})
