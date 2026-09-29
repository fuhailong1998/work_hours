"""Verify calendar-month defaults and manual cycle selection without OA writes."""
from playwright.sync_api import sync_playwright, expect

URL = 'http://127.0.0.1:18767'
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
    page = browser.new_page()
    page.clock.set_fixed_time('2026-09-29T04:00:00Z')
    bootstrap = page.request.get(URL+'/api/bootstrap').json()
    calls = []
    def query(route):
        calls.append(route.request.post_data_json)
        route.fulfill(json=bootstrap)
    page.route('**/api/query', query)
    page.goto(URL)
    expect(page.get_by_role('button',name='刷新工时',exact=True)).to_be_enabled()
    assert calls == [{'start':'2026-08-25','end':'2026-09-24'}], calls
    page.locator('.date-button').click()
    month = page.locator('#cycle-month')
    month.fill('2027-01')
    month.dispatch_event('change')
    expect(page.locator('#range-start')).to_have_value('2026-12-25')
    expect(page.locator('#range-end')).to_have_value('2027-01-24')
    page.get_by_role('button',name='查询工时',exact=True).click()
    expect(page.get_by_role('dialog')).not_to_be_visible()
    assert calls[-1] == {'start':'2026-12-25','end':'2027-01-24'}
    page.locator('.date-button').click()
    page.get_by_role('button',name='本月工时周期',exact=True).click()
    expect(month).to_have_value('2026-09')
    expect(page.locator('#range-start')).to_have_value('2026-08-25')
    expect(page.locator('#range-end')).to_have_value('2026-09-24')
    page.get_by_role('button',name='上月工时周期',exact=True).click()
    expect(month).to_have_value('2026-08')
    expect(page.locator('#range-start')).to_have_value('2026-07-25')
    page.locator('#range-start').fill('2026-08-01')
    page.locator('#range-start').dispatch_event('change')
    expect(month).to_have_value('')
    page.set_viewport_size({'width':375,'height':800})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    dialog = page.get_by_role('dialog')
    assert dialog.evaluate('(el)=>el.scrollWidth <= el.clientWidth')
    browser.close()
    print('Calendar-month default, manual cycle selection, shortcuts and custom dates passed')
