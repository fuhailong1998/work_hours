"""Browser allocation regression; OA query/save are mocked, preview uses real validation."""
from playwright.sync_api import sync_playwright, expect

URL = 'http://127.0.0.1:18767'
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width':1440, 'height':1000})
    bootstrap = page.request.get(URL+'/api/bootstrap').json()
    page.route('**/api/query', lambda route: route.fulfill(json=bootstrap))
    saved = []
    def save(route):
        saved.append(route.request.post_data_json)
        route.fulfill(json={'draft':{'request_id':'test','url':'https://i.thundersoft.com/?requestid=test','oa_saved':True,'oa_submitted':False}})
    page.route('**/api/oa-draft', save)
    page.goto(URL)
    expect(page.get_by_role('button',name='刷新工时',exact=True)).to_be_enabled()
    day = bootstrap['report']['public_hours_candidates'][0]['date']
    hours = float(bootstrap['report']['public_hours_candidates'][0]['hours'])
    page.locator(f'[data-row-date="{day}"]').check()
    page.locator('[data-target="0"]').select_option('__custom')
    page.locator('[data-custom-target="0"]').fill('TEST_PROJECT_A')
    page.get_by_role('button',name='+ 添加调入项目',exact=True).click()
    page.locator('[data-target="1"]').select_option('__custom')
    page.locator('[data-custom-target="1"]').fill('TEST_PROJECT_B')
    page.locator('#plan-reason').fill('多项目回归测试，不创建真实草稿')
    first = page.locator(f'[data-quantity="{day}"][data-allocation="0"]')
    second = page.locator(f'[data-quantity="{day}"][data-allocation="1"]')
    expect(second).to_have_value('0')
    second.fill('1')
    expect(page.locator('#preview-button')).to_be_disabled()
    first.fill(str(hours-1))
    expect(page.locator('#preview-button')).to_be_enabled()
    page.locator('[data-custom-target="1"]').fill('TEST_PROJECT_A')
    expect(page.locator('#preview-button')).to_be_disabled()
    page.locator('[data-custom-target="1"]').fill('TEST_PROJECT_B')
    page.locator('#preview-button').click()
    dialog = page.get_by_role('dialog')
    expect(dialog).to_be_visible()
    expect(dialog.locator('.modal-head')).to_contain_text('1 天')
    expect(dialog.locator('.preview-table tbody tr')).to_have_count(2)
    page.get_by_role('button',name='创建 OA 表单',exact=False).click()
    expect(page.locator('#oa-draft-result')).to_contain_text('OA 草稿已保存')
    assert len(saved)==1
    assert {r['target_project'] for r in saved[0]['rows']}=={'TEST_PROJECT_A','TEST_PROJECT_B'}
    assert sum(float(r['hours']) for r in saved[0]['rows'])==hours
    for width in [375,768,1440]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        bounds=dialog.bounding_box()
        assert abs(bounds['x']+bounds['width']/2-width/2)<2
    page.keyboard.press('Escape')
    page.locator('[data-remove-target="0"]').click()
    expect(page.locator('[data-target]')).to_have_count(1)
    expect(page.locator(f'[data-quantity="{day}"]')).to_have_value('1')
    expect(page.locator('[data-custom-target="0"]')).to_have_value('TEST_PROJECT_B')
    # Average the current partial withdrawal (1h), not the full available day.
    page.get_by_role('button',name='+ 添加调入项目',exact=True).click()
    page.get_by_role('button',name='+ 添加调入项目',exact=True).click()
    for i, name in [(1, 'TEST_PROJECT_C'), (2, 'TEST_PROJECT_D')]:
        page.locator(f'[data-target="{i}"]').select_option('__custom')
        page.locator(f'[data-custom-target="{i}"]').fill(name)
    page.get_by_role('button',name='平均调入工时',exact=True).click()
    inputs=page.locator(f'[data-quantity="{day}"]')
    assert inputs.evaluate_all('(els)=>els.map(el=>el.value)') == ['0.34','0.33','0.33']
    expect(page.locator('#selected-hours')).to_have_text('1')
    page.get_by_role('button',name='平均调入工时',exact=True).click()
    assert inputs.evaluate_all('(els)=>els.map(el=>el.value)') == ['0.34','0.33','0.33']
    inputs.first.fill(str(hours+1))
    expect(page.locator('#average-button')).to_be_disabled()
    inputs.first.fill('0.34')
    for width in [375,768,1024,1440]:
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        plan=page.locator('.plan-card').bounding_box()
        records=page.locator('.records').bounding_box()
        assert abs(plan['width']-records['width'])<2
        assert plan['y']>records['y']+records['height']
    page.locator('.plan-card').scroll_into_view_if_needed()
    page.screenshot(path='.local/ui-checks/spacious-allocation.png', full_page=True)
    page.locator('#theme-button').click()
    page.screenshot(path='.local/ui-checks/spacious-allocation-dark.png', full_page=True)
    page.locator(f'[data-row-date="{day}"]').uncheck()
    expect(page.locator('#average-button')).to_be_disabled()
    browser.close()
    print('Multi-project allocation, validation, preview, mocked draft and responsive layout passed')
