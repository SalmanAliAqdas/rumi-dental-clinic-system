from django.db import migrations

def seed_lock(apps, schema_editor):
    apps.get_model('clinic','FinancialLock').objects.using(schema_editor.connection.alias).get_or_create(pk=1)

class Migration(migrations.Migration):
    dependencies = [('clinic','0004_financiallock_schedule_installment_treatmentaccount_and_more')]
    operations = [migrations.RunPython(seed_lock, migrations.RunPython.noop)]
