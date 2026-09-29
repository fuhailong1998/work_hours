"""Read OA form metadata, resolve projects and evaluate field linkage over HTTP."""
from collections import deque


class OAForm:
    def __init__(self, client):
        self.client = client
        self.identity = client.identity()
        self.schema = client.request('POST', '/api/workflow/reqform/loadForm',
                                     data={'iscreate':'1', 'workflowid':'83592'}).json()
        self.base = self.schema['submitParams']
        if str(self.base['formid']) != '-1099' or str(self.base['workflowid']) != '110092':
            raise ValueError('OA 表单定义已变化')
        self.fields = {table: {v.get('fieldname','').lower(): str(k)
                              for k,v in info['fieldinfomap'].items()}
                       for table,info in self.schema['tableInfo'].items()}

    def common(self):
        return {k:self.base[k] for k in ('requestid','workflowid','nodeid','formid','isbill',
                'linkageUUID','f_weaver_belongto_userid','f_weaver_belongto_usertype')}

    def project(self, name):
        field = self.fields['detail_1']['dzxm']
        info = self.schema['tableInfo']['detail_1']['fieldinfomap'][field]
        params = dict(self.common(), type=info['fielddbtype'], fielddbtype=info['fielddbtype'],
                      wfid=self.base['workflowid'], billid=self.base['formid'], fieldid=field,
                      viewtype='1',fromModule='workflow',wfCreater=self.identity['id'],
                      pageSize='100',current='1',min='1',max='100',companyId='1',
                      con9981_value=name,isFromAdvanceSearch='1',disabledConditionCache='true')
        data = self.client.request('GET','/api/public/browser/data/161',params=params).json()
        rows = data.get('datas',[])
        matches = [r for r in rows if r.get('xmmc') == name]
        if len(matches) != 1 or int(data.get('total',0)) > len(rows):
            raise ValueError(f'项目“{name}”未唯一匹配，请使用 OA 完整名称')
        return {'id':str(matches[0]['id']),'name':name,'code':matches[0].get('xmbh','')}

    def linked_values(self, table, values, row=0):
        """Run the server's configured data-input rules until their inputs stabilize."""
        suffix = '' if table == 'main' else f'_{row}'
        fields = self.schema['tableInfo'][table]['fieldinfomap']
        config = {}
        for kind, endpoint in [('dataInputCfg','reqDataInputResult'),('fieldSqlCfg','reqFieldSqlResult')]:
            for trigger,rules in self.schema['linkageCfg'][kind].items():
                config.setdefault(trigger,[]).extend(dict(r, endpoint=endpoint) for r in rules)
        values = dict(values)
        queue = deque(k[5:].split('_')[0] for k in values if k.startswith('field'))
        executed = set()
        while queue:
            trigger = queue.popleft()
            for rule in config.get(trigger,[]):
                if trigger not in fields: continue
                ident = str(rule['config'])
                inputs = list(dict.fromkeys([trigger]+rule.get('relateFields',[])))
                fingerprint = (ident,tuple(values.get('field'+str(f)+suffix, '') for f in inputs))
                if fingerprint in executed: continue
                if len(executed) > 100: raise ValueError('OA 联动未收敛，停止准备表单')
                executed.add(fingerprint)
                params = dict(self.common(),triSource='1',showAI='1',linkageid=ident)
                params.update({f'triFieldid_{ident}':trigger,f'rowIndexStr_{ident}':str(row) if suffix else '-1',
                               f'triTableMark_{ident}':table})
                params.update({'field'+str(f)+suffix:values.get('field'+str(f)+suffix,'') for f in inputs})
                result = self.client.request('POST','/api/workflow/linkage/'+rule['endpoint'],data=params).json()
                assigned = result.get('assignInfo_'+ident)
                if not assigned or assigned.get('resultOutOfLimit'):
                    raise ValueError('OA 字段联动返回不完整')
                for key, obj in assigned.get('changeValue',{}).items():
                    value = str(obj.get('value',''))
                    if values.get(key) != value:
                        values[key] = value
                        queue.append(key[5:].split('_')[0])
        return values

    def prepare(self, plan, expanded, progress=lambda message:None):
        """Prepare a reviewable payload without saving any OA request."""
        import json
        if self.identity['id'] != plan['employee']['id']:
            raise ValueError('OA 当前账号与计划员工不一致')
        params = self.schema['params']
        details = self.client.api('/api/workflow/reqform/detailData',data={
            'iscreate':'1','workflowid':'83592','detailmark':'detail_1,detail_2,detail_3',
            'reqParams':json.dumps(params),
            'f_weaver_belongto_userid':self.identity['id'],'f_weaver_belongto_usertype':'0'})
        defaults = details['detail_1']['addRowDefValue']
        projects = {}
        template = {}
        rows = []
        mapping = self.fields['detail_1']
        for position,row in enumerate(expanded):
            progress(f'正在通过接口准备明细 {position+1}/{len(expanded)}')
            name = row['project']
            if name not in projects:
                projects[name] = self.project(name)
                values = {k+'_0':str(v.get('value','')) for k,v in defaults.items()}
                values['field'+mapping['ygxm']+'_0'] = self.identity['id']
                values['field'+mapping['dzxm']+'_0'] = projects[name]['id']
                template[name] = self.linked_values('detail_1',values)
            values = {k.rsplit('_',1)[0]+'_'+str(position):v for k,v in template[name].items()}
            for field,value in [('ygxm',self.identity['id']),('dzxm',projects[name]['id']),
                                ('dzlx',row['direction']),('dzyf',row['day'][:7]),
                                ('ksrq',row['day']),('jsrq',row['day']),('dzgsl',row['hours'])]:
                values['field'+mapping[field]+'_'+str(position)] = value
            if values.get('field'+mapping['ygbh']+'_'+str(position)) != plan['employee']['employee_code'] or values.get('field'+mapping['yglx']+'_'+str(position)) != '1':
                raise ValueError('员工接口联动结果与计划不一致')
            rows.append(values)
        main = {k:str(v.get('value','')) for k,v in self.schema['maindata'].items()}
        main = self.linked_values('main',main)
        main['field'+self.fields['main']['sqyy']] = plan['application_reason']
        return {'schema':self.schema,'main':main,'rows':rows,'projects':projects}
