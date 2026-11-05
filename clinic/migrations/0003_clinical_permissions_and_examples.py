from django.db import migrations


def seed(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Procedure = apps.get_model('clinic', 'Procedure')
    allowed = {
        'patient': ['view', 'add', 'change'], 'visit': ['view', 'add', 'change'],
        'medicalreview': ['view', 'add'], 'visitamendment': ['view', 'add'],
        'procedure': ['view', 'add', 'change'], 'treatmentplan': ['view', 'add', 'change'],
        'planitem': ['view', 'add', 'change'], 'planrevision': ['view'],
        'performedwork': ['view', 'add'], 'toothobservation': ['view', 'add'], 'attachment': ['view', 'add'],
    }
    group, _ = Group.objects.get_or_create(name='Doctor')
    for model, actions in allowed.items():
        content_type, _ = ContentType.objects.get_or_create(app_label='clinic', model=model)
        for action in actions:
            permission, _ = Permission.objects.get_or_create(content_type=content_type, codename=f'{action}_{model}', defaults={'name': f'Can {action} {model}'})
            group.permissions.add(permission)
    for name in ['Examination', 'Scaling', 'Restoration', 'Root canal treatment', 'Extraction', 'Crown']:
        Procedure.objects.get_or_create(name='Example: ' + name, defaults={'is_example': True, 'description': 'Starter example only. Review and adapt to the clinic catalogue. No price.'})


class Migration(migrations.Migration):
    dependencies = [('clinic', '0002_procedure_auditevent_object_id_and_more')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
