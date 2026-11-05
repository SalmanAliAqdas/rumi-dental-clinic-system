from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from .models import (Visit, VisitAmendment, MedicalReview, Procedure, TreatmentPlan, PlanItem,
                     PerformedWork, ToothObservation, Attachment)
from .teeth import TEETH

MEDICAL_FIELDS = ['medical_history', 'current_medicines', 'allergies', 'medical_alerts']
HISTORY_STATES = [('not_recorded', 'Not recorded'), ('none', 'Patient reports none'), ('details', 'Details recorded')]

class MedicalReviewForm(forms.Form):
    reason = forms.CharField(max_length=240, label='Reason for review / change')
    for key in MEDICAL_FIELDS:
        locals()[key + '_state'] = forms.ChoiceField(choices=HISTORY_STATES, label=key.replace('_', ' ').title() + ' status')
        locals()[key] = forms.CharField(required=False, max_length=20000, widget=forms.Textarea(attrs={'rows': 3}), label=key.replace('_', ' ').title())
    del key

    def clean(self):
        data = super().clean()
        for key in MEDICAL_FIELDS:
            state, details = data.get(key + '_state'), data.get(key, '')
            if state == 'details' and not details:
                self.add_error(key, 'Record the details, or choose Not recorded / Patient reports none.')
            elif state != 'details' and details:
                self.add_error(key, 'Select Details recorded when supplying details.')
        return data

    def snapshot(self):
        return {key: {'state': self.cleaned_data[key + '_state'], 'details': self.cleaned_data[key]} for key in MEDICAL_FIELDS}


class TeethFormMixin:
    def setup_teeth(self):
        self.fields['teeth'] = forms.MultipleChoiceField(choices=[(t, t) for t in TEETH], required=False,
            help_text='Select multiple FDI teeth. Leave teeth empty for general treatment and optionally describe the area.')


class VisitForm(TeethFormMixin, forms.ModelForm):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    medical_reviewed = forms.BooleanField(label='I reviewed the medical history and alerts shown for this visit.')

    class Meta:
        model = Visit
        fields = ['visit_at', 'clinician', 'chief_complaint', 'examination', 'diagnosis', 'teeth', 'area',
                  'planned_treatment', 'performed_treatment', 'advice', 'remaining_work', 'follow_up', 'status']
        widgets = {'visit_at': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}),
                   'follow_up': forms.DateInput(attrs={'type': 'date'}),
                   **{name: forms.Textarea(attrs={'rows': 3, 'maxlength': 20000}) for name in ['chief_complaint', 'examination', 'diagnosis', 'planned_treatment', 'performed_treatment', 'advice', 'remaining_work']}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_teeth()
        self.fields['clinician'].queryset = User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(groups__name='Doctor')).distinct()
        self.fields['status'].choices = [('draft', 'Draft'), ('in_progress', 'In Progress')]
        self.fields['visit_at'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S']
        self.initial.setdefault('revision', self.instance.revision if self.instance.pk else 0)
        self.initial.setdefault('medical_reviewed', bool(self.instance.pk))

    def clean_follow_up(self):
        date = self.cleaned_data['follow_up']
        if date and self.cleaned_data.get('visit_at') and date < timezone.localtime(self.cleaned_data['visit_at']).date():
            raise forms.ValidationError('Follow-up cannot be earlier than the visit date.')
        return date


class AmendmentForm(forms.ModelForm):
    class Meta:
        model = VisitAmendment
        fields = ['reason', 'content']
        widgets = {'content': forms.Textarea(attrs={'rows': 5})}


class ProcedureForm(forms.ModelForm):
    class Meta:
        model = Procedure
        fields = ['name', 'description', 'active']


class PlanForm(forms.ModelForm):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)
    class Meta:
        model = TreatmentPlan
        fields = ['title', 'notes']


class PlanItemForm(TeethFormMixin, forms.ModelForm):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)
    class Meta:
        model = PlanItem
        fields = ['procedure', 'teeth', 'area', 'notes', 'status', 'target_date']
        widgets = {'target_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_teeth()
        self.fields['procedure'].queryset = Procedure.objects.filter(Q(active=True) | Q(pk=self.instance.procedure_id))


class WorkForm(TeethFormMixin, forms.ModelForm):
    class Meta:
        model = PerformedWork
        fields = ['procedure', 'plan_item', 'teeth', 'area', 'notes']

    def __init__(self, *args, patient, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_teeth()
        self.fields['procedure'].queryset = Procedure.objects.filter(active=True)
        self.fields['plan_item'].queryset = PlanItem.objects.filter(plan__patient=patient).select_related('plan', 'procedure')


class ObservationForm(TeethFormMixin, forms.ModelForm):
    class Meta:
        model = ToothObservation
        fields = ['visit', 'teeth', 'area', 'observation']

    def __init__(self, *args, patient, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_teeth()
        self.fields['visit'].queryset = patient.visits.exclude(status='completed')


class AttachmentForm(TeethFormMixin, forms.ModelForm):
    file = forms.FileField(help_text='JPEG, PNG or passive PDF only. Maximum 10 MiB by default; image limits also apply.')
    class Meta:
        model = Attachment
        fields = ['visit', 'category', 'title', 'description', 'taken_on', 'teeth', 'area']
        widgets = {'taken_on': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, patient, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_teeth()
        self.fields['visit'].queryset = patient.visits.all()

    def clean_taken_on(self):
        date = self.cleaned_data['taken_on']
        if date and date > timezone.localdate():
            raise forms.ValidationError('Date taken cannot be in the future.')
        return date
