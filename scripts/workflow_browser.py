"""Fictional Phase 4 browser checks; never contacts WhatsApp or prescribes real drugs."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

def check_workflow(page,context,base,profile_url,username,width,root,password):
    purpose=f'Fictional appointment {username} {width}'
    page.goto(profile_url)
    patient_name=page.locator('h1').inner_text()
    page.get_by_role('link',name='Book appointment',exact=True).click()
    start=datetime.now(ZoneInfo('Asia/Karachi')).replace(second=0,microsecond=0)+timedelta(minutes=10)
    page.get_by_label('Start date/time (Pakistan)',exact=True).fill(start.strftime('%Y-%m-%dT%H:%M'))
    page.get_by_label('End date/time (Pakistan)',exact=True).fill((start+timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M'))
    page.get_by_label('Purpose',exact=True).fill(purpose)
    page.get_by_role('button',name='Save',exact=True).click()
    appointment_url=page.url
    page.get_by_role('link',name='Print appointment slip',exact=True).click()
    assert page.locator('body').evaluate('e => getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)'
    assert page.get_by_text(patient_name,exact=True).count()==1
    assert page.get_by_role('navigation').count()==0
    page.get_by_role('link',name='Return to appointment',exact=True).click()
    page.get_by_role('link',name='Prepare reminder',exact=True).click()
    assert page.get_by_role('link',name='Open WhatsApp',exact=True).count()==0
    page.get_by_label('I confirm the primary phone is appropriate for this WhatsApp reminder',exact=True).check()
    page.get_by_label('Activity',exact=True).select_option('prepare')
    page.get_by_role('button',name='Save user-confirmed activity / review fallback',exact=True).click()
    assert page.get_by_role('link',name='Open WhatsApp',exact=True).get_attribute('href').startswith('https://wa.me/')
    assert purpose not in page.locator('#reminder-text').input_value()
    page.goto(base+'/')
    assert page.locator('#daily-panels').get_by_text(purpose,exact=False).count()>0
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(root/'runtime'/f'dashboard-phase4-active-{username}-{width}.png'),full_page=True)
    # A midnight refresh replaces only the panel, retaining phone-search input.
    search=page.get_by_label('Phone number, patient name or patient number')
    search.fill('Fictional retained search')
    page.evaluate("document.querySelector('[data-business-date]').dataset.businessDate='2000-01-01'")
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_function("() => !!document.querySelector('#daily-panels [data-business-date]') && document.querySelector('#daily-panels [data-business-date]').dataset.businessDate !== '2000-01-01'")
    assert search.input_value()=='Fictional retained search'
    page.locator('#daily-panels').get_by_role('link',name='Mark Arrived',exact=True).first.click()
    page.get_by_label('Reason',exact=True).fill('Fictional patient arrival')
    page.get_by_role('button',name='Save',exact=True).click()
    assert page.get_by_text('Arrival',exact=False).count()>0
    if username=='browserdoctor':
        page.get_by_role('link',name='Start Visit',exact=True).click()
        page.get_by_label('I reviewed this patient medical history and alerts before starting the visit',exact=True).check()
        page.get_by_role('button',name='Save',exact=True).click()
        visit_url=page.url
        visit_id=int(urlsplit(visit_url).path.strip('/').split('/')[-1])
        page.get_by_role('link',name='Prescriptions',exact=True).click()
        page.get_by_role('link',name='Your clinician print details',exact=True).click()
        page.get_by_label('Your actual prescribing clinician name',exact=True).fill('Fictional Browser Clinician')
        page.get_by_role('button',name='Save',exact=True).click()
        page.goto(profile_url)
        page.get_by_role('link',name='Prescriptions',exact=True).click()
        page.get_by_role('link',name='New prescription draft',exact=True).click()
        page.get_by_label('Visit',exact=True).select_option(str(visit_id))
        for field,value in {'name':'Fictional medication only','strength_form':'Fictional form','dose':'Fictional entered dose','route':'Fictional route','frequency':'Fictional frequency','duration':'Fictional duration','quantity':'Fictional quantity','instructions':'Fictional reviewed instructions'}.items():
            page.locator(f'[name="meds-0-{field}"]').fill(value)
        page.get_by_role('button',name='Save',exact=True).click()
        rx_url=page.url
        assert '/prescriptions/new/' not in rx_url, page.locator('.errorlist').all_text_contents()
        page.get_by_role('link',name='Review and issue',exact=True).click()
        page.get_by_label('I reviewed the patient, allergies, medication details and clinician identity and confirm issuance',exact=True).check()
        page.get_by_role('button',name='Issue prescription',exact=True).click()
        page.get_by_role('link',name='Print / Save as PDF preview',exact=True).click()
        assert page.get_by_text('Prescribing clinician: Fictional Browser Clinician',exact=True).count()==1
        assert page.get_by_text(patient_name,exact=True).count()==1
        assert page.get_by_role('navigation').count()==0
        page.emulate_media(media='print')
        page.wait_for_function("() => getComputedStyle(document.querySelector('.no-print')).display === 'none'")
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(root/'runtime'/f'prescription-{width}.png'),full_page=True)
        page.emulate_media(media='screen')
        owner_context=context.browser.new_context(viewport={'width':width,'height':1000})
        owner_context.route('**/*',lambda route: route.continue_() if route.request.url.startswith(base+'/') else route.abort())
        owner_page=owner_context.new_page()
        owner_page.goto(base+'/login/')
        owner_page.get_by_label('Username').fill('browserowner')
        owner_page.get_by_label('Password').fill(password)
        owner_page.get_by_role('button',name='Sign in',exact=True).click()
        owner_page.wait_for_url(base+'/')
        owner_page.goto(rx_url+'print/')
        assert owner_page.get_by_text('Prescribing clinician: Fictional Browser Clinician',exact=True).count()==1
        assert owner_page.request.get(rx_url+'issue/').status==403
        owner_context.close()
        page.goto(appointment_url)
        page.get_by_role('link',name='Change Status / queue order',exact=True).click()
        page.get_by_label('Status',exact=True).select_option('completed')
        page.get_by_label('Reason',exact=True).fill('Fictional appointment finished; clinical draft remains open')
        page.get_by_role('button',name='Save',exact=True).click()
        assert page.get_by_text('Clinical visit status: In Progress.',exact=False).count()==1
    else:
        assert page.request.get(profile_url+'prescriptions/new/').status==403
        page.get_by_role('link',name='Change Status / queue order',exact=True).click()
        page.get_by_label('Status',exact=True).select_option('completed')
        page.get_by_label('Reason',exact=True).fill('Fictional Owner booking completed')
        page.get_by_role('button',name='Save',exact=True).click()
    page.goto(base+'/tasks/new/')
    task_title=f'Fictional personal task {username} {width}'
    page.get_by_label('Title',exact=True).fill(task_title)
    page.get_by_label('Notes',exact=True).fill('Fictional private task note')
    page.get_by_role('button',name='Save',exact=True).click()
    task=page.locator('article').filter(has=page.get_by_role('heading',name=task_title,exact=True))
    task.get_by_role('link',name='Complete task',exact=True).click()
    page.get_by_role('button',name='Save',exact=True).click()
    page.get_by_role('link',name='Completed history',exact=True).click()
    assert page.get_by_role('heading',name=task_title,exact=True).count()==1
    page.goto(base+'/')
    page.screenshot(path=str(root/'runtime'/f'dashboard-phase4-{username}-{width}.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert page.request.get(base+'/finance/reports/?period=annual').status==(200 if username=='browserowner' else 403)
    if username=='browserdoctor' and width==390:
        page.goto(base+'/tasks/new/')
        page.get_by_label('Title',exact=True).fill('Fictional panel privacy marker')
        page.get_by_role('button',name='Save',exact=True).click()
        expired=context.browser.new_context(storage_state=context.storage_state())
        expired.route('**/*',lambda route: route.continue_() if route.request.url.startswith(base+'/') else route.abort())
        expired_page=expired.new_page()
        expired_page.goto(base+'/')
        assert expired_page.get_by_text('Fictional panel privacy marker',exact=True).count()==1
        expired.clear_cookies()
        expired_page.evaluate("document.querySelector('[data-business-date]').dataset.businessDate='2000-01-01'; document.dispatchEvent(new Event('visibilitychange'))")
        expired_page.get_by_role('link',name='Refresh today or sign in again',exact=True).wait_for()
        assert expired_page.get_by_text('Fictional panel privacy marker',exact=True).count()==0
        expired.close()
        print('PASS: lost-session midnight refresh clears patient/task panel data and offers sign-in; no login HTML is inserted',flush=True)
    role_result='Doctor visit, issued fictional prescription/print and Owner print access' if username=='browserdoctor' else 'Owner-only prescription issuance denied'
    print(f'PASS: Phase 4 {username} {width}px: booking/dashboard/arrival, slip/reminder, midnight refresh preserves search, task completion; {role_result}; financial boundaries',flush=True)
    page.goto(profile_url)
