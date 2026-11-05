from getpass import getpass
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from clinic.views import doctor_group

class Command(BaseCommand):
    help = 'Create a Doctor with patient permissions only; password is entered securely.'

    def add_arguments(self, parser):
        parser.add_argument('username')

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username']
        try:
            User._meta.get_field('username').run_validators(username)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages))
        if User.objects.filter(username=username).exists():
            raise CommandError('Username already exists.')
        password = getpass('Doctor password: ')
        if password != getpass('Confirm password: '):
            raise CommandError('Passwords do not match.')
        user = User(username=username)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages))
        with transaction.atomic():
            user.set_password(password)
            user.save()
            user.groups.add(doctor_group())
        self.stdout.write(self.style.SUCCESS('Doctor created; no staff or superuser access.'))
