"""Visible diagnostic server for an explicitly selected runtime."""
import os
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Serve the selected clinic on loopback using Waitress; normal desktop startup uses its fixed runtime.'

    def add_arguments(self, parser):
        parser.add_argument('--port', type=int, default=8000)

    def handle(self, *args, **options):
        if not os.environ.get('RUMI_DATA_DIR'):
            raise CommandError('Set RUMI_DATA_DIR explicitly before diagnostic startup.')
        from clinic.management.commands.runserver import Command as Guard
        Guard().check_migrations()
        from clinic.local_server import serve
        serve(port=options['port'])
