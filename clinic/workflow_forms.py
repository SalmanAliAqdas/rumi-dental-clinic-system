from django import forms
from django.forms import formset_factory
from django.utils import timezone
from .finance_forms import TokenForm
from .models import Visit
from .workflow_models import STATUSES

DT_WIDGET = forms.DateTimeInput(format='%Y-%m-%dT%H:%M',attrs={'type':'datetime-local'})

class RevisionForm(TokenForm):
    revision = forms.IntegerField(min_value=0,widget=forms.HiddenInput,initial=0)

class AppointmentForm(RevisionForm):
    starts_at = forms.DateTimeField(widget=DT_WIDGET,label='Start date/time (Pakistan)')
    ends_at = forms.DateTimeField(widget=DT_WIDGET,label='End date/time (Pakistan)')
    purpose = forms.CharField(max_length=240)
    notes = forms.CharField(required=False,max_length=20000,widget=forms.Textarea(attrs={'rows':3}))
    reason = forms.CharField(required=False,max_length=240,label='Reason for change / rescheduling')
    overlap_confirm = forms.BooleanField(required=False,label='I reviewed the conflicting bookings and intentionally confirm this overlap')
    overlap_reason = forms.CharField(required=False,max_length=240,label='Reason for intentional overlap')
    arrived_at = forms.DateTimeField(required=False,widget=DT_WIDGET,label='Walk-in arrival time (blank means now)')
    def clean(self):
        data=super().clean()
        if data.get('starts_at') and data.get('ends_at') and data['ends_at']<=data['starts_at']:
            self.add_error('ends_at','End must be after start.')
        return data

class StatusForm(RevisionForm):
    status = forms.ChoiceField(choices=STATUSES)
    reason = forms.CharField(max_length=240)
    queue_at = forms.DateTimeField(required=False,widget=DT_WIDGET,label='Optional explicit queue ordering time (Arrived only)')
    overlap_confirm = forms.BooleanField(required=False,label='I intentionally confirm an overlap when reactivating this booking')
    overlap_reason = forms.CharField(required=False,max_length=240)

class StartVisitForm(RevisionForm):
    reviewed = forms.BooleanField(label='I reviewed this patient medical history and alerts before starting the visit')
    existing_visit = forms.ModelChoiceField(queryset=Visit.objects.none(),required=False,label='Optional existing editable visit (otherwise create one)')
    def __init__(self,*args,patient,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['existing_visit'].queryset=patient.visits.exclude(status='completed').filter(appointment__isnull=True)

class TaskForm(RevisionForm):
    title = forms.CharField(max_length=160)
    notes = forms.CharField(required=False,max_length=20000,widget=forms.Textarea(attrs={'rows':4}))
    due_at = forms.DateTimeField(required=False,widget=DT_WIDGET,label='Due date/time (optional, Pakistan)')

class ConfirmForm(RevisionForm):
    confirmed = forms.BooleanField(label='I reviewed the patient, allergies, medication details and clinician identity and confirm issuance')

class CorrectionForm(TokenForm):
    reason = forms.CharField(max_length=240)
    action = forms.ChoiceField(choices=[('replace','Void original and create replacement draft'),('void','Void without replacement')])

class PrescriptionForm(RevisionForm):
    prescribed_on = forms.DateField(initial=timezone.localdate,widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}),label='Prescription date')
    visit = forms.ModelChoiceField(queryset=Visit.objects.none(),required=False)
    advice = forms.CharField(required=False,max_length=20000,widget=forms.Textarea(attrs={'rows':3}),label='General advice (entered by Doctor)')
    follow_up = forms.CharField(required=False,max_length=240)
    def __init__(self,*args,patient,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['visit'].queryset=patient.visits.all()

class MedicationForm(forms.Form):
    name = forms.CharField(required=False,max_length=160,label='Medication name')
    strength_form = forms.CharField(required=False,max_length=160,label='Strength / form')
    dose = forms.CharField(required=False,max_length=160)
    route = forms.CharField(required=False,max_length=160)
    frequency = forms.CharField(required=False,max_length=160)
    duration = forms.CharField(required=False,max_length=160)
    quantity = forms.CharField(required=False,max_length=160)
    instructions = forms.CharField(required=False,max_length=2000,widget=forms.Textarea(attrs={'rows':2}))
    def __init__(self,*args,**kwargs):
        kwargs.setdefault('label_suffix','')
        super().__init__(*args,**kwargs)
    def clean(self):
        data=super().clean()
        if any(v for k,v in data.items() if k!='DELETE') and not data.get('name'):
            self.add_error('name','Enter the medication name or clear this unused row.')
        return data

MedicationFormSet=formset_factory(MedicationForm,extra=1,can_delete=True,max_num=20,validate_max=True,absolute_max=21)

class ClinicSettingsForm(RevisionForm):
    name = forms.CharField(max_length=160,label='Clinic name')
    address = forms.CharField(required=False,max_length=240)
    contact = forms.CharField(required=False,max_length=160)

class PrescriberForm(RevisionForm):
    display_name = forms.CharField(max_length=160,label='Your actual prescribing clinician name')
    qualifications = forms.CharField(required=False,max_length=240,help_text='Enter only your actual details; leave blank if not supplied.')
    registration = forms.CharField(required=False,max_length=160)
    contact = forms.CharField(required=False,max_length=160)

class ReminderForm(TokenForm):
    confirmed_fallback = forms.BooleanField(required=False,label='I confirm the primary phone is appropriate for this WhatsApp reminder')
    activity = forms.ChoiceField(choices=[('prepare','Review only / enable confirmed fallback'),('copied','I copied the reminder'),('sent','I manually sent the reminder')])
