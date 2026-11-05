"""Optional Playwright smoke check. Uses an isolated, temporary fictional clinic."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / '.venv' / 'Scripts' / 'python.exe'
if not PYTHON.exists():
    PYTHON = ROOT / '.venv' / 'bin' / 'python'

def run():
    (ROOT / 'runtime').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='browser-', dir=ROOT / 'runtime') as data_dir:
        env = dict(os.environ, RUMI_DATA_DIR=data_dir, RUMI_BROWSER_PASSWORD=secrets.token_urlsafe(30))
        subprocess.run([str(PYTHON), 'manage.py', 'migrate', '--noinput'], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
        seed = "import os,django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup(); from django.contrib.auth.models import User; from clinic.views import doctor_group; u=User.objects.create_user('browserdoctor',password=os.environ['RUMI_BROWSER_PASSWORD']); u.groups.add(doctor_group())"
        subprocess.run([str(PYTHON), '-c', seed], cwd=ROOT, env=env, check=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        server = subprocess.Popen([str(PYTHON), 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload', '--insecure'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(30):
                if server.poll() is not None:
                    raise RuntimeError('Local test server exited before startup.')
                try:
                    if urlopen(base + '/login/', timeout=1).status == 200:
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Local test server did not start.')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                for width in [1440, 390]:
                    context = browser.new_context(viewport={'width': width, 'height': 1000})
                    # Block any external traffic: every asset must be served locally.
                    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/') else route.abort())
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '/login/')
                    page.get_by_label('Username').fill('browserdoctor')
                    page.get_by_label('Password').fill(env['RUMI_BROWSER_PASSWORD'])
                    page.get_by_role('button', name='Sign in', exact=True).click()
                    page.wait_for_url(base + '/')
                    page.get_by_role('link', name='+ Register patient', exact=True).click()
                    name = f'Fictional Browser Patient {width}'
                    phone = '03001234567' if width == 1440 else '+442079460958'
                    alternate = '00923001234567' if width == 1440 else '00442079460958'
                    page.get_by_label('Full name').fill(name)
                    page.get_by_label('Primary phone number').fill(phone)
                    page.get_by_label('Approximate age').fill('32')
                    page.get_by_label('Allergies', exact=True).fill('None confirmed')
                    page.get_by_role('button', name='Register patient', exact=True).click()
                    page.get_by_role('heading', name=name, exact=True).wait_for()
                    profile_url = page.url
                    page.get_by_role('link', name='Find a patient', exact=True).click()
                    page.get_by_label('Phone number, patient name or patient number').fill(alternate)
                    page.get_by_role('button', name='Find patient', exact=True).click()
                    page.get_by_role('link').filter(has_text=name).click()
                    assert page.url == profile_url
                    page.get_by_role('link', name='Edit patient', exact=True).click()
                    page.get_by_label('Occupation').fill('Fictional browser test')
                    page.get_by_role('button', name='Save changes', exact=True).click()
                    page.get_by_text('Fictional browser test', exact=True).wait_for()
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), f'Overflow at {width}px'
                    assert page.locator('h1').evaluate("el => getComputedStyle(el).fontFamily").startswith('"Segoe UI"')
                    page.screenshot(path=str(ROOT / 'runtime' / f'profile-{width}.png'), full_page=True)
                    assert page.request.get(base + '/accounts/').status == 403
                    page.get_by_role('button', name='Log out', exact=True).click()
                    page.wait_for_url(base + '/login/')
                    page.goto(profile_url)
                    page.wait_for_url('**/login/?next=**')
                    assert not errors, errors
                    context.close()
                    print(f'PASS: {width}px login -> register -> alternate-format search -> profile -> edit -> logout; local assets, no horizontal overflow, Doctor denied accounts')
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=15)

if __name__ == '__main__':
    run()
