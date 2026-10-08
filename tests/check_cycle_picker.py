"""Verify the top date toolbar with isolated fixtures; no requests reach OA."""
from datetime import date, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright, expect


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


ROOT=Path(__file__).resolve().parents[1]
PROFILE={'id':'1','name':'测试用户','employee_code':'T1','department':'研发',
         'public_project':'PUBLIC','public_project_confirmed':True}


def report(period):
    start,end=date.fromisoformat(period['start']),date.fromisoformat(period['end'])
    days=[str(start+timedelta(days=i)) for i in range((end-start).days+1)]
    return {'start_date':str(start),'end_date':str(end),'public_project':'PUBLIC',
            'queried_at':'2026-09-29T04:00:00Z',
            'project_totals':{'PUBLIC':str(len(days)*4),'PROJECT_A':str(len(days)*4),'合计':str(len(days)*8)},
            'daily':[{'date':day,'hours':{'PUBLIC':'4','PROJECT_A':'4','合计':'8'}} for day in days],
            'public_hours_candidates':[{'date':day,'hours':'4'} for day in days]}


def check_picker(browser,url):
    page=browser.new_page(viewport={'width':1440,'height':1000},locale='zh-CN',reduced_motion='reduce')
    page.clock.set_fixed_time('2026-09-29T04:00:00Z')
    calls,errors,pending=[],[],[]
    fail=False
    hold=False
    page.on('pageerror',lambda error:errors.append(str(error)))

    def api(route):
        path=route.request.url.split('/api/')[1]
        if path=='bootstrap':
            return route.fulfill(json={'profile':PROFILE,'report':None,'report_id':None})
        if path=='oa-saved':return route.fulfill(json={'items':[]})
        if path=='query':
            period=route.request.post_data_json
            calls.append(period)
            if hold:
                pending.append(route)
                return
            return route.fulfill(status=502 if fail else 200,json={'error':'测试网络错误'} if fail else
                                 {'report':report(period),'report_id':'fixture'})
        raise AssertionError(path)

    def ready():
        expect(page.get_by_role('button',name='刷新工时',exact=True)).to_be_enabled()

    page.route('**/api/**',api)
    page.goto(url)
    ready()
    assert calls==[{'start':'2026-08-25','end':'2026-09-24'}]
    toolbar=page.get_by_role('region',name='工时查询',exact=True)
    expect(page.locator('#query-month')).to_have_value('2026-09')
    expect(page.locator('#query-period')).to_contain_text('2026.08.25 — 2026.09.24')
    assert toolbar.bounding_box()['y']<page.locator('.metrics').bounding_box()['y']
    assert toolbar.bounding_box()['y']<page.locator('#oa-saved-flows').bounding_box()['y']
    assert page.locator('.records [data-action="date"]').count()==0

    page.locator('#query-month').fill('2027-01')
    ready()
    assert calls[-1]=={'start':'2026-12-25','end':'2027-01-24'}
    page.get_by_role('button',name='上一个工时周期',exact=True).click()
    ready()
    expect(page.locator('#query-month')).to_have_value('2026-12')
    assert calls[-1]=={'start':'2026-11-25','end':'2026-12-24'}
    page.get_by_role('button',name='下一个工时周期',exact=True).click()
    ready()
    expect(page.locator('#query-month')).to_have_value('2027-01')
    page.get_by_role('button',name='本月',exact=True).click()
    ready()
    assert calls[-1]=={'start':'2026-08-25','end':'2026-09-24'}

    page.get_by_role('button',name='自定义日期',exact=True).click()
    page.locator('#range-start').fill('2026-05-01')
    page.locator('#range-end').fill('2026-05-10')
    page.get_by_role('button',name='查询工时',exact=True).click()
    ready()
    expect(page.locator('#query-month')).to_have_value('')
    expect(page.locator('#query-period')).to_contain_text('自定义日期')
    expect(page.locator('#query-period')).to_contain_text('2026.05.01 — 2026.05.10')
    assert calls[-1]=={'start':'2026-05-01','end':'2026-05-10'}
    page.get_by_role('button',name='刷新工时',exact=True).click()
    ready()
    assert calls[-1]==calls[-2]

    fail=True
    page.locator('#query-month').fill('2026-04')
    ready()
    expect(page.locator('#query-month')).to_have_value('2026-04')
    expect(page.locator('.query-retained')).to_contain_text('2026.05.01 — 2026.05.10')
    page.get_by_role('button',name='自定义日期',exact=True).click()
    expect(page.locator('#range-start')).to_have_value('2026-03-25')
    expect(page.locator('#range-end')).to_have_value('2026-04-24')
    page.get_by_role('button',name='取消',exact=True).click()
    fail=False
    hold=True
    page.get_by_role('button',name='刷新工时',exact=True).click()
    expect(page.locator('#query-month')).to_be_disabled()
    expect(page.get_by_role('button',name='本月',exact=True)).to_be_disabled()
    expect(page.get_by_role('button',name='自定义日期',exact=True)).to_be_disabled()
    assert len(pending)==1
    pending.pop().fulfill(json={'report':report(calls[-1]),'report_id':'fixture'})
    ready()
    assert calls[-1]=={'start':'2026-03-25','end':'2026-04-24'}
    expect(page.locator('.query-retained')).to_have_count(0)

    artifacts=ROOT/'.local/ui-checks'
    artifacts.mkdir(parents=True,exist_ok=True)
    for theme in ['light','dark']:
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        for width in [375,768,1024,1440]:
            page.set_viewport_size({'width':width,'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (theme,width)
            assert toolbar.evaluate('(el)=>el.scrollWidth <= el.clientWidth'), (theme,width)
            assert toolbar.bounding_box()['y']<page.locator('.metrics').bounding_box()['y']
            if width in [375,1440]:
                page.screenshot(path=str(artifacts/f'date-toolbar-{theme}-{width}.png'))
    assert not errors,errors
    page.close()


if __name__=='__main__':
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(ROOT/'web')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox'])
            check_picker(browser,f'http://127.0.0.1:{server.server_port}/')
            browser.close()
        print('Top date toolbar: month navigation, custom dates, retry, loading and responsive themes passed')
    finally:
        server.shutdown();server.server_close()
