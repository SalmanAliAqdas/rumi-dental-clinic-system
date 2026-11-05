from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.http import require_http_methods, require_GET
from .access import clinic_required
from .forms import DoctorCreationForm, PatientForm
from .models import AuditEvent, LoginAttempt, Patient
from .phones import normalize_phone, partial_phone

@require_GET
def trial_ready(request):
    """Loopback-only readiness proof; no account, patient or filesystem data."""
    from django.conf import settings
    from django.http import JsonResponse, HttpResponseNotFound
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from .trial_identity import APPLICATION, CHALLENGE_HEADER, identity_proof, valid_challenge
    challenge = request.headers.get(CHALLENGE_HEADER, '')
    if request.META.get('REMOTE_ADDR') not in ['127.0.0.1', '::1'] or not valid_challenge(challenge):
        return HttpResponseNotFound()
    executor = MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        return JsonResponse({'ready': False}, status=503)
    return JsonResponse({'application': APPLICATION, 'proof': identity_proof(
        settings.SECRET_KEY, challenge, settings.BASE_DIR, connection.settings_dict['NAME'],
    )})

def doctor_group():
    group, _ = Group.objects.get_or_create(name='Doctor')
    group.permissions.set(Permission.objects.filter(content_type__app_label='clinic', codename__in=['view_patient', 'add_patient', 'change_patient']))
    return group

class ClinicLoginView(LoginView):
    template_name = 'login.html'
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        # Independent account and local-client buckets resist password guessing
        # across accounts as well as a targeted account. Persist across restarts.
        keys = [salted_hmac('rumi-login', value).hexdigest() for value in [
            'account:' + request.POST.get('username', '').strip().casefold(),
            'client:' + request.META.get('REMOTE_ADDR', ''),
        ]]
        now = timezone.now()
        for key in keys:
            attempt = LoginAttempt.objects.filter(key=key).first()
            if attempt and attempt.window_started > now - timedelta(minutes=15) and attempt.failures >= 5:
                return render(request, self.template_name, {'form': AuthenticationForm(request), 'locked': True}, status=429)
        form = self.get_form()
        if form.is_valid():
            LoginAttempt.objects.filter(key=keys[0]).delete()
            return self.form_valid(form)
        for key in keys:
            attempt, _ = LoginAttempt.objects.get_or_create(key=key)
            if attempt.window_started <= now - timedelta(minutes=15):
                LoginAttempt.objects.filter(pk=attempt.pk).update(failures=1, window_started=now)
            else:
                LoginAttempt.objects.filter(pk=attempt.pk).update(failures=F('failures') + 1)
        # Entries contain only keyed hashes and counters; prune expired buckets.
        LoginAttempt.objects.filter(window_started__lt=now - timedelta(days=1)).delete()
        return self.form_invalid(form)

@clinic_required()
@require_GET
def dashboard(request):
    return render(request, 'dashboard.html', {'patient_count': Patient.objects.count()})

@clinic_required()
@require_http_methods(['GET', 'POST'])
def search(request):
    query = request.POST.get('query', '').strip()[:160] if request.method == 'POST' else ''
    results = Patient.objects.none()
    error = ''
    if query:
        phone_fragment = partial_phone(query)
        if phone_fragment:
            # Count actual input digits, not the automatically added PK prefix.
            if sum(c.isdigit() for c in query) < 4:
                error = 'Enter at least four phone digits.'
            else:
                try:
                    normalized = normalize_phone(query)
                    results = Patient.objects.filter(Q(phone=normalized) | Q(whatsapp=normalized))
                except ValidationError:
                    results = Patient.objects.filter(Q(phone__contains=phone_fragment) | Q(whatsapp__contains=phone_fragment))
        elif len(query) < 2:
            error = 'Enter at least two characters for a name or patient number.'
        else:
            results = Patient.objects.filter(Q(full_name__icontains=query) | Q(number__icontains=query))
    page = Paginator(results, 20).get_page(request.POST.get('page', 1))
    return render(request, 'search.html', {'query': query, 'page': page, 'search_error': error})

@clinic_required('add_patient')
@require_http_methods(['GET', 'POST'])
def patient_create(request):
    form = PatientForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            patient = form.save(commit=False)
            patient.created_by = patient.updated_by = request.user
            patient.save()
            AuditEvent.objects.create(actor=request.user, patient=patient, action='create')
        messages.success(request, 'Patient registered.')
        return redirect('patient_detail', pk=patient.pk)
    return render(request, 'patient_form.html', {'form': form, 'creating': True})

@clinic_required()
@require_GET
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    AuditEvent.objects.create(actor=request.user, patient=patient, action='view')
    return render(request, 'patient_detail.html', {'patient': patient})

@clinic_required('change_patient')
@require_http_methods(['GET', 'POST'])
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = PatientForm(request.POST or None, instance=patient)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            patient = form.save(commit=False)
            patient.updated_by = request.user
            patient.save()
            AuditEvent.objects.create(actor=request.user, patient=patient, action='update')
        messages.success(request, 'Patient details updated.')
        return redirect('patient_detail', pk=patient.pk)
    return render(request, 'patient_form.html', {'form': form, 'patient': patient})

@clinic_required(owner=True)
@require_http_methods(['GET', 'POST'])
def accounts(request):
    if request.method == 'POST' and request.POST.get('action') in ['disable', 'enable']:
        from django.contrib.auth.models import User
        doctor = get_object_or_404(User, pk=request.POST.get('account_id'), is_superuser=False, is_staff=False, groups__name='Doctor')
        doctor.is_active = request.POST['action'] == 'enable'
        doctor.save(update_fields=['is_active'])
        messages.success(request, 'Doctor account status updated.')
        return redirect('accounts')
    form = DoctorCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
            user.groups.add(doctor_group())
        messages.success(request, 'Doctor account created with patient permissions only.')
        return redirect('accounts')
    from django.contrib.auth.models import User
    return render(request, 'accounts.html', {'form': form, 'accounts': User.objects.order_by('username')})

@clinic_required(owner=True)
@require_GET
def audit(request):
    events = AuditEvent.objects.select_related('actor', 'patient').order_by('-occurred_at', '-pk')
    return render(request, 'audit.html', {'page': Paginator(events, 50).get_page(request.GET.get('page', 1))})
