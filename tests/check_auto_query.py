"""Run against the local server: python tests/check_auto_query.py."""
import json
from playwright.sync_api import sync_playwright, expect

URL = "http://127.0.0.1:18767"

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox"])
    page = browser.new_page()
    bootstrap = page.request.get(URL + "/api/bootstrap").json()
    assert bootstrap["report"], "This check requires an existing report snapshot"
    for has_cache, succeeds in [(True, True), (True, False), (False, True)]:
        page.unroute_all()
        calls = []
        payload = dict(bootstrap, report=bootstrap["report"] if has_cache else None)
        page.route("**/api/bootstrap", lambda route: route.fulfill(json=payload))

        def query(route):
            calls.append(route.request.post_data_json)
            route.fulfill(status=200 if succeeds else 502, json=(
                {"report": bootstrap["report"], "report_id": bootstrap["report_id"]}
                if succeeds else {"error": "测试：OA 暂时不可用"}))

        page.route("**/api/query", query)
        page.goto(URL)
        expect(page.get_by_role("button", name="刷新工时", exact=True)).to_be_enabled()
        assert len(calls) == 1, calls
        assert calls[0]["start"].endswith("-25")
        assert calls[0]["end"].endswith("-24")
        assert calls[0]["start"] < calls[0]["end"]
        expect(page.locator(".metric-value").first).to_contain_text(str(int(float(bootstrap["report"]["project_totals"]["合计"]))))
        if not succeeds:
            expect(page.get_by_role("alert")).to_contain_text("OA 暂时不可用")
            expect(page.get_by_role("button", name="扫码登录 OA", exact=True)).to_be_visible()
            page.get_by_role("button", name="重试查询", exact=True).click()
            expect(page.get_by_role("button", name="刷新工时", exact=True)).to_be_enabled()
            assert len(calls) == 2 and calls[0] == calls[1]
    page.unroute_all()
    queries = []
    page.route("**/api/bootstrap", lambda route: route.fulfill(json=bootstrap))
    def recovering_query(route):
        queries.append(route.request.post_data_json)
        route.fulfill(status=401 if len(queries) == 1 else 200, json=(
            {"error": "请扫码登录"} if len(queries) == 1 else
            {"report": bootstrap["report"], "report_id": bootstrap["report_id"]}))
    page.route("**/api/query", recovering_query)
    page.route("**/api/auth/start", lambda route: route.fulfill(json={"status": "waiting", "message": "等待扫码"}))
    page.route("**/api/auth/status", lambda route: route.fulfill(json={"status": "authenticated", "message": "登录成功"}))
    page.goto(URL)
    page.get_by_role("button", name="扫码登录 OA", exact=True).click()
    expect(page.get_by_role("dialog")).not_to_be_visible(timeout=10000)
    expect(page.get_by_role("button", name="刷新工时", exact=True)).to_be_enabled()
    assert len(queries) == 2 and queries[0] == queries[1]
    expect(page.get_by_role("alert")).to_have_count(0)
    browser.close()
    print("Auto-query: cached, first-use and error fallback passed")
