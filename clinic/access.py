from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

def clinic_required(permission='view_patient', owner=False):
    def decorate(view):
        @login_required
        @wraps(view)
        def guarded(request, *args, **kwargs):
            if owner:
                allowed = request.user.is_superuser
            else:
                allowed = request.user.has_perm(f'clinic.{permission}')
            if not allowed:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return guarded
    return decorate
