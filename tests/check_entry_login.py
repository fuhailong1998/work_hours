"""Entry login UI checks using isolated fixtures; no requests reach OA."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright, expect

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

ROOT = Path(__file__).resolve().parents[1]
server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT/'web')))
threading.Thread(target=server.serve_forever, daemon=True).start()
profile = {'id':'1','name':'测试用户','employee_code':'T1','department':'研发','public_project':'PUBLIC','public_project_confirmed':True}
guest = dict(profile,id='',name='未登录',employee_code='',department='')
report = {'start_date':'2026-09-21','end_date':'2026-09-21','queried_at':'2026-09-29T00:00:00Z',
          'public_project':'PUBLIC','project_totals':{'PUBLIC':'8','PROJECT':'0','合计':'8'},
          'daily':[{'date':'2026-09-21','hours':{'PUBLIC':'8','PROJECT':'0','合计':'8'}}],
          'public_hours_candidates':[{'date':'2026-09-21','hours':'8'}]}
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox'])
        for scenario in ['guest','expired','connected','network_error']:
            page=browser.new_page(viewport={'width':1280,'height':900})
            calls=[]
            signed_in=False
            def api(route):
                global signed_in
                path=route.request.url.split('/api/')[1];calls.append(path)
                if path=='bootstrap':
                    return route.fulfill(json={'profile':guest if scenario=='guest' else profile,
                                              'report':None,'report_id':None})
                if path=='auth/start':
                    return route.fulfill(json={'status':'waiting','message':'请用飞书扫码登录'})
                if path=='auth/status':
                    signed_in=True
                    return route.fulfill(json={'status':'authenticated','message':'登录成功','profile':profile})
                if path in ['query','oa-saved']:
                    if not signed_in and scenario=='expired':
                        return route.fulfill(status=401,json={'code':'oa_login_required','error':'登录已过期'})
                    if scenario=='network_error':
                        return route.fulfill(status=502,json={'code':'oa_connection_error','error':'网络暂不可用'})
                    return route.fulfill(json={'items':[]} if path=='oa-saved' else {'report':report,'report_id':'fixture'})
                raise AssertionError(path)
            page.route('**/api/**',api)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            if scenario in ['guest','expired']:
                expect(page.get_by_role('dialog')).to_be_visible()
                expect(page.locator('#auth-message')).to_have_text('请用飞书扫码登录')
                assert calls.count('auth/start')==1
                bounds=page.get_by_role('dialog').bounding_box()
                assert abs(bounds['x']+bounds['width']/2-640)<2
                if scenario=='guest':
                    assert 'query' not in calls
                    page.get_by_role('button',name='关闭弹窗',exact=True).click()
                    page.wait_for_timeout(2800)
                    assert 'auth/status' not in calls
                    expect(page.get_by_role('dialog')).not_to_be_visible()
                else:
                    expect(page.get_by_role('dialog')).not_to_be_visible(timeout=10000)
                    expect(page.locator('#breadcrumb-name')).to_have_text('项目工时')
                    expect(page.get_by_role('button',name='刷新工时',exact=True)).to_be_enabled()
                    assert calls.count('query')==2
            else:
                expect(page.get_by_role('button',name='刷新工时',exact=True)).to_be_enabled()
                expect(page.get_by_role('dialog')).not_to_be_visible()
                assert 'auth/start' not in calls
            page.close()
        browser.close()
    print('Entry login: guest prompt, expired-session login/retry, dismissal, valid session and network error passed')
finally:
    server.shutdown();server.server_close()
