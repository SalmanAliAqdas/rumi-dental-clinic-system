from datetime import date, timedelta
from decimal import Decimal
import csv
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import OperationalError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from .access import clinic_required
from .models import Patient, TreatmentAccount, LedgerEntry, CorrectionRequest, Expense
from .finance_models import METHODS
from .finance_forms import (AccountForm, EntryForm, ScheduleForm, ReasonForm, CorrectionForm, DecisionForm, ExpenseForm)
from . import finance_services as service


def audit_view(actor, account):
    service.audit(actor, account, 'finance_view', account)

def scoped(pk, account_id):
    patient = get_object_or_404(Patient, pk=pk)
    return patient, get_object_or_404(TreatmentAccount, pk=account_id, patient=patient)

def form_page(request, form, heading, callback, patient=None, account=None):
    status = 200
    if request.method == 'POST' and form.is_valid():
        try:
            result = callback(form.cleaned_data)
            return result
        except ValidationError as exc:
            form.add_error(None, exc)
            status = 400
        except OperationalError:
            form.add_error(None, 'The database is busy. Retry this same submission; its reference prevents duplicate posting.')
            status = 409
    elif request.method == 'POST': status = 400
    return render(request, 'finance/form.html', dict(form=form, heading=heading, patient=patient, account=account), status=status)

@clinic_required()
@require_GET
def patient_accounts(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    accounts = patient.treatment_accounts.all()
    for a in accounts: audit_view(request.user, a)
    return render(request, 'finance/patient.html', dict(patient=patient, accounts=accounts))

@clinic_required()
@require_http_methods(['GET','POST'])
def account_new(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = AccountForm(request.POST or None)
    def save(data):
        a = service.create_account(request.user, patient, **data)
        return redirect('finance_account', pk=pk, account_id=a.pk)
    return form_page(request, form, 'New treatment account', save, patient=patient)

@clinic_required()
@require_GET
def account_detail(request, pk, account_id):
    patient, a = scoped(pk, account_id)
    audit_view(request.user, a)
    schedule = service.active_schedule(a)
    t = service.totals(a)
    if schedule and sum((i.remaining for i in schedule.items.all()), service.ZERO) != t['balance']: schedule = None
    return render(request, 'finance/account.html', dict(patient=patient, account=a, totals=t,
        entries=a.entries.select_related('actor','original','plan_item','visit'), schedule=schedule,
        can_close=not a.closed_at and t['balance']==0 and t['charges']>0 and (not t['reductions'] or request.user.is_superuser),
        schedules=a.schedules.prefetch_related('items__allocations'), requests=a.correction_requests.select_related('original','requested_by','decided_by'), events=a.events.select_related('actor')))

@clinic_required()
@require_http_methods(['GET','POST'])
def entry_new(request, pk, account_id):
    patient, a = scoped(pk, account_id)
    initial = {'kind':request.GET.get('kind','payment'), 'amount': service.totals(a)['balance'] or None}
    form = EntryForm(request.POST or None, account=a, actor=request.user, initial=initial)
    def save(data):
        entry = service.post(request.user, a, **data)
        if entry.kind == 'payment': return redirect('finance_receipt', pk=pk, account_id=a.pk, entry_id=entry.pk)
        return redirect('finance_account', pk=pk, account_id=a.pk)
    return form_page(request, form, 'Record charge / receive payment', save, patient, a)

@clinic_required()
@require_http_methods(['GET','POST'])
def schedule_new(request, pk, account_id):
    patient, a = scoped(pk, account_id)
    if a.schedules.exists() and not request.user.is_superuser: raise PermissionDenied
    form = ScheduleForm(request.POST or None)
    def save(data):
        service.schedule_account(request.user, a, data['installments'], data['reason'], data['token'])
        return redirect('finance_account', pk=pk, account_id=a.pk)
    return form_page(request, form, 'Installment agreement / schedule revision', save, patient, a)

@clinic_required()
@require_http_methods(['GET','POST'])
def account_action(request, pk, account_id, action):
    patient, a = scoped(pk, account_id)
    if action not in ('close','reopen'): return HttpResponse(status=404)
    if action == 'reopen' and not request.user.is_superuser: raise PermissionDenied
    form = ReasonForm(request.POST or None)
    def save(data):
        service.account_action(request.user, a, action, **data)
        return redirect('finance_account', pk=pk, account_id=a.pk)
    return form_page(request, form, 'Close account' if action=='close' else 'Reopen account (Owner)', save, patient, a)

@clinic_required()
@require_http_methods(['GET','POST'])
def correction_new(request, pk, account_id):
    patient, a = scoped(pk, account_id)
    form = CorrectionForm(request.POST or None, account=a)
    def save(data):
        service.request_correction(request.user, a, **data)
        return redirect('finance_account', pk=pk, account_id=a.pk)
    return form_page(request, form, 'Request reversal / correction', save, patient, a)

@clinic_required(owner=True)
@require_http_methods(['GET','POST'])
def correction_decide(request, pk, account_id, correction_id):
    patient, a = scoped(pk, account_id)
    correction = get_object_or_404(CorrectionRequest, pk=correction_id, account=a)
    form = DecisionForm(request.POST or None)
    def save(data):
        service.decide(request.user, a, correction, data['decision']=='approve', data['reason'], data['token'])
        return redirect('finance_account', pk=pk, account_id=a.pk)
    return form_page(request, form, 'Owner correction decision: ' + correction.reason, save, patient, a)

@clinic_required()
@require_GET
def receipt(request, pk, account_id, entry_id):
    patient, a = scoped(pk, account_id)
    e = get_object_or_404(LedgerEntry, pk=entry_id, account=a, kind='payment')
    audit_view(request.user, a)
    return render(request, 'finance/receipt.html', dict(patient=patient, account=a, entry=e, totals=service.totals(a)))

@clinic_required()
@require_GET
def outstanding(request):
    allowed = {'filter','page'}
    if not request.user.is_superuser and set(request.GET)-allowed: raise PermissionDenied
    choice = request.GET.get('filter','outstanding')
    if choice not in ('outstanding','due','overdue','settled'): return HttpResponse('Invalid filter',status=400)
    rows = []
    for a in TreatmentAccount.objects.select_related('patient'):
        t = service.totals(a)
        schedule = service.active_schedule(a)
        pending = [i for i in schedule.items.all() if i.remaining>0] if schedule else []
        next_due = min((i.due_on for i in pending if i.due_on), default=None)
        matches = (choice=='settled' and t['balance']==0 and t['charges']>0) or (choice=='outstanding' and t['balance']>0 and not a.closed_at) or (choice=='due' and t['balance']>0 and next_due and next_due<=service.today()) or (choice=='overdue' and t['balance']>0 and next_due and next_due<service.today())
        status='Overdue' if next_due and next_due<service.today() else 'Installments due' if next_due and next_due==service.today() else 'Schedule revision required' if not schedule and a.schedules.exists() and t['balance']>0 else a.status
        if matches: rows.append(dict(account=a, balance=t['balance'], next_due=next_due, status=status))
    page = Paginator(rows,20).get_page(request.GET.get('page'))
    context = dict(page=page, choice=choice)
    if request.user.is_superuser: context['combined_balance'] = sum((r['balance'] for r in rows), service.ZERO)
    return render(request,'finance/outstanding.html',context)


def collection_data(start, end):
    lo, hi = service.boundaries(start,end)
    entries = LedgerEntry.objects.filter(received_at__gte=lo, received_at__lt=hi).select_related('account__patient','original')
    entries = [e for e in entries if e.kind in ('payment','refund') or (e.kind=='reversal' and e.original.kind=='payment')]
    gross = sum((e.amount for e in entries if e.kind=='payment'),service.ZERO)
    adjustments = sum((e.amount for e in entries if e.kind!='payment'),service.ZERO)
    methods = [(label, sum((e.amount if e.kind=='payment' else -e.amount for e in entries if e.method==key),service.ZERO)) for key,label in METHODS]
    return dict(entries=entries,gross=gross,adjustments=adjustments,net=gross-adjustments,methods=methods)

@clinic_required()
@require_GET
def today_collections(request):
    if request.GET: raise PermissionDenied
    day = service.today()
    return render(request,'finance/collections.html',dict(start=day,end=day,**collection_data(day,day)))


def report_range(query):
    day = service.today()
    period = query.get('period','daily')
    try:
        anchor = date.fromisoformat(query.get('date',day.isoformat()))
        if period=='daily': start=end=anchor
        elif period=='weekly':
            start=anchor-timedelta(days=anchor.weekday()); end=start+timedelta(days=6)
        elif period=='monthly':
            start=anchor.replace(day=1); end=(start.replace(year=start.year+1,month=1) if start.month==12 else start.replace(month=start.month+1))-timedelta(days=1)
        elif period=='annual': start=anchor.replace(month=1,day=1); end=anchor.replace(month=12,day=31)
        elif period=='custom': start=date.fromisoformat(query['start']); end=date.fromisoformat(query['end'])
        else: raise ValueError
        if end<start or end==date.max: raise ValueError
        return start,end
    except (ValueError,KeyError,OverflowError): raise ValidationError('Choose a valid date range (start on or before end).')


def safe_cell(value):
    text=str(value)
    return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else text

@clinic_required(owner=True)
@require_GET
def reports(request, export=False):
    try: start,end=report_range(request.GET)
    except ValidationError as exc: return HttpResponse('; '.join(exc.messages),status=400)
    data=collection_data(start,end)
    lo,hi=service.boundaries(start,end)
    ledger=list(LedgerEntry.objects.filter(received_at__gte=lo,received_at__lt=hi).select_related('account__patient','original'))
    charges=sum((e.amount if e.kind=='charge' else -e.amount for e in ledger if e.kind=='charge' or (e.kind=='reversal' and e.original.kind=='charge')),service.ZERO)
    reductions=sum((e.amount if e.kind!='reversal' else -e.amount for e in ledger if e.kind in ('discount','writeoff') or (e.kind=='reversal' and e.original.kind in ('discount','writeoff'))),service.ZERO)
    expenses=list(Expense.objects.filter(spent_on__range=(start,end)).select_related('actor','original'))
    expense_total=sum((-e.amount if e.original_id else e.amount for e in expenses),service.ZERO)
    outstanding_total=service.ZERO
    overdue=service.ZERO
    for a in TreatmentAccount.objects.all():
        outstanding_total += service.totals(a)['balance']
        schedule=service.active_schedule(a)
        if schedule:
            overdue += sum((i.remaining for i in schedule.items.all() if i.due_on and i.due_on<service.today()),service.ZERO)
    if export:
        response=HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition']='attachment; filename="rumi-financial-report.csv"'
        writer=csv.writer(response)
        writer.writerow(['Rumi Dental Care financial report',start.isoformat(),end.isoformat(),'PKR'])
        writer.writerow(['Type','Business date/time','Patient number','Account','Reference','Method','Amount PKR','Cash effect PKR','Description'])
        for e in ledger:
            cash=e.amount if e.kind=='payment' else -e.amount if e.kind=='refund' or (e.kind=='reversal' and e.original.kind=='payment') else service.ZERO
            writer.writerow([safe_cell(v) for v in [e.get_kind_display(),e.received_at.astimezone(service.PK).isoformat(),e.account.patient.number,e.account.reference,e.reference,e.get_method_display(),e.amount,cash,e.description]])
        for e in expenses:
            writer.writerow([safe_cell(v) for v in ['Expense reversal' if e.original_id else 'Expense',e.spent_on,'','',e.reference,e.get_method_display(),e.amount,e.amount if e.original_id else -e.amount,e.description]])
        for label,value in [('Net charges in selected range',charges),('Approved net discounts/write-offs in selected range',reductions),('Gross collections',data['gross']),('Refunds/payment reversals',data['adjustments']),('Net collections',data['net']),('Net expenses',expense_total),('Net cash movement',data['net']-expense_total),('Current receivables (as of today)',outstanding_total),('Current overdue installments',overdue)]: writer.writerow([label,value])
        return response
    return render(request,'finance/reports.html',dict(start=start,end=end,expenses=expenses,expense_total=expense_total,
        charges=charges,reductions=reductions,cash_movement=data['net']-expense_total,outstanding_total=outstanding_total,overdue=overdue,**data))

@clinic_required(owner=True)
@require_http_methods(['GET','POST'])
def expense_new(request, expense_id=None):
    original=get_object_or_404(Expense,pk=expense_id) if expense_id else None
    form=ReasonForm(request.POST or None) if original else ExpenseForm(request.POST or None)
    def save(data):
        token=data.pop('token')
        if original: data={'description':data['reason']}
        service.expense(request.user,data,token,original)
        return redirect('finance_reports')
    return form_page(request,form,'Reverse expense with reason' if original else 'Record expense',save)
