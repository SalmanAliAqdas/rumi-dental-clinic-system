from django.utils.cache import add_never_cache_headers

class PrivacyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith('/static/'):
            add_never_cache_headers(response)
            response['Referrer-Policy'] = 'same-origin'
            response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
            response['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        return response
