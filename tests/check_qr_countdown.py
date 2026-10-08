"""Exercise QR expiry, refresh and login using a virtual clock and isolated HTTP fixtures."""
import base64
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import threading
import qrcode
from playwright.sync_api import sync_playwright, expect


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


ROOT=Path(__file__).resolve().parents[1]
qr_image=io.BytesIO()
qrcode.make('LOCAL-UI-TEST-ONLY').save(qr_image,format='PNG')
QR='data:image/png;base64,'+base64.b64encode(qr_image.getvalue()).decode()
PROFILE={'id':'1','name':'测试用户','employee_code':'T1','department':'研发',
         'public_project':'PUBLIC','public_project_confirmed':True}


def check_countdown(browser,url):
    page=browser.new_page(viewport={'width':375,'height':900})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    base=datetime(2026,10,8,10,0,tzinfo=timezone.utc)
    page.clock.install(time=base)
    page.clock.pause_at(base+timedelta(seconds=1))
    fixture={'expires':int((base+timedelta(seconds=61)).timestamp()*1000),
             'status':'waiting','scanned':False,'polls':0}

    def api(route):
        path=route.request.url.split('/api/')[1]
        if path=='bootstrap':
            return route.fulfill(json={'profile':dict(PROFILE,id=''), 'report':None,'report_id':None})
        if path in ('auth/start','auth/status'):
            if path=='auth/status':fixture['polls']+=1
            if fixture['status']=='authenticated':
                return route.fulfill(json={'status':'authenticated','message':'登录成功','profile':PROFILE})
            message='已扫码，请在手机上确认登录' if fixture['scanned'] else '请用飞书扫码并在手机上确认登录'
            return route.fulfill(json={'status':fixture['status'],'message':message,'qr':QR,
                                       'qr_expires_at':fixture['expires'],'scanned':fixture['scanned']})
        if path=='oa-saved':return route.fulfill(json={'items':[]})
        if path=='query':
            period=route.request.post_data_json
            return route.fulfill(json={'report':{'start_date':period['start'],'end_date':period['end'],
                'queried_at':'2026-10-08T10:00:00Z','public_project':'PUBLIC','project_totals':{},
                'daily':[],'public_hours_candidates':[]},'report_id':'fixture'})
        raise AssertionError(path)

    def refresh():
        fixture.update(status='waiting',scanned=False,expires=page.evaluate('Date.now()')+60000)
        page.locator('#auth-refresh').click()
        expect(page.locator('#auth-countdown')).to_have_text('预计 01:00 后过期')
        expect(page.locator('#auth-qr')).to_be_visible()

    page.route('**/api/**',api)
    page.goto(url)
    expect(page.locator('#auth-countdown')).to_have_text('预计 01:00 后过期')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    bounds=page.get_by_role('dialog').bounding_box()
    assert abs(bounds['x']+bounds['width']/2-187.5)<2
    assert abs(bounds['y']+bounds['height']/2-450)<2
    page.clock.fast_forward(46000)
    expect(page.locator('#auth-countdown')).to_have_text('预计 00:14 后过期')
    expect(page.locator('#auth-countdown')).to_have_class('auth-countdown urgent')
    page.clock.fast_forward(15000)
    expect(page.locator('#auth-countdown')).to_have_text('二维码已到期，请刷新')
    expect(page.locator('#auth-qr')).not_to_be_visible()
    expect(page.locator('#auth-qr-expired')).to_be_visible()
    assert fixture['polls']>0

    refresh()
    fixture['status']='expired'
    page.clock.fast_forward(3000)
    expect(page.locator('#auth-countdown')).to_have_text('二维码已过期，请刷新')
    expect(page.locator('#auth-qr')).not_to_be_visible()

    refresh()
    fixture['scanned']=True
    page.clock.fast_forward(3000)
    expect(page.locator('#auth-message')).to_have_text('已扫码，请在手机上确认登录')
    expect(page.locator('#auth-countdown')).not_to_be_visible()
    page.clock.fast_forward(65000)
    expect(page.locator('#auth-message')).to_have_text('已扫码，请在手机上确认登录')
    fixture['status']='authenticated'
    page.clock.fast_forward(3000)
    expect(page.get_by_role('dialog')).not_to_be_visible()
    expect(page.get_by_role('button',name='刷新工时',exact=True)).to_be_enabled()
    polls=fixture['polls']
    page.clock.fast_forward(10000)
    assert fixture['polls']==polls

    page.reload()
    expect(page.get_by_role('dialog')).not_to_be_visible()
    # A fresh guest opens the dialog again; close must cancel both timers.
    fixture.update(status='waiting',scanned=False,expires=page.evaluate('Date.now()')+60000)
    page.reload()
    expect(page.locator('#auth-countdown')).to_have_text('预计 01:00 后过期')
    page.get_by_role('button',name='关闭弹窗',exact=True).click()
    expect(page.get_by_role('dialog')).not_to_be_visible()
    polls=fixture['polls']
    page.clock.fast_forward(65000)
    assert fixture['polls']==polls
    assert not errors,errors
    page.close()


def check_refresh_during_poll(browser,url):
    page=browser.new_page()
    page.clock.install()
    pending=[]
    starts=[]
    expires=page.evaluate('Date.now()')+60000

    def api(route):
        path=route.request.url.split('/api/')[1]
        if path=='bootstrap':
            return route.fulfill(json={'profile':dict(PROFILE,id=''),'report':None,'report_id':None})
        if path=='auth/start':
            starts.append(path)
            return route.fulfill(json={'status':'waiting','message':'请扫码登录','qr':QR,'qr_expires_at':expires})
        if path=='auth/status':
            pending.append(route)
            return
        raise AssertionError(path)

    page.route('**/api/**',api)
    page.goto(url)
    expect(page.locator('#auth-countdown')).to_be_visible()
    with page.expect_request('**/api/auth/status'):
        page.clock.fast_forward(3000)
    expect(page.locator('#auth-refresh')).to_be_enabled()
    page.locator('#auth-refresh').click()
    expect(page.locator('#auth-message')).to_have_text('正在准备登录二维码…')
    assert len(starts)==1, 'A refresh must wait for the previous status request to finish'
    assert len(pending)==1
    expires=page.evaluate('Date.now()')+60000
    pending.pop().fulfill(json={'status':'expired','message':'旧二维码已失效'})
    expect(page.locator('#auth-countdown')).to_have_text('预计 01:00 后过期')
    expect(page.locator('#auth-qr')).to_be_visible()
    assert len(starts)==2
    page.close()


if __name__=='__main__':
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(ROOT/'web')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox'])
            check_countdown(browser,f'http://127.0.0.1:{server.server_port}/')
            check_refresh_during_poll(browser,f'http://127.0.0.1:{server.server_port}/')
            browser.close()
        print('QR countdown: expiry, refresh, server invalidation, scanned confirmation, login and cleanup passed')
    finally:
        server.shutdown();server.server_close()
