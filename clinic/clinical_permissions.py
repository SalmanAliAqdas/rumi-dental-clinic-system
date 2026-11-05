DOCTOR_MODELS = {
    'patient': ['view', 'add', 'change'], 'visit': ['view', 'add', 'change'],
    'medicalreview': ['view', 'add'], 'visitamendment': ['view', 'add'],
    'procedure': ['view', 'add', 'change'], 'treatmentplan': ['view', 'add', 'change'],
    'planitem': ['view', 'add', 'change'], 'planrevision': ['view'],
    'performedwork': ['view', 'add'], 'toothobservation': ['view', 'add'], 'attachment': ['view', 'add'],
}
DOCTOR_PERMISSIONS = [f'{action}_{model}' for model, actions in DOCTOR_MODELS.items() for action in actions]
