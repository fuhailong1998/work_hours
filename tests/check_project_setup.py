"""First-use setup and settings UI checks with isolated fixtures, without OA requests."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright, expect


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


ROOT = Path(__file__).resolve().parents[1]


def check_setup(browser, url, guest=False):
    page = browser.new_page(viewport={'width': 375 if guest else 1280, 'height': 900})
    profile = {'id': '1', 'name': '测试用户', 'employee_code': 'T1', 'department': '研发',
               'public_project': 'OS_AIOS_2026', 'public_project_confirmed': False}
    calls, errors = [], []
    signed_in = not guest
    fail_save = False
    page.on('pageerror', lambda error: errors.append(str(error)))

    def api(route):
        nonlocal signed_in, fail_save, profile
        path = route.request.url.split('/api/')[1]
        calls.append(path)
        if path == 'bootstrap':
            return route.fulfill(json={'profile': profile if signed_in else dict(profile, id=''),
                                       'report': None, 'report_id': None})
        if path == 'auth/start':
            return route.fulfill(json={'status': 'waiting', 'message': '请用飞书扫码登录'})
        if path == 'auth/status':
            signed_in = True
            return route.fulfill(json={'status': 'authenticated', 'message': '登录成功', 'profile': profile})
        if path == 'oa-saved':
            return route.fulfill(json={'items': []})
        if path == 'profile':
            if fail_save:
                return route.fulfill(status=500, json={'error': '保存失败，请重试'})
            profile = dict(profile, public_project=route.request.post_data_json['public_project'],
                           public_project_confirmed=True)
            return route.fulfill(json={'profile': profile})
        if path == 'query':
            period = route.request.post_data_json
            report = {'start_date': period['start'], 'end_date': period['end'],
                      'queried_at': '2026-10-08T00:00:00Z', 'public_project': profile['public_project'],
                      'project_totals': {profile['public_project']: '8', '合计': '8'},
                      'daily': [{'date': period['start'], 'hours': {profile['public_project']: '8', '合计': '8'}}],
                      'public_hours_candidates': [{'date': period['start'], 'hours': '8'}]}
            return route.fulfill(json={'report': report, 'report_id': 'fixture'})
        raise AssertionError(path)

    page.route('**/api/**', api)
    page.goto(url)
    dialog = page.get_by_role('dialog')
    if guest:
        expect(page.locator('#auth-message')).to_have_text('请用飞书扫码登录')
        assert 'query' not in calls
    expect(dialog.get_by_role('heading', name='设置你的公共项目')).to_be_visible(timeout=10000)
    expect(page.locator('#setup-public-project')).to_have_value('OS_AIOS_2026')
    assert 'query' not in calls
    bounds = dialog.bounding_box()
    assert abs(bounds['x'] + bounds['width']/2 - page.viewport_size['width']/2) < 2
    assert abs(bounds['y'] + bounds['height']/2 - page.viewport_size['height']/2) < 2
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert dialog.evaluate('(el) => el.scrollWidth <= el.clientWidth')

    if not guest:
        page.get_by_role('button', name='稍后设置').click()
        expect(dialog).not_to_be_visible()
        expect(page.locator('#breadcrumb-name')).to_have_text('个人设置')
        assert 'query' not in calls
        page.locator('.sidebar button[data-view="workbench"]').click()
        expect(dialog).to_be_visible()
        page.locator('#setup-public-project').fill('   ')
        page.locator('#setup-save').click()
        expect(page.locator('#setup-error')).to_have_text('请填写公共项目名称')
        assert 'profile' not in calls
        fail_save = True
        page.locator('#setup-public-project').fill('PUBLIC_CUSTOM')
        page.locator('#setup-save').click()
        expect(page.locator('#setup-error')).to_have_text('保存失败，请重试')
        expect(page.locator('#setup-public-project')).to_have_value('PUBLIC_CUSTOM')
        expect(page.locator('#setup-save')).to_be_enabled()
        assert 'query' not in calls
        fail_save = False

    page.locator('#setup-public-project').fill('  PUBLIC_CUSTOM  ')
    page.locator('#setup-save').click()
    expect(dialog).not_to_be_visible()
    expect(page.locator('#breadcrumb-name')).to_have_text('项目工时')
    expect(page.get_by_role('button', name='刷新工时', exact=True)).to_be_enabled()
    assert calls.count('query') == 1
    assert profile['public_project'] == 'PUBLIC_CUSTOM' and profile['public_project_confirmed']

    page.reload()
    expect(page.get_by_role('button', name='刷新工时', exact=True)).to_be_enabled()
    expect(dialog).not_to_be_visible()
    assert calls.count('query') == 2
    if not guest:
        page.locator('.sidebar [data-view="settings"]').click()
        expect(page.locator('#public-project')).to_have_value('PUBLIC_CUSTOM')
        page.locator('#public-project').fill('PUBLIC_EDITED')
        page.get_by_role('button', name='保存个人配置').click()
        expect(page.locator('#toast')).to_have_text('公共项目已保存到本机，请重新查询工时')
        assert profile['public_project'] == 'PUBLIC_EDITED'
        page.reload()
        expect(page.get_by_role('button', name='刷新工时', exact=True)).to_be_enabled()
        expect(dialog).not_to_be_visible()
        page.locator('.sidebar [data-view="settings"]').click()
        expect(page.locator('#public-project')).to_have_value('PUBLIC_EDITED')
    assert not errors, errors
    page.close()


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT/'web')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True,
                                        args=['--no-sandbox'])
            for guest in [False, True]:
                check_setup(browser, f'http://127.0.0.1:{server.server_port}/', guest=guest)
            browser.close()
        print('Project setup: first use, login, local save/edit, retry, reload and mobile layout passed')
    finally:
        server.shutdown()
        server.server_close()
