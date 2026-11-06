"""Isolated browser verification for Owner backup controls and Doctor denial."""
import os,secrets,socket,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from playwright.sync_api import sync_playwright
from backup_fixture import seed
from backup_browser import check_backups
ROOT=Path(__file__).resolve().parent.parent
PYTHON=ROOT/'.venv/Scripts/python.exe'
if not PYTHON.exists():PYTHON=ROOT/'.venv/bin/python'

def run():
    with tempfile.TemporaryDirectory(prefix='backup-ui-',dir=ROOT/'runtime') as temp:
        root=Path(temp);data=root/'data';destination=root/'destination';destination.mkdir()
        password=seed(data);recovery=secrets.token_urlsafe(30)
        env={**os.environ,'RUMI_DATA_DIR':str(data),'DJANGO_SETTINGS_MODULE':'config.settings','RUMI_DISABLE_BACKUP_SCHEDULER':'1'}
        # Fixture account names are different from the original browser helper's.
        # A trusted local seed creates aliases only in this isolated directory.
        code="import django;django.setup();from django.contrib.auth.models import User;User.objects.filter(username='recoveryowner').update(username='browserowner');User.objects.filter(username='recoverydoctor').update(username='browserdoctor')"
        subprocess.run([str(PYTHON),'-c',code],cwd=ROOT,env=env,check=True)
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        process=subprocess.Popen([str(PYTHON),'manage.py','runserver',f'127.0.0.1:{port}','--noreload','--insecure'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    if build_opener(ProxyHandler({})).open(base+'/login/',timeout=1).status==200:break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Fixture server did not start.')
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                for width,user in [(1440,'browserowner'),(390,'browserowner'),(390,'browserdoctor')]:
                    context=browser.new_context(viewport={'width':width,'height':1000})
                    context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(base+'/login/');page.get_by_label('Username').fill(user);page.get_by_label('Password').fill(password);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(base+'/')
                    try:
                        check_backups(page,base,user,width,destination,recovery,password)
                        assert not errors,errors
                    except Exception:
                        print('Fixture-only progress diagnostics:',page.url,page.locator('#backup-state').all_text_contents(),page.locator('#backup-stage').all_text_contents(),page.locator('.errorlist').all_text_contents(),errors,flush=True)
                        for f in (data/'backup-control/jobs').glob('*.json'):
                            import json
                            job=json.loads(f.read_text());print('Fixture job state:',job['kind'],job['status'],job['stage'],flush=True)
                        for f in (data/'diagnostics').glob('*.log'):print('Safe fixture diagnostics:',f.read_text(),flush=True)
                        raise
                    context.close()
                browser.close()
        finally:process.terminate();process.wait(timeout=15)

if __name__=='__main__':run()
