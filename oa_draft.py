"""Create OA drafts entirely over HTTP: initialize, link, save, and verify."""
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit, urlencode
from oa_http import get_session, OA_ORIGIN
from oa_form_api import OAForm, value

SAVE_PATH = "/api/workflow/reqform/requestOperation"


def expand_rows(plan):
    # Withdraw once per date, then credit each destination on that exact date.
    by_day = {}
    for row in plan["adjustments"]:
        by_day.setdefault(row["date"], []).append(row)
    result = []
    for day, allocations in sorted(by_day.items()):
        total = sum((Decimal(row["hours"]) for row in allocations), Decimal(0))
        if 'source_withdrawals' in plan:
            for item in plan['source_withdrawals']:
                if item['date']==day:result.append(dict(day=day,hours=item['hours'],project=item['source_project'],direction='0'))
        else:
            result.append(dict(day=day, hours=str(total), project=plan.get("source_project",plan["public_project"]), direction="0"))
        for row in allocations:
            result.append(dict(day=day, hours=row["hours"],
                               project=row.get("target_project") or plan["target_project"], direction="1"))
    return result


def validate_save_request(request):
    url = urlsplit(request["url"])
    values = parse_qs(request["body"], keep_blank_values=True)
    if (url.scheme != "https" or url.hostname != "i.thundersoft.com" or url.path != SAVE_PATH
            or values.get("src") != ["save"] or values.get("requestid") != ["-1"]
            or values.get("actiontype") != ["requestOperation"]
            or values.get("workflowid") != ["110092"]
            or values.get("isaffirmance", ["0"])[0] not in ("", "0")):
        raise ValueError("OA 保存参数不符合新建草稿要求，未发送")



def send_save_request(client, request):
    validate_save_request(request)
    response = client.request('POST', SAVE_PATH, data=request['body'],
                              headers={'Content-Type':'application/x-www-form-urlencoded'})
    payload = response.json()
    data = payload.get('data', {})
    request_id = str(data.get('resultInfo', {}).get('requestid', ''))
    if data.get('type') != 'SUCCESS' or not request_id.isdigit() or int(request_id) <= 0:
        raise ValueError('OA 保存接口未确认草稿编号，结果需核实')
    return request_id


def verify_saved(form, expected, employee_id, reason):
    rows=form.detail['detail_1'].get('rowDatas',{})
    actual=[rows[key] for key in sorted(rows,key=lambda k:int(k.split('_')[-1]))]
    if len(actual)!=len(expected):raise ValueError('OA 草稿回读明细行数不一致')
    for data,item in zip(actual,expected):
        wanted={'ygxm':employee_id,'dzxm':item['project_id'],'dzlx':item['direction'],
                'dzyf':item['day'][:7],'ksrq':item['day'],'jsrq':item['day']}
        if any(value(data.get('field'+form.names[k],{}))!=str(v) for k,v in wanted.items()):
            raise ValueError('OA 草稿回读字段与计划不一致')
        if Decimal(value(data.get('field'+form.names['dzgsl'],{})) or '0')!=Decimal(item['hours']):
            raise ValueError('OA 草稿回读工时与计划不一致')
    reason_id=next(k for k,f in form.tables['main']['fieldinfomap'].items() if f.get('fieldname','').lower()=='sqyy')
    if value(form.main.get('field'+reason_id,{}))!=reason:
        raise ValueError('OA 草稿回读申请原因与计划不一致')


def create_draft(client, plan, before_save, saved, progress=lambda message: None):
    client=client if hasattr(client,'identity') else get_session()
    identity=client.identity()
    if identity['id']!=plan['employee']['id']:raise ValueError('OA 登录身份与计划员工不一致')
    progress('正在通过接口初始化 OA 表单')
    form=OAForm(client)
    expected=expand_rows(plan)
    payload=form.prepare(plan,expected,progress)
    request={'url':OA_ORIGIN+SAVE_PATH,'body':urlencode(payload)}
    validate_save_request(request)
    progress('正在通过接口保存 OA 草稿')
    before_save()
    request_id=send_save_request(client,request)
    result={'request_id':request_id,'url':OA_ORIGIN+'/spa/workflow/static4form/index.html#/main/workflow/req?requestid='+request_id,
            'oa_saved':True,'oa_submitted':False,'verified':False,'projects':form.projects}
    saved(result)
    progress('草稿已保存，正在通过接口回读核验')
    readback=OAForm(client,request_id)
    verify_saved(readback,expected,identity['id'],plan['application_reason'])
    result['verified']=True
    saved(result)
    return result
