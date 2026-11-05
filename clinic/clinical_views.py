from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from .access import clinic_required
from .attachments import store_attachment, stored_path
from .clinical_forms import (VisitForm, AmendmentForm, MedicalReviewForm, PlanForm, PlanItemForm,
                            ProcedureForm, WorkForm, ObservationForm, AttachmentForm, MEDICAL_FIELDS)
from .clinical_services import audit, current_medical, ensure_medical_review, update_medical, save_visit, StaleRevision, plan_snapshot
from .models import (Patient, Visit, VisitAmendment, MedicalReview, TreatmentPlan, PlanItem,
                     Procedure, PerformedWork, ToothObservation, Attachment)
from .teeth import ADULT_ROWS, PRIMARY_ROWS

SECTIONS = {'visits': ('Visits', 'view_visit'), 'medical': ('Medical History', 'view_medicalreview'),
            'chart': ('Dental Chart', 'view_toothobservation'), 'plans': ('Treatment Plans', 'view_treatmentplan'),
            'attachments': ('Attachments / X-rays', 'view_attachment')}


def context(patient, **values):
    return {'patient': patient, 'adult_rows': ADULT_ROWS, 'primary_rows': PRIMARY_ROWS,
            'current_medical': current_medical(patient), **values}


def form_page(request, patient, form, heading, status=200, **extra):
    return render(request, 'clinical/form.html', context(patient, form=form, heading=heading, **extra), status=status)


def section_context(patient, section, request):
    querysets = {'visits': patient.visits.select_related('clinician'), 'medical': patient.medical_reviews.select_related('reviewed_by'),
                 'chart': patient.observations.select_related('author', 'visit'), 'plans': patient.treatment_plans.prefetch_related('items__procedure'),
                 'attachments': patient.attachments.select_related('uploader', 'visit')}
    page = Paginator(querysets[section], 20).get_page(request.GET.get('page', 1))
    if section == 'attachments':
        for attachment in page:
            try:
                attachment.original_available = stored_path(attachment.storage_name).is_file()
                attachment.preview_available = bool(attachment.thumbnail_name) and stored_path(attachment.thumbnail_name).is_file()
            except ValidationError:
                attachment.original_available = attachment.preview_available = False
    return context(patient, section=section, heading=SECTIONS[section][0], page=page,
                   unfinished=patient.visits.exclude(status='completed')[:5],
                   performed=PerformedWork.objects.filter(patient=patient).select_related('visit', 'procedure')[:50])


@clinic_required()
@require_GET
def section(request, pk, section):
    if section not in SECTIONS:
        return HttpResponse(status=404)
    if not request.user.has_perm('clinic.' + SECTIONS[section][1]):
        raise PermissionDenied
    patient = get_object_or_404(Patient, pk=pk)
    audit(request.user, patient, 'view')
    return render(request, 'clinical/section.html', section_context(patient, section, request))


@clinic_required('add_visit')
@require_http_methods(['GET', 'POST'])
def visit_new(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = VisitForm(request.POST or None, initial={'visit_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'clinician': request.user.pk, 'status': 'in_progress', 'revision': 0})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            visit = form.save(commit=False)
            visit.patient = patient
            visit.medical_review = ensure_medical_review(patient, request.user, force=True)
            visit.created_by = visit.updated_by = request.user
            visit.full_clean()
            visit.save()
            audit(request.user, patient, 'visit_create', visit)
        return redirect('visit_detail', pk=pk, visit_id=visit.pk)
    return form_page(request, patient, form, 'Start visit', creating_visit=True)


@clinic_required('view_visit')
@require_GET
def visit_detail(request, pk, visit_id):
    patient = get_object_or_404(Patient, pk=pk)
    visit = get_object_or_404(Visit.objects.select_related('clinician', 'medical_review__reviewed_by'), patient=patient, pk=visit_id)
    audit(request.user, patient, 'visit_view', visit)
    return render(request, 'clinical/visit.html', context(patient, visit=visit))


def edit_visit(request, pk, visit_id, autosave=False):
    patient = get_object_or_404(Patient, pk=pk)
    visit = get_object_or_404(Visit, patient=patient, pk=visit_id)
    if visit.status == 'completed':
        return JsonResponse({'error': 'completed_visit_requires_amendment'}, status=409) if autosave else redirect('visit_detail', pk=pk, visit_id=visit_id)
    form = VisitForm(request.POST if request.method == 'POST' else None, instance=visit)
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            try:
                visit = save_visit(visit, form, request.user, complete=not autosave and request.POST.get('action') == 'complete')
                if autosave:
                    return JsonResponse({'saved': True, 'revision': visit.revision, 'saved_at': timezone.localtime(visit.updated_at).strftime('%H:%M:%S')})
                messages.success(request, 'Visit completed. Original notes are preserved.' if visit.status == 'completed' else 'Visit saved.')
                return redirect('visit_detail', pk=pk, visit_id=visit_id)
            except StaleRevision:
                status = 409
                form.add_error(None, 'Another tab saved a newer revision or completed this visit. Your text remains below. Open the latest visit in another tab and reconcile your changes; do not discard this tab.')
            except ValidationError as exc:
                form.add_error(None, exc)
        else:
            status = 400
        if autosave:
            return JsonResponse({'error': 'conflict' if status == 409 else 'validation'}, status=status if status != 200 else 400)
    return form_page(request, patient, form, 'Continue visit', status=status, visit=visit, editing_visit=True)


@clinic_required('change_visit')
@require_http_methods(['GET', 'POST'])
def visit_edit(request, pk, visit_id):
    return edit_visit(request, pk, visit_id)


@require_POST
def visit_autosave(request, pk, visit_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'session_expired'}, status=401)
    if not request.user.has_perm('clinic.change_visit'):
        return JsonResponse({'error': 'permission_denied'}, status=403)
    return edit_visit(request, pk, visit_id, autosave=True)


@clinic_required('add_visitamendment')
@require_http_methods(['GET', 'POST'])
def amend(request, pk, visit_id):
    patient = get_object_or_404(Patient, pk=pk)
    visit = get_object_or_404(Visit, patient=patient, pk=visit_id, status='completed')
    form = AmendmentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            amendment = form.save(commit=False)
            amendment.visit, amendment.author = visit, request.user
            amendment.save()
            audit(request.user, patient, 'visit_amend', amendment)
        return redirect('visit_detail', pk=pk, visit_id=visit_id)
    return form_page(request, patient, form, 'Amend completed visit', visit=visit)


@clinic_required('add_medicalreview')
@require_http_methods(['GET', 'POST'])
def medical_review(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    snapshot = current_medical(patient)
    initial = {}
    for key, value in snapshot.items():
        initial[key], initial[key + '_state'] = value['details'], value['state']
    form = MedicalReviewForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        update_medical(patient, request.user, form.snapshot(), form.cleaned_data['reason'])
        return redirect('clinical_section', pk=pk, section='medical')
    return form_page(request, patient, form, 'Review medical history')


@clinic_required('add_toothobservation')
@require_http_methods(['GET', 'POST'])
def chart_add(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = ObservationForm(request.POST or None, patient=patient, instance=ToothObservation(patient=patient, author=request.user))
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            observation = form.save()
            audit(request.user, patient, 'chart_observe', observation)
        return redirect('clinical_section', pk=pk, section='chart')
    return form_page(request, patient, form, 'Record dated dental observation')


@clinic_required('change_treatmentplan')
@require_http_methods(['GET', 'POST'])
def plan_edit(request, pk, plan_id=None):
    patient = get_object_or_404(Patient, pk=pk)
    plan = get_object_or_404(TreatmentPlan, patient=patient, pk=plan_id) if plan_id else TreatmentPlan(patient=patient, created_by=request.user)
    if not plan_id and not request.user.has_perm('clinic.add_treatmentplan'):
        raise PermissionDenied
    form = PlanForm(request.POST or None, instance=plan, initial={'revision': plan.revision})
    status = 200
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            if plan_id:
                changed = TreatmentPlan.objects.filter(pk=plan_id, patient=patient, revision=form.cleaned_data['revision']).update(title=form.cleaned_data['title'], notes=form.cleaned_data['notes'], revision=form.cleaned_data['revision'] + 1)
                if not changed:
                    form.add_error(None, 'Newer plan revision exists. Your edits were not applied.')
                    status = 409
                else:
                    plan.refresh_from_db()
            else:
                plan = form.save()
            if status == 200:
                plan_snapshot(plan, request.user)
                audit(request.user, patient, 'plan_update' if plan_id else 'plan_create', plan)
                return redirect('plan_detail', pk=pk, plan_id=plan.pk)
    return form_page(request, patient, form, 'Edit treatment plan' if plan_id else 'New treatment plan', status=status)


@clinic_required('view_treatmentplan')
@require_GET
def plan_detail(request, pk, plan_id):
    patient = get_object_or_404(Patient, pk=pk)
    plan = get_object_or_404(TreatmentPlan, patient=patient, pk=plan_id)
    return render(request, 'clinical/plan.html', context(patient, plan=plan))


@clinic_required('change_planitem')
@require_http_methods(['GET', 'POST'])
def item_edit(request, pk, plan_id, item_id=None):
    patient = get_object_or_404(Patient, pk=pk)
    plan = get_object_or_404(TreatmentPlan, patient=patient, pk=plan_id)
    item = get_object_or_404(PlanItem, plan=plan, pk=item_id) if item_id else PlanItem(plan=plan)
    if not item_id and not request.user.has_perm('clinic.add_planitem'):
        raise PermissionDenied
    form = PlanItemForm(request.POST or None, instance=item, initial={'revision': item.revision})
    status = 200
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            if item_id:
                values = {key: form.cleaned_data[key] for key in form.Meta.fields}
                values['revision'] = form.cleaned_data['revision'] + 1
                changed = PlanItem.objects.filter(pk=item_id, plan=plan, revision=form.cleaned_data['revision']).update(**values)
                if not changed:
                    form.add_error(None, 'Another tab changed this plan item. Your edits were not applied.')
                    status = 409
            else:
                item = form.save()
            if status == 200:
                plan_snapshot(plan, request.user)
                audit(request.user, patient, 'plan_update', plan)
                return redirect('plan_detail', pk=pk, plan_id=plan_id)
    return form_page(request, patient, form, 'Edit plan item' if item_id else 'Add plan item', status=status)


@clinic_required('add_performedwork')
@require_http_methods(['GET', 'POST'])
def work_add(request, pk, visit_id):
    patient = get_object_or_404(Patient, pk=pk)
    visit = get_object_or_404(Visit, patient=patient, pk=visit_id, status__in=['draft', 'in_progress'])
    form = WorkForm(request.POST or None, patient=patient, instance=PerformedWork(patient=patient, visit=visit, author=request.user))
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            # Recheck status within the write transaction, not only the GET.
            if not Visit.objects.filter(pk=visit_id).exclude(status='completed').exists():
                return form_page(request, patient, form, 'Record performed procedure', status=409, visit=visit)
            work = form.save(commit=False)
            work.procedure_label = str(work.procedure)
            work.full_clean()
            work.save()
            audit(request.user, patient, 'procedure_record', work)
        return redirect('visit_detail', pk=pk, visit_id=visit_id)
    return form_page(request, patient, form, 'Record performed procedure', visit=visit)


@clinic_required('view_procedure')
@require_http_methods(['GET', 'POST'])
def catalogue(request, procedure_id=None):
    procedure = get_object_or_404(Procedure, pk=procedure_id) if procedure_id else Procedure()
    form = ProcedureForm(request.POST or None, instance=procedure)
    if request.method == 'POST':
        permission = 'change_procedure' if procedure_id else 'add_procedure'
        if not request.user.has_perm('clinic.' + permission):
            raise PermissionDenied
        if form.is_valid():
            form.save()
            messages.success(request, 'Procedure catalogue saved. No prices are recorded in Phase 2.')
            return redirect('catalogue')
    return render(request, 'clinical/catalogue.html', {'form': form, 'procedures': Procedure.objects.all()})


@clinic_required('add_attachment')
@require_http_methods(['GET', 'POST'])
def upload(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = AttachmentForm(request.POST or None, request.FILES or None, patient=patient, instance=Attachment(patient=patient, uploader=request.user))
    if request.method == 'POST' and form.is_valid():
        try:
            store_attachment(form, form.cleaned_data['file'], patient, request.user)
            return redirect('clinical_section', pk=pk, section='attachments')
        except ValidationError as exc:
            form.add_error('file', exc)
        except Exception:
            # Safe diagnostics format ignores exception text and form content.
            import logging
            logging.getLogger('django.request').error('attachment_processing_failed', exc_info=True)
            form.add_error('file', 'Upload could not be stored. No new attachment was retained; please retry or contact the owner.')
    return form_page(request, patient, form, 'Upload private attachment')


@clinic_required('view_attachment')
@require_GET
def attachment_file(request, pk, attachment_id, mode):
    patient = get_object_or_404(Patient, pk=pk)
    attachment = get_object_or_404(Attachment, patient=patient, pk=attachment_id)
    if mode not in ['original', 'download', 'preview', 'thumbnail'] or (mode in ['preview', 'thumbnail'] and not attachment.content_type.startswith('image/')):
        return HttpResponse(status=404)
    name = attachment.thumbnail_name if mode == 'thumbnail' else attachment.storage_name
    try:
        if not name:
            raise FileNotFoundError
        handle = stored_path(name).open('rb')
    except (OSError, ValidationError):
        return HttpResponse('Attachment unavailable. Contact the clinic owner; its metadata has been preserved.', status=404, content_type='text/plain')
    try:
        audit(request.user, patient, 'attachment_access', attachment)
    except Exception:
        handle.close()
        raise
    response = FileResponse(handle, as_attachment=mode in ['original', 'download'],
        filename=f'attachment-{attachment.pk}' + ('.png' if mode == 'thumbnail' else __import__('pathlib').Path(name).suffix),
        content_type='image/png' if mode == 'thumbnail' else attachment.content_type)
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    response['X-Content-Type-Options'] = 'nosniff'
    return response
