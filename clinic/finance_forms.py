from uuid import uuid4
from decimal import Decimal
from django import forms
from django.utils import timezone
from .finance_models import METHODS
from .models import PlanItem, Visit, LedgerEntry

class TokenForm(forms.Form):
    token = forms.UUIDField(widget=forms.HiddenInput)
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label_suffix','')
        super().__init__(*args, **kwargs)
        if not self.is_bound: self.initial['token'] = uuid4()

class AccountForm(TokenForm):
    title = forms.CharField(max_length=160, label='Treatment account title')

class EntryForm(TokenForm):
    kind = forms.ChoiceField(choices=[('charge','Record Charge'),('payment','Receive Payment')])
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'), label='Amount (PKR)')
    description = forms.CharField(max_length=240, required=False, label='Description / correction reason')
    method = forms.ChoiceField(choices=[('', 'Choose payment method')] + METHODS, required=False)
    payment_reference = forms.CharField(max_length=120, required=False)
    received_at = forms.DateTimeField(required=False, widget=forms.DateTimeInput(attrs={'type':'datetime-local'}))
    original = forms.ModelChoiceField(queryset=LedgerEntry.objects.none(), required=False)
    plan_item = forms.ModelChoiceField(queryset=PlanItem.objects.none(), required=False, label='Treatment plan item (charged only once)')
    visit = forms.ModelChoiceField(queryset=Visit.objects.none(), required=False)
    def __init__(self, *args, account, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['original'].queryset = account.entries.all()
        self.fields['plan_item'].queryset = PlanItem.objects.filter(plan__patient=account.patient).select_related('plan','procedure')
        self.fields['visit'].queryset = account.patient.visits.all()
        if actor.is_superuser:
            self.fields['kind'].choices += [('discount','Approve discount'),('writeoff','Approve write-off'),('refund','Refund payment'),('reversal','Reverse original entry')]
        else:
            self.fields.pop('received_at')
            self.fields.pop('original')
        self.fields['amount'].widget.attrs['step'] = '.01'

class ScheduleForm(TokenForm):
    reason = forms.CharField(max_length=240, label='Agreement notes / Owner revision reason')
    installments = forms.CharField(widget=forms.Textarea(attrs={'rows':5}), help_text='One installment per line: amount | optional YYYY-MM-DD | optional notes. Example: 2000 | 2026-12-01 | Agreed first payment. Leave date blank if none agreed.')
    def clean_installments(self):
        from datetime import date
        from .finance_services import money
        rows = []
        for line in self.cleaned_data['installments'].splitlines():
            if not line.strip(): continue
            parts = [p.strip() for p in line.split('|')]
            if len(parts) > 3: raise forms.ValidationError('Use amount | optional date | optional notes.')
            try:
                rows.append(dict(amount=money(parts[0]), due_on=date.fromisoformat(parts[1]) if len(parts)>1 and parts[1] else None,
                                 notes=parts[2][:240] if len(parts)>2 else ''))
            except ValueError: raise forms.ValidationError('Use YYYY-MM-DD for agreed dates.')
        if len(rows)>60: raise forms.ValidationError('Use at most 60 installments.')
        return rows

class ReasonForm(TokenForm):
    reason = forms.CharField(max_length=240)

class CorrectionForm(ReasonForm):
    original = forms.ModelChoiceField(queryset=LedgerEntry.objects.none())
    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['original'].queryset = account.entries.filter(kind__in=['charge','payment','discount','writeoff'])

class DecisionForm(ReasonForm):
    decision = forms.ChoiceField(choices=[('approve','Approve reversal'),('reject','Reject request')])

class ExpenseForm(TokenForm):
    spent_on = forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={'type':'date'}))
    category = forms.CharField(max_length=100)
    description = forms.CharField(max_length=240)
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    method = forms.ChoiceField(choices=METHODS)
    reference = forms.CharField(max_length=120, required=False)
