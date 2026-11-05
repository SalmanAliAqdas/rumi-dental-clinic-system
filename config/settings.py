"""Offline development settings. Runtime state lives outside the source tree."""
import os
from pathlib import Path
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get('RUMI_DATA_DIR', Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'RumiDentalCare'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
key_file = DATA_DIR / 'secret.key'
try:
    with key_file.open('x', encoding='utf-8') as handle:
        handle.write(get_random_secret_key())
except FileExistsError:
    pass
SECRET_KEY = key_file.read_text(encoding='utf-8').strip()
DEBUG = False
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
# Clinic precedes staticfiles so its guarded runserver command is selected.
INSTALLED_APPS = ['clinic', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'clinic.middleware.PrivacyMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': DATA_DIR / 'clinic.sqlite3', 'OPTIONS': {'timeout': 20}}}
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'en-gb'
TIME_ZONE = 'Asia/Karachi'
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SAMESITE = 'Strict'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
# Suppress request paths (including accidental query strings) in ordinary logs.
LOGGING = {'version': 1, 'disable_existing_loggers': False, 'handlers': {'null': {'class': 'logging.NullHandler'}}, 'loggers': {name: {'handlers': ['null'], 'propagate': False} for name in ['django.server', 'django.request', 'django.security']}}
