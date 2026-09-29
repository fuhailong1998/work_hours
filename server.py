#!/usr/bin/env python3
"""Local hours workbench using OA HTTP APIs; save drafts without submission."""
import argparse
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

from query_hours import query_report, OAAuthRequired
from oa_draft import create_draft
from oa_session import get_session, login_status
from oa_auth_api import clear_login
from oa_saved import saved_adjustments
from oa_form_api import OAForm, value
from work_calendar import annotate_calendar
from oa_http import get_session

from app_paths import RESOURCE_ROOT as ROOT, DATA_ROOT

LOCAL = DATA_ROOT / "workbench"
REPORT_FILE = DATA_ROOT / "oa" / "hours.json"
PROFILE_FILE = LOCAL / "profile.json"
LOCK = threading.Lock()
QUERY_LOCK = threading.Lock()
DRAFT_LOCK = threading.Lock()  # ponytail: one local user; serialize draft creation to avoid duplicates.
DRAFT_PROGRESS = {"message": "", "started": 0, "active": False}


def draft_progress(message):
    with LOCK:
        DRAFT_PROGRESS["message"] = message


DEFAULT_PROFILE = {"id":"", "name":"未登录", "employee_code":"", "department":"", "public_project":""}



def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.chmod(0o600)
    temp.replace(path)


def activate_employee(client, employee):
    """Switch the local workspace only after OA has verified the employee."""
    employee_id=str(employee['id'])
    if not employee_id.isdigit():raise ValueError('OA 返回的员工编号无效')
    form=OAForm(client,load_details=False)
    form.link_main()
    fields=form.tables['main']['fieldinfomap']
    values={f.get('fieldname','').lower():value(form.main.get('field'+key,{})) for key,f in fields.items()}
    if values.get('sqr')!=employee_id or not values.get('ygbh'):
        raise ValueError('OA 员工身份或工号未核实，请重试登录状态查询')
    return store_employee(dict(employee,employee_code=values['ygbh']))


def store_employee(employee):
    employee_id=str(employee['id'])
    if not employee_id.isdigit():raise ValueError('OA 返回的员工编号无效')
    with LOCK:
        previous=load(PROFILE_FILE,DEFAULT_PROFILE)
        if previous['id'] and previous['id']!=employee_id:
            old=LOCAL/'employees'/previous['id']
            write_json(old/'profile.json',previous)
            report=load(REPORT_FILE,None)
            if report:write_json(old/'hours.json',report)
        directory=LOCAL/'employees'/employee_id
        stored=previous if previous['id']==employee_id else load(directory/'profile.json',DEFAULT_PROFILE)
        profile={**DEFAULT_PROFILE,**stored,**employee,'id':employee_id}
        if previous['id']!=employee_id:
            restored=load(directory/'hours.json',None)
            if restored and restored.get('employee',{}).get('id')==employee_id:write_json(REPORT_FILE,restored)
            else:REPORT_FILE.unlink(missing_ok=True)
        write_json(directory/'profile.json',profile)
        write_json(PROFILE_FILE,profile)
        return profile


def deactivate_employee():
    """Archive account data, then expose only the guest workspace."""
    with LOCK:
        profile=load(PROFILE_FILE,DEFAULT_PROFILE)
        if profile['id']:
            directory=LOCAL/'employees'/profile['id']
            write_json(directory/'profile.json',profile)
            report=load(REPORT_FILE,None)
            if report:write_json(directory/'hours.json',report)
        write_json(PROFILE_FILE,DEFAULT_PROFILE)
        REPORT_FILE.unlink(missing_ok=True)
    return dict(DEFAULT_PROFILE)


def report_id(report):
    return hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()[:20]


def draft_key(plan):
    data={k: plan[k] for k in ("employee", "public_project", "target_project", "application_reason", "adjustments")}
    if len(plan.get("source_projects",[]))>1:data["source_withdrawals"]=plan["source_withdrawals"]
    return report_id(data)


def make_draft(body, client):
    if not DRAFT_LOCK.acquire(blocking=False):
        raise ValueError("OA 表单正在创建，请勿重复操作")
    try:
        with LOCK:
            DRAFT_PROGRESS.update(message="正在核实最新调出项目工时", started=time.monotonic(), active=True)
            profile = load(PROFILE_FILE, DEFAULT_PROFILE)
            report = load(REPORT_FILE, None)
            plan = validate_plan(body, report, profile)
        path = LOCAL / "drafts" / (draft_key(plan) + ".json")
        previous = load(path, None)
        if previous:
            if previous.get("result"):
                return previous["result"]
            if previous.get("status") == "saving":
                raise ValueError("上次保存结果尚未确认。请在 OA 草稿列表核实，系统不会重复创建")
        # Recheck source hours at creation time, not just the old preview snapshot.
        days = [r["date"] for r in plan["adjustments"]]
        fresh = query_report(client, date.fromisoformat(min(days)), date.fromisoformat(max(days)), profile["public_project"], profile["id"])
        refreshed=validate_plan(dict(body, report_id=report_id(fresh)), fresh, profile)
        if refreshed['source_withdrawals']!=plan['source_withdrawals']:raise ValueError('来源项目工时已变化，请重新查询并预览')
        def before_save():
            with LOCK:
                if load(PROFILE_FILE, DEFAULT_PROFILE) != profile:
                    raise ValueError("个人配置已改变，未保存 OA 表单")
                write_json(path, {"status": "saving", "plan": plan})
        def saved(result):
            with LOCK:
                write_json(path, {"status": "saved", "plan": plan, "result": result})
        try:
            return create_draft(client, plan, before_save, saved, progress=draft_progress)
        except Exception as error:
            record = load(path, None)
            if record and record.get("result"):
                return dict(record["result"], warning="草稿已保存，但回读核验未完成，请打开 OA 表单核对")
            if record and record.get("status") == "saving":
                raise ValueError("OA 保存结果尚未确认，请在 OA 草稿列表核实；不会自动重试保存") from error
            raise
    finally:
        with LOCK:
            DRAFT_PROGRESS["active"] = False
        DRAFT_LOCK.release()


def validate_plan(body, report, profile):
    if not report or body.get("report_id") != report_id(report):
        raise ValueError("查询结果已变化，请刷新后重新选择工时")
    if report["public_project"] != profile["public_project"]:
        raise ValueError("公共项目已变更，请重新查询工时")
    sources=body.get('source_projects',[body.get('source_project',profile['public_project'])])
    if not isinstance(sources,list) or not sources or any(not isinstance(x,str) or not x.strip() or x=='合计' for x in sources):
        raise ValueError('请至少选择一个有效的调出项目')
    sources=sorted(set(x.strip() for x in sources))
    source=sources[0] if len(sources)==1 else ''
    target = str(body.get("target_project", "")).strip()
    reason = str(body.get("reason", "")).strip()
    if not reason or len(reason) > 4000:
        raise ValueError("请填写申请原因（不超过 4000 字）")
    selected = body.get("rows", [])
    if not isinstance(selected, list) or not selected or len(selected) > 3670:
        raise ValueError("请至少选择一天调出项目工时")
    balances={}
    for name in sources:
        if name==report['public_project']:
            balances[name]={r['date']:Decimal(r['hours']) for r in report['public_hours_candidates']}
        else:
            if name not in report.get('project_totals',{}):raise ValueError('调出项目不在本次查询结果中')
            balances[name]={r['date']:Decimal(str(r['hours'].get(name,0))) for r in report.get('daily',[]) if Decimal(str(r['hours'].get(name,0)))>0}
    available={}
    for days in balances.values():
        for day,hours in days.items():available[day]=available.get(day,Decimal(0))+hours
    seen = set()
    daily_totals = {}
    adjustments = []
    total = Decimal(0)
    for row in selected:
        if not isinstance(row, dict):
            raise ValueError("调整明细格式错误")
        day = row.get("date")
        target = str(row.get("target_project", body.get("target_project", ""))).strip()
        if not target or len(target) > 180 or target in sources:
            raise ValueError("请选择不同于调出项目的目标项目")
        try:
            hours = Decimal(str(row.get("hours")))
        except InvalidOperation:
            raise ValueError("工时必须是有效数字") from None
        if (day, target) in seen or day not in available:
            raise ValueError("存在重复的日期与调入项目，或非调出项目工时日期")
        if not hours.is_finite() or hours <= 0 or hours > available[day]:
            raise ValueError(f"{day} 调整量须大于 0 且不超过该日调出项目工时")
        if hours.as_tuple().exponent < -2:
            raise ValueError("工时最多保留两位小数；OA 支持的精度仍需填写时核实")
        seen.add((day, target))
        daily_totals[day] = daily_totals.get(day, Decimal(0)) + hours
        if daily_totals[day] > available[day]:
            raise ValueError(f"{day} 各项目分配合计不能超过当天调出项目工时")
        total += hours
        adjustments.append({"date": day, "hours": str(hours),
                            "source_project": source, "target_project": target})
    adjustments.sort(key=lambda r: (r["date"], r["target_project"]))
    withdrawals=[]
    for day,amount in sorted(daily_totals.items()):
        cents=int(amount*100)
        weighted=[(name,Decimal(cents)*balances[name].get(day,Decimal(0))/available[day]) for name in sources]
        parts={name:int(value) for name,value in weighted}
        remaining=cents-sum(parts.values())
        for name,value in sorted(weighted,key=lambda pair:(-(pair[1]-int(pair[1])),pair[0]))[:remaining]:parts[name]+=1
        for name in sources:
            if parts[name]:withdrawals.append({'date':day,'source_project':name,'hours':str(amount) if len(sources)==1 else format(Decimal(parts[name])/100,'.2f')})
    targets = sorted({r["target_project"] for r in adjustments})
    return {"mode": "local_preview", "employee": {k:profile[k] for k in ("id", "name", "employee_code")},
            "public_project": profile["public_project"], "source_project": source, "target_project": targets[0] if len(targets) == 1 else "",
            "target_projects": targets, "source_projects": sources, "source_withdrawals": withdrawals,
            "application_reason": reason, "adjustments": adjustments, "total_hours": str(total),
            "created_at": datetime.now().astimezone().isoformat(), "report_id": report_id(report),
            "oa_saved": False, "oa_submitted": False, "oa_project_id_resolved": False,
            "pending_adjustments_checked": False}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        super().end_headers()

    def respond(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def trusted_request(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host") not in allowed:
            self.respond({"error": "只接受本机访问"}, 403)
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + h for h in allowed}:
            self.respond({"error": "请求来源不匹配"}, 403)
            return False
        return True

    def do_GET(self):
        if not self.trusted_request():
            return
        path = urlsplit(self.path).path
        if path == "/api/bootstrap":
            if not get_session().http.cookies:deactivate_employee()
            with LOCK:
                profile = load(PROFILE_FILE, DEFAULT_PROFILE)
                report = load(REPORT_FILE, None)
                if report:
                    annotate_calendar(report)
                    write_json(REPORT_FILE,report)
            self.respond({"profile": profile, "report": report,
                          "report_id": report_id(report) if report else None,
                          "mode": "draft_only"})
        elif path == "/api/oa-draft/status":
            with LOCK:
                state = dict(DRAFT_PROGRESS)
            self.respond({"active": state["active"], "message": state["message"],
                          "elapsed_seconds": int(time.monotonic() - state["started"]) if state["active"] else 0})
        elif path in {"/", "/index.html", "/static/app.js", "/static/styles.css", "/favicon.svg"}:
            super().do_GET()
        else:
            self.respond({"error": "页面不存在"}, 404)

    def do_POST(self):
        if not self.trusted_request():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 100000 or self.headers.get_content_type() != "application/json":
                raise ValueError("请求格式错误")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("请求必须为对象")
            path = urlsplit(self.path).path
            if path in ('/api/projects/validate','/api/projects/search'):
                name=str(body.get('name','')).strip()
                if not name or len(name)>180:raise ValueError('请填写不超过 180 字符的完整项目名称')
                with LOCK:
                    profile=load(PROFILE_FILE,DEFAULT_PROFILE)
                client=get_session()
                with client.lock:
                    if client.identity()['id']!=profile['id']:raise ValueError('OA 当前账号与工作台账号不一致')
                    form=OAForm(client,load_details=False)
                    result=form.search_projects(name) if path.endswith('/search') else {'project':form.resolve_project(name)}
                self.respond(result)
            elif path == '/api/oa-saved':
                with LOCK:
                    profile=load(PROFILE_FILE,DEFAULT_PROFILE)
                self.respond(saved_adjustments(get_session(),profile['id']))
            elif path == '/api/auth/clear':
                if not DRAFT_LOCK.acquire(blocking=False):
                    raise ValueError('正在创建 OA 表单，请完成后再清除登录态')
                try:
                    if not QUERY_LOCK.acquire(blocking=False):
                        raise ValueError('正在查询工时，请完成后再清除登录态')
                    try:
                        result=clear_login(get_session())
                        result['profile']=deactivate_employee()
                        (DATA_ROOT / 'auth-debug/callback.html').unlink(missing_ok=True)
                        self.respond(result)
                    finally:
                        QUERY_LOCK.release()
                finally:
                    DRAFT_LOCK.release()
            elif path in {"/api/auth/start", "/api/auth/status"}:
                if not DRAFT_LOCK.acquire(blocking=False):raise ValueError('请等待 OA 草稿保存完成后再登录')
                try:
                    if not QUERY_LOCK.acquire(blocking=False):raise ValueError('请等待工时查询完成后再登录')
                    try:
                        client=get_session()
                        with client.lock:
                            result=login_status(client,None,start=path.endswith('/start'))
                            if result.get('status')=='authenticated':
                                result['profile']=activate_employee(client,result['employee'])
                        self.respond(result)
                    finally:QUERY_LOCK.release()
                finally:DRAFT_LOCK.release()
            elif path == "/api/query":
                start, end = date.fromisoformat(body["start"]), date.fromisoformat(body["end"])
                with LOCK:
                    profile = load(PROFILE_FILE, DEFAULT_PROFILE)
                if not QUERY_LOCK.acquire(blocking=False):
                    self.respond({"error": "已有查询正在进行，请稍后再试"}, 409)
                    return
                try:
                    if not profile["id"]:raise OAAuthRequired("请先扫码登录 OA，自动识别员工身份")
                    if not profile["public_project"]:raise ValueError("请先在个人设置填写你的公共项目")
                    report = query_report(get_session(), start, end, profile["public_project"], profile["id"])
                    with LOCK:
                        current = load(PROFILE_FILE, DEFAULT_PROFILE)
                        if current != profile:
                            raise ValueError("查询期间公共项目发生变化，请重新查询")
                        write_json(REPORT_FILE, report)
                    self.respond({"report": report, "report_id": report_id(report)})
                finally:
                    QUERY_LOCK.release()
            elif path == "/api/profile":
                public = str(body.get("public_project", "")).strip()
                if not public or len(public) > 180:
                    raise ValueError("请填写有效的个人公共工时项目名称")
                with LOCK:
                    profile = dict(load(PROFILE_FILE, DEFAULT_PROFILE), public_project=public)
                    if not profile["id"]:raise OAAuthRequired("请先扫码登录 OA")
                    write_json(PROFILE_FILE, profile)
                self.respond({"profile": profile})
            elif path == "/api/preview":
                with LOCK:
                    preview = validate_plan(body, load(REPORT_FILE, None), load(PROFILE_FILE, DEFAULT_PROFILE))
                self.respond({"preview": preview})
            elif path == "/api/oa-draft":
                self.respond({"draft": make_draft(body, get_session())})
            else:
                self.respond({"error": "不支持此操作"}, 404)
        except OAAuthRequired as error:
            self.respond({"error": str(error), "code": "oa_login_required"}, 401)
        except (ValueError, KeyError, TypeError) as error:
            self.respond({"error": str(error)}, 400)
        except Exception:
            self.respond({"error": "暂时无法连接 OA，请重试；若工作台尚未登录，请使用页面内的扫码登录。", "code": "oa_connection_error"}, 502)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18767)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1–65535 之间")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        parser.exit(1, f"无法启动：端口 {args.port} 不可用。请关闭已运行的工作台，或使用 --port 指定其他端口。\n")
    print(f"工时工作台已启动：http://127.0.0.1:{args.port}/", flush=True)
    print(f"个人数据目录：{DATA_ROOT}\n按 Ctrl+C 停止服务。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
