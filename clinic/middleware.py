from django.utils.cache import add_never_cache_headers
import uuid

class PrivacyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def process_exception(self, request, exception):
        request._rumi_error_id = uuid.uuid4().hex

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code >= 500 and hasattr(request, '_rumi_error_id'):
            response['X-Rumi-Error-ID'] = request._rumi_error_id
        if not request.path.startswith('/static/'):
            add_never_cache_headers(response)
            response['Referrer-Policy'] = 'same-origin'
            response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
            if 'Content-Security-Policy' not in response:
                response['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        return response


from django.contrib.sessions.middleware import SessionMiddleware
from django.utils.cache import patch_vary_headers

class ClinicSessionMiddleware(SessionMiddleware):
    def process_response(self, request, response):
        # Status polling is not user activity and must not prolong Owner login.
        session = getattr(request, 'session', None)
        if (request.path.startswith('/backups/jobs/') and request.path.endswith('/status/')
                and session is not None and not session.modified and not session.is_empty()):
            if session.accessed:
                patch_vary_headers(response, ('Cookie',))
            return response
        return super().process_response(request, response)
