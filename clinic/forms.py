from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Patient
from .phones import normalize_phone

class PatientForm(forms.ModelForm):
    phone = forms.CharField(max_length=64, label='Primary phone number')
    whatsapp = forms.CharField(max_length=64, required=False, label='WhatsApp number')
    confirm_shared_phone = forms.BooleanField(required=False, label='I reviewed these matches. Register this additional patient with the shared number.')

    class Meta:
        model = Patient
        fields = ['full_name', 'phone', 'whatsapp', 'date_of_birth', 'approximate_age', 'address', 'occupation', 'emergency_contact', 'allergies', 'medical_alerts', 'medical_history', 'current_medicines']
        widgets = {'date_of_birth': forms.DateInput(attrs={'type': 'date'}), **{field: forms.Textarea(attrs={'rows': 3}) for field in ['address', 'allergies', 'medical_alerts', 'medical_history', 'current_medicines']}}

    def clean_phone(self):
        return normalize_phone(self.cleaned_data['phone'])

    def clean_whatsapp(self):
        value = self.cleaned_data.get('whatsapp')
        return normalize_phone(value) if value else ''

    def clean_full_name(self):
        value = self.cleaned_data['full_name'].strip()
        if len(value) < 2:
            raise forms.ValidationError('Enter a name of at least two characters.')
        return value

    def clean(self):
        data = super().clean()
        dob, age = data.get('date_of_birth'), data.get('approximate_age')
        today = timezone.localdate()
        years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day)) if dob else None
        if dob and (dob > today or years > 120):
            self.add_error('date_of_birth', 'Enter a birth date in the past, within 120 years.')
        if dob and age is not None:
            self.add_error('approximate_age', 'Enter a birth date OR approximate age, not both.')
        self.duplicates = Patient.objects.none()
        if data.get('phone'):
            from django.db.models import Q
            self.duplicates = Patient.objects.filter(Q(phone=data['phone']) | Q(whatsapp=data['phone'])).exclude(pk=self.instance.pk)
            if self.duplicates.exists() and not data.get('confirm_shared_phone'):
                self.add_error(None, 'Possible duplicate: review the patients below, then confirm if this is another family member.')
        return data

    def save(self, commit=True):
        patient = super().save(commit=False)
        age_changed = 'approximate_age' in self.changed_data or not patient.age_recorded_on
        patient.age_recorded_on = (timezone.localdate() if age_changed else patient.age_recorded_on) if patient.approximate_age is not None else None
        if commit:
            patient.save()
        return patient

class DoctorCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name']
