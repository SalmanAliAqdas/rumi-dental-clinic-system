"""Fictional Phase 3 browser flow, called by browser_check.py for both roles/widths."""
from urllib.parse import urlsplit

def check_finance(page, base, profile_url, username, width, root):
    title=f'Fictional installments {username} {width}'
    page.goto(profile_url)
    page.get_by_role('link',name='Payments',exact=True).click()
    page.get_by_role('link',name='New treatment account',exact=True).click()
    page.get_by_label('Treatment account title',exact=True).fill(title)
    page.get_by_role('button',name='Save',exact=True).click()
    account_url=page.url
    def balance(amount):
        assert page.locator('dd strong').inner_text()==f'PKR {amount}.00'
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),f'Finance overflow at {width}'
    page.get_by_role('link',name='Record Charge',exact=True).click()
    page.get_by_label('Amount (PKR)',exact=True).fill('10000')
    page.get_by_label('Description / correction reason',exact=True).fill('Fictional agreed treatment total')
    page.get_by_role('button',name='Save',exact=True).click()
    balance(10000)
    def pay(amount):
        page.get_by_role('link',name='Receive Payment / Pay in Full',exact=True).click()
        page.get_by_label('Amount (PKR)',exact=True).fill(str(amount))
        page.get_by_label('Method',exact=True).select_option('cash')
        page.get_by_role('button',name='Save',exact=True).click()
        page.get_by_role('heading',name='Rumi Dental Care',exact=True).wait_for()
        assert page.get_by_text(f'Amount received: PKR {amount}.00',exact=True).count()==1
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.emulate_media(media='print')
        assert page.locator('.main-nav').evaluate('e => getComputedStyle(e).display')=='none'
        page.emulate_media(media='screen')
        page.get_by_role('link',name='Return to account',exact=True).click()
    pay(3000); balance(7000)
    page.get_by_role('link',name='Installment Plan',exact=True).click()
    page.get_by_label('Agreement notes / Owner revision reason',exact=True).fill('Fictional agreed installments without invented dates')
    page.get_by_label('Installments',exact=True).fill('2000 | | First agreed amount\n5000 | | Final agreed amount')
    page.get_by_role('button',name='Save',exact=True).click()
    pay(2000); balance(5000)
    pay(5000); balance(0)
    page.get_by_role('link',name='Full Payment Received & Close Account',exact=True).click()
    page.get_by_label('Reason',exact=True).fill('Fictional full payment verified')
    page.get_by_role('button',name='Save',exact=True).click()
    page.get_by_text('Closed - fully paid',exact=False).wait_for()
    page.goto(base+'/finance/outstanding/')
    assert page.get_by_text(title,exact=False).count()==0
    page.goto(profile_url)
    page.get_by_role('link',name='Payments',exact=True).click()
    page.get_by_role('link',name=title,exact=True).click()
    balance(0)
    assert page.get_by_role('link',name='Printable receipt',exact=True).count()==3
    page.screenshot(path=str(root/'runtime'/f'finance-{username}-{width}.png'),full_page=True)
    expected=200 if username=='browserowner' else 403
    assert page.request.get(base+'/finance/reports/?period=annual&date=2025-01-01').status==expected
    assert page.request.get(base+'/finance/export/?period=annual&date=2025-01-01').status==expected
    assert page.request.get(base+'/finance/today/?date=2020-01-01').status==403
    assert page.request.get(base+'/finance/today/').status==200
    print(f'PASS: finance {username} {width}px: charge 10000 -> 3000 -> 7000; installments -> 2000 -> 5000 -> final 5000 -> zero -> close -> outstanding removal -> full history; report/export permissions; print/local layout',flush=True)
    page.goto(profile_url)
