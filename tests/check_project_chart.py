"""Check real project segments and daily selection using isolated OA report fixtures."""
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright, expect


ROOT=Path(__file__).resolve().parents[1]
SPECIAL='项目 C "专项" <验证> & 支持'
PROFILE={'id':'1','name':'测试用户','employee_code':'T1','department':'研发',
         'public_project':'PUBLIC','public_project_confirmed':True}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def report(period,extra=False):
    start,end=date.fromisoformat(period['start']),date.fromisoformat(period['end'])
    examples=[{'PROJECT_A':'4','PROJECT_B':'2',SPECIAL:'2'},
              {'PUBLIC':'2','PROJECT_A':'3.5','PROJECT_B':'2.5'},
              {'PROJECT_A':'3','PROJECT_B':'1'}, {'PUBLIC':'8'}, {}, {'PROJECT_A':'10'}, {}]
    names=['PUBLIC','PROJECT_A','PROJECT_B',SPECIAL,'ZERO_ONLY']+(['000_NEW_PROJECT'] if extra else [])
    daily=[]
    for i in range((end-start).days+1):
        hours={name:'0' for name in names}
        hours.update(examples[i] if i<len(examples) else {})
        if extra and i==9:hours['000_NEW_PROJECT']='1'
        hours['合计']=str(sum(Decimal(h) for h in hours.values()))
        daily.append({'date':str(start+timedelta(days=i)),'hours':hours,
                      'calendar':{'known':True,'label':'工作日' if i<6 else '休息日',
                                  'missing_hours':str(max(Decimal(0),8-Decimal(hours['合计']))) if i<6 else '0'}})
    return {'start_date':str(start),'end_date':str(end),'public_project':'PUBLIC',
            'queried_at':'2026-09-29T04:00:00Z','daily':daily,
            'project_totals':{name:str(sum(Decimal(row['hours'][name]) for row in daily)) for name in names+['合计']},
            'public_hours_candidates':[{'date':row['date'],'hours':row['hours']['PUBLIC']} for row in daily if Decimal(row['hours']['PUBLIC'])>0]}


def check_chart(browser,url):
    page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    page.clock.set_fixed_time('2026-09-29T04:00:00Z')
    errors=[]
    extra=False
    page.on('pageerror',lambda error:errors.append(str(error)))

    def api(route):
        path=route.request.url.split('/api/')[1]
        if path=='bootstrap':return route.fulfill(json={'profile':PROFILE,'report':None,'report_id':None})
        if path=='oa-saved':return route.fulfill(json={'items':[]})
        if path=='query':return route.fulfill(json={'report':report(route.request.post_data_json,extra),'report_id':'fixture'})
        raise AssertionError(path)

    page.route('**/api/**',api)
    page.goto(url)
    expect(page.get_by_role('button',name='刷新工时',exact=True)).to_be_enabled()
    chart=page.get_by_role('region',name='逐日工时分布',exact=True)
    first=page.locator('[data-chart-date="2026-08-25"]')
    expect(first.locator('.project-bar')).to_have_count(3)
    assert set(first.locator('.project-bar').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.chartProject)'))=={'PROJECT_A','PROJECT_B',SPECIAL}
    for label in ['合计 8 小时','PROJECT_A 4 小时','PROJECT_B 2 小时',SPECIAL+' 2 小时','未填 0 小时']:
        assert label in first.get_attribute('title')
    colors=first.locator('.project-bar').evaluate_all('(nodes)=>nodes.map(n=>getComputedStyle(n).backgroundColor)')
    assert len(set(colors))==3
    expect(chart.locator('[data-legend-project="ZERO_ONLY"]')).to_have_count(0)
    expect(chart.locator('[data-legend-project="合计"]')).to_have_count(0)
    expect(chart.locator('.project-legend')).to_contain_text(SPECIAL)
    expect(chart.locator('.project-legend')).not_to_contain_text('正式工时')
    assert chart.locator('img').count()==0
    alpha=first.locator('[data-chart-project="PROJECT_A"]')
    alpha_color=alpha.evaluate('(el)=>getComputedStyle(el).backgroundColor')
    assert alpha_color==chart.locator('[data-legend-project="PROJECT_A"] i').evaluate('(el)=>getComputedStyle(el).backgroundColor')
    mixed=page.locator('[data-chart-date="2026-08-26"]')
    expect(mixed.locator('.project-bar')).to_have_count(3)
    expect(mixed.locator('[data-chart-project="PROJECT_A"]')).to_have_attribute('title','2026-08-26 · PROJECT_A：3.5 小时（当天合计 8 小时）')
    assert mixed.locator('[data-chart-project="PROJECT_A"]').evaluate('(el)=>getComputedStyle(el).backgroundColor')==alpha_color
    assert abs(alpha.bounding_box()['height']/first.locator('.bar-space').bounding_box()['height']-.4)<.01
    missing=page.locator('[data-chart-date="2026-08-27"]')
    expect(missing.locator('.project-bar')).to_have_count(2)
    expect(missing.locator('.missing-bar')).to_have_count(1)
    assert 'repeating-linear-gradient' in missing.locator('.missing-bar').evaluate('(el)=>getComputedStyle(el).backgroundImage')
    expect(page.locator('[data-chart-date="2026-08-28"] .project-bar')).to_have_count(1)
    expect(page.locator('[data-chart-date="2026-08-29"] .project-bar')).to_have_count(0)
    expect(page.locator('[data-chart-date="2026-08-29"] .missing-bar')).to_have_count(1)
    expect(page.locator('[data-chart-date="2026-08-31"] .empty')).to_have_count(1)

    expect(mixed).to_have_attribute('aria-pressed','true')
    mixed.locator('[data-chart-project="PROJECT_B"]').click()
    expect(mixed).to_have_attribute('aria-pressed','false')
    expect(page.locator('#selected-hours')).to_have_text('8')
    mixed.press('Space')
    expect(mixed).to_have_attribute('aria-pressed','true')
    expect(page.locator('#selected-hours')).to_have_text('10')
    extra=True
    page.get_by_role('button',name='下一个工时周期',exact=True).click()
    expect(page.get_by_role('button',name='刷新工时',exact=True)).to_be_enabled()
    assert page.locator('[data-chart-date="2026-09-25"] [data-chart-project="PROJECT_A"]').evaluate('(el)=>getComputedStyle(el).backgroundColor')==alpha_color
    expect(chart.locator('[data-legend-project="000_NEW_PROJECT"]')).to_have_count(1)

    artifacts=ROOT/'.local/ui-checks'
    artifacts.mkdir(parents=True,exist_ok=True)
    for theme in ['light','dark']:
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        for width in [375,768,1024,1440]:
            page.set_viewport_size({'width':width,'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (theme,width)
            assert chart.evaluate('(el)=>el.scrollWidth <= el.clientWidth'), (theme,width)
            if width in [375,1440]:chart.screenshot(path=str(artifacts/f'project-chart-{theme}-{width}.png'))
    first=page.locator('[data-chart-date="2026-09-25"]')
    first.click()
    expect(page.locator('#record-search')).to_have_value('2026-09-25')
    expect(page.locator('.hours-table tbody tr')).to_have_count(3)
    assert not errors,errors
    page.close()


if __name__=='__main__':
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(ROOT/'web')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox'])
            check_chart(browser,f'http://127.0.0.1:{server.server_port}/')
            browser.close()
        print('Project chart: segments, scale, colors, missing hours, labels, selection and responsive themes passed')
    finally:
        server.shutdown();server.server_close()
