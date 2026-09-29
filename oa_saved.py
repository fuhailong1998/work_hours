"""Read the current employee's saved and in-progress adjustment requests."""
from datetime import datetime
from oa_http import OA_ORIGIN


def saved_adjustments(client, employee_id):
    with client.lock:
        if client.identity()['id'] != str(employee_id):
            raise ValueError('OA 当前账号与工作台账号不一致')
        saved=_request_list(client, employee_id, {'nodetype':'0'}, 'saved')
        pending=_request_list(client, employee_id, {'archivestatus':'2'}, 'pending')
        # A request can move between the two queries; use the later status.
        items={item['request_id']:item for item in saved+pending}
        return {'items':sorted(items.values(),key=lambda x:(x['created_at'],int(x['request_id'])),reverse=True),
                'total':len(items),'checked_at':datetime.now().astimezone().isoformat()}


def _request_list(client, employee_id, filters, category):
    query=client.api('/api/workflow/reqlist/splitPageKey',data={
        'viewScope':'mine','complete':2,'date2during':0,'actiontype':'splitpage',
        'workflowid':'110092','wfstatu':'1',**filters})
    key=query.get('sessionkey')
    if not key:raise ValueError('OA 未返回调整流程查询凭据')
    count=client.api('/api/ec/dev/table/counts',data={'dataKey':key})
    if count.get('status') is not True or 'count' not in count:
        raise ValueError('OA 未返回调整流程数量，请重试')
    total=int(count['count']);items={};seen=set();current=1
    while len(seen)<total:
        page=client.api('/api/ec/dev/table/datas',data={'dataKey':key,'current':current,'sortParams':'[]'})
        if page.get('status') is not True or not isinstance(page.get('datas'),list):
            raise ValueError('OA 调整流程查询失败，请重试')
        before=len(seen)
        for row in page['datas']:
            rid=str(row.get('requestid',''))
            if not rid.isdigit() or int(rid)<=0:raise ValueError('OA 返回无效的流程编号')
            seen.add(rid)
            if str(row.get('creater'))!=str(employee_id) or str(row.get('workflowid'))!='110092':
                raise ValueError('OA 返回的流程不符合员工或流程类型筛选条件')
            if category=='saved' and row.get('currentnodeidspan')!='创建':
                raise ValueError('OA 返回的流程已离开创建节点，请重新检查')
            items[rid]={'request_id':rid,'title':row.get('requestname','非常规工时调整流程'),
                'created_at':row.get('createdatespan') or row.get('createdate',''),
                'node':row.get('currentnodeidspan') or '未知节点',
                'category':'saved' if row.get('currentnodeidspan')=='创建' else category,
                'url':OA_ORIGIN+'/spa/workflow/static4form/index.html#/main/workflow/req?requestid='+rid}
        if len(seen)==before or current>=1000:
            raise ValueError('OA 流程列表未读取完整，请重新检查')
        current+=1
    return list(items.values())
