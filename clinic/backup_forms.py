from django import forms
from .finance_forms import TokenForm
from .workflow_forms import RevisionForm

class DestinationForm(RevisionForm):
    label=forms.CharField(max_length=100)
    kind=forms.ChoiceField(choices=[('local','Local folder / drive'),('external','External USB folder / drive'),('gdrive','Existing Google Drive synchronized folder')])
    folder=forms.CharField(max_length=1000,label='Absolute existing destination folder',help_text='Create/select the folder in Windows Explorer, then copy its full path here. A browser cannot silently choose folders. Missing drives never fall back to another folder.')

    staging_folder=forms.CharField(required=False,max_length=1000,label='Unsynchronized staging folder (required for Google Drive)',help_text='Choose an existing folder outside Google Drive on the same volume. Only completed encrypted packages are moved into the selected sync folder.')

class AutomaticForm(RevisionForm):
    automatic=forms.BooleanField(required=False,label='Enable daily backups while this application is running')
    daily_time=forms.TimeField(widget=forms.TimeInput(format='%H:%M',attrs={'type':'time'}),label='Daily time (Asia/Karachi)')
    keep_last=forms.IntegerField(min_value=2,max_value=365,label='Verified dated versions to retain per destination')
    recovery_password=forms.CharField(required=False,strip=False,max_length=1024,widget=forms.PasswordInput,help_text='At least 12 characters for a new password. Saved only with Windows user-bound DPAPI; no plaintext fallback. Leave blank to keep the existing protected credential.')
    confirm_password=forms.CharField(required=False,strip=False,max_length=1024,widget=forms.PasswordInput)
    def clean(self):
        data=super().clean()
        if data.get('recovery_password')!=data.get('confirm_password'):self.add_error('confirm_password','Passwords must match.')
        return data

class BackupForm(TokenForm):
    recovery_password=forms.CharField(strip=False,min_length=12,max_length=1024,widget=forms.PasswordInput,label='Backup recovery password')
    confirm_password=forms.CharField(strip=False,max_length=1024,widget=forms.PasswordInput,label='Confirm recovery password')
    def clean(self):
        data=super().clean()
        if data.get('recovery_password')!=data.get('confirm_password'):self.add_error('confirm_password','Passwords must match.')
        return data

class VerifyForm(TokenForm):
    package=forms.CharField(max_length=1000,label='Encrypted package full path')
    recovery_password=forms.CharField(strip=False,max_length=1024,widget=forms.PasswordInput)

class RestorePreviewForm(VerifyForm):
    owner_password=forms.CharField(strip=False,max_length=1024,widget=forms.PasswordInput,label='Your current Owner login password')
    confirmed=forms.BooleanField(label='I understand restore replaces the selected runtime, never merges it, and requires the stopped-server local helper. Preview does not replace working data.')
