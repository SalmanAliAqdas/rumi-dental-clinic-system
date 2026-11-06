from django.db import migrations

def seed(apps,schema_editor):
    apps.get_model('clinic','WorkflowLock').objects.using(schema_editor.connection.alias).get_or_create(pk=1)

class Migration(migrations.Migration):
    dependencies=[('clinic','0006_clinicprintsettings_workflowlock_appointment_and_more')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop)]
