"""Optional Playwright smoke check. Uses an isolated, temporary fictional clinic."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
import sqlite3
from contextlib import closing
from urllib.request import urlopen
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from finance_browser import check_finance

def check_clinical(page, context, base, password, image_path, database, width):
    page.get_by_role('link', name='+ Start Visit', exact=True).click()
    page.get_by_label('Chief complaint', exact=True).fill('Fictional first clinical complaint')
    page.get_by_label('I reviewed the medical history and alerts shown for this visit.', exact=True).check()
    page.locator('input[name="teeth"][value="11"]').check()
    page.locator('input[name="teeth"][value="55"]').check()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.get_by_role('button', name='Start In Progress / Draft', exact=True).click()
    visit_url = page.url
    visit_id = int(urlsplit(visit_url).path.strip('/').split('/')[-1])
    page.get_by_role('link', name='Continue Visit', exact=True).click()
    page.get_by_label('Examination', exact=True).fill('Fictional persisted examination')
    page.wait_for_function("() => Number(document.querySelector('[name=revision]').value) > 0 && document.querySelector('#save-state').textContent.startsWith('Saved ')")
    def persisted():
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
            return connection.execute('SELECT examination,revision FROM clinic_visit WHERE id=?', (visit_id,)).fetchone()
    assert persisted()[0] == 'Fictional persisted examination'
    stale = context.new_page()
    stale.goto(page.url)
    old_revision = int(page.locator('[name=revision]').input_value())
    page.get_by_label('Examination', exact=True).fill('Fictional newer revision')
    page.wait_for_function('(old) => Number(document.querySelector("[name=revision]").value) > old && document.querySelector("#save-state").textContent.startsWith("Saved ")', arg=old_revision)
    stale.get_by_label('Examination', exact=True).fill('Fictional stale notes retained')
    stale.locator('#save-state').filter(has_text='Failed').wait_for()
    assert stale.get_by_label('Examination', exact=True).input_value() == 'Fictional stale notes retained'
    assert persisted()[0] == 'Fictional newer revision'
    stale.close()
    context.clear_cookies(name='sessionid')
    page.get_by_label('Examination', exact=True).fill('Fictional notes retained after expired session')
    page.locator('#save-state').filter(has_text='Failed').wait_for()
    assert page.get_by_label('Examination', exact=True).input_value() == 'Fictional notes retained after expired session'
    login = context.new_page()
    login.goto(base + '/login/')
    login.get_by_label('Username').fill('browserdoctor')
    login.get_by_label('Password').fill(password)
    login.get_by_role('button', name='Sign in', exact=True).click()
    login.wait_for_url(base + '/')
    login.close()
    page.get_by_role('button', name='Retry draft save', exact=True).click()
    page.locator('#save-state').filter(has_text='Saved').wait_for()
    assert persisted()[0] == 'Fictional notes retained after expired session'
    page.get_by_role('link', name='Back to record', exact=True).click()
    page.get_by_role('link', name='Record performed procedure', exact=True).click()
    page.get_by_label('Procedure').select_option(index=1)
    page.locator('input[name="teeth"][value="11"]').check()
    page.get_by_label('Notes', exact=True).fill('Fictional staged procedure')
    page.get_by_role('button', name='Save', exact=True).click()
    page.get_by_role('link', name='Upload private attachment', exact=True).click()
    page.get_by_label('Visit', exact=True).select_option(str(visit_id))
    page.get_by_label('Category').select_option('photo')
    page.get_by_label('Title').fill('Fictional clinical image')
    page.get_by_label('File').set_input_files(str(image_path))
    page.get_by_role('button', name='Save', exact=True).click()
    page.get_by_role('heading', name='Fictional clinical image', exact=True).wait_for()
    page.wait_for_function('() => Array.from(document.querySelectorAll(".attachment-thumb")).every(img => img.complete && img.naturalWidth > 0)')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.goto(visit_url)
    page.get_by_role('link', name='Continue Visit', exact=True).click()
    page.get_by_label('Performed treatment', exact=True).fill('Fictional completed clinical work')
    page.get_by_role('button', name='Complete Visit', exact=True).click()
    page.get_by_role('link', name='Add amendment', exact=True).wait_for()
    page.get_by_role('link', name='Add amendment', exact=True).click()
    page.get_by_label('Reason').fill('Fictional clarification')
    page.get_by_label('Content').fill('Fictional dated amendment retaining originals')
    page.get_by_role('button', name='Save', exact=True).click()
    page.get_by_text('Fictional dated amendment retaining originals', exact=True).wait_for()
    page.get_by_role('link', name='+ Start Visit', exact=True).click()
    page.get_by_label('Chief complaint', exact=True).fill('Fictional return visit complaint')
    page.get_by_label('I reviewed the medical history and alerts shown for this visit.', exact=True).check()
    page.get_by_role('button', name='Start In Progress / Draft', exact=True).click()
    assert page.url != visit_url
    page.get_by_role('link', name='Visits', exact=True).click()
    page.locator('a[href="' + urlsplit(visit_url).path + '"]').click()
    page.get_by_text('Fictional completed clinical work', exact=True).wait_for()
    page.get_by_text('Fictional dated amendment retaining originals', exact=True).wait_for()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(ROOT / 'runtime' / f'clinical-{width}.png'), full_page=True)
    print(f'PASS: Doctor clinical return workflow at {width}px, database-confirmed draft, stale-tab rejection, expired-session recovery, teeth/procedure, private image thumbnail, completion, amendment, return visit and old history', flush=True)

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / '.venv' / 'Scripts' / 'python.exe'
if not PYTHON.exists():
    PYTHON = ROOT / '.venv' / 'bin' / 'python'

def run():
    (ROOT / 'runtime').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='browser-', dir=ROOT / 'runtime') as data_dir:
        env = dict(os.environ, RUMI_DATA_DIR=data_dir, RUMI_BROWSER_PASSWORD=secrets.token_urlsafe(30))
        subprocess.run([str(PYTHON), 'manage.py', 'migrate', '--noinput'], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
        image_path = Path(data_dir) / 'fictional.png'
        env['RUMI_BROWSER_IMAGE'] = str(image_path)
        seed = "import os,django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup(); from django.contrib.auth.models import User; from clinic.views import doctor_group; u=User.objects.create_user('browserdoctor',password=os.environ['RUMI_BROWSER_PASSWORD']); u.groups.add(doctor_group()); User.objects.create_superuser('browserowner',password=os.environ['RUMI_BROWSER_PASSWORD']); from PIL import Image; Image.new('RGB',(32,32),color='blue').save(os.environ['RUMI_BROWSER_IMAGE'])"
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
                cases = [
                    (1440, 'browserowner', '03001234567', '00923001234567'),
                    (390, 'browserowner', '+442079460958', '00442079460958'),
                    (1440, 'browserdoctor', '03011234567', '00923011234567'),
                    (390, 'browserdoctor', '+12025550123', '0012025550123'),
                ]
                for width, username, phone, alternate in cases:
                    context = browser.new_context(viewport={'width': width, 'height': 1000})
                    # Block any external traffic: every asset must be served locally.
                    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/') else route.abort())
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '/login/')
                    page.get_by_label('Username').fill(username)
                    page.get_by_label('Password').fill(env['RUMI_BROWSER_PASSWORD'])
                    page.get_by_role('button', name='Sign in', exact=True).click()
                    page.wait_for_url(base + '/')
                    page.get_by_role('heading', name='Clinic dashboard', exact=True).wait_for()
                    page.get_by_role('link', name='+ Register patient', exact=True).click()
                    name = f'Fictional {username} Patient {width}'
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
                    page.screenshot(path=str(ROOT / 'runtime' / f'profile-{username}-{width}.png'), full_page=True)
                    expected = 200 if username == 'browserowner' else 403
                    assert page.request.get(base + '/accounts/').status == expected
                    assert page.request.get(base + '/audit/').status == expected
                    check_finance(page, base, profile_url, username, width, ROOT)
                    if username == 'browserdoctor':
                        check_clinical(page, context, base, env['RUMI_BROWSER_PASSWORD'], image_path, Path(data_dir) / 'clinic.sqlite3', width)
                    page.get_by_role('button', name='Log out', exact=True).click()
                    page.wait_for_url(base + '/login/')
                    page.goto(profile_url)
                    page.wait_for_url('**/login/?next=**')
                    assert not errors, errors
                    context.close()
                    print(f'PASS: {username} at {width}px login -> dashboard -> register -> alternate-format search -> profile -> edit -> logout; local assets, no overflow, account/audit permissions correct', flush=True)
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=15)

if __name__ == '__main__':
    run()
