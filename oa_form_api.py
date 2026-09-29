"""Prepare OA form data using the observed load, browser-data, and linkage HTTP APIs."""
import copy
import json
import re
from decimal import Decimal, InvalidOperation
from oa_rules import apply_save_rules

BASE_FIELDS = ('requestid','workflowid','nodeid','formid','isbill','f_weaver_belongto_userid','f_weaver_belongto_usertype')


def value(data):
    return str(data.get('value', '')) if isinstance(data, dict) else str(data or '')


class OAForm:
    def __init__(self, client, request_id=None, load_details=True):
        self.client=client
        self.data=client.api('/api/workflow/reqform/loadForm', data=(
            {'requestid':str(request_id)} if request_id else {'iscreate':'1','workflowid':'83592'}))
        self.params=self.data.get('params',{})
        self.submit=self.data.get('submitParams',{})
        if str(self.params.get('formid'))!='-1099' or str(self.params.get('workflowid'))!='110092':
            raise ValueError('OA 表单类型或接口结构发生变化')
        self.base={k:str(self.params.get(k,self.submit.get(k,''))) for k in BASE_FIELDS}
        self.base['requestid']=str(request_id or '-1')
        self.cfg=self.data['linkageCfg']
        self.tables=self.data['tableInfo']
        self.fields=self.tables['detail_1']['fieldinfomap']
        self.names={f.get('fieldname','').lower():str(k) for k,f in self.fields.items()}
        self.main=copy.deepcopy(self.data['maindata'])
        self.detail=client.api('/api/workflow/reqform/detailData',data=dict(self.base,
            iscreate='0' if request_id else '1',detailmark='detail_1,detail_2,detail_3',
            reqParams=json.dumps(dict(self.params,**self.base)))) if load_details else {}
        self.rows=[]
        self.projects={}

    def link_main(self):
        for trigger, rules in self.cfg.get('dataInputCfg',{}).items():
            if trigger not in self.tables['main']['fieldinfomap']:continue
            for rule in rules:
                config=str(rule['config'])
                args=dict(self.base,triSource='1',showAI='1',linkageid=config,
                          linkageUUID=self.submit['linkageUUID'],wfTestStr='')
                args.update({f'triFieldid_{config}':trigger,f'rowIndexStr_{config}':'-1',
                             f'triTableMark_{config}':'main'})
                args.update({'field'+f:value(self.main.get('field'+f,{})) for f in rule['relateFields']})
                info=self.client.api('/api/workflow/linkage/reqDataInputResult',data=args).get('assignInfo_'+config)
                if not isinstance(info,dict) or info.get('resultOutOfLimit'):raise ValueError('OA 主表联动未返回完整结果')
                self.main.update(info.get('changeValue',{}))

    def search_projects(self, name):
        field=self.names['dzxm']
        data=self.client.api('/api/public/browser/data/161',params=dict(self.base,
            pageSize=100,current=1,min=1,max=100,companyId=1,con9981_value=name,isFromAdvanceSearch=1,
            type=self.fields[field]['fielddbtype'],fielddbtype=self.fields[field]['fielddbtype'],
            wfid=self.base['workflowid'],billid=self.base['formid'],fieldid=field,viewtype=1,
            fromModule='workflow',wfCreater=self.base['f_weaver_belongto_userid'],disabledConditionCache='true'))
        rows=data.get('datas')
        if not isinstance(rows,list):raise ValueError('OA 项目查询未返回有效列表')
        return {'items':[{'id':str(r['id']),'name':r['xmmc'],'code':r.get('xmbh','')} for r in rows],
                'total':int(data.get('total',len(rows)))}

    def resolve_project(self, name):
        if name in self.projects:return self.projects[name]
        data=self.search_projects(name)
        rows=data['items']
        exact=[r for r in rows if r.get('name')==name]
        if len(exact)!=1 or int(data.get('total',0))>len(rows):
            raise ValueError(f'项目“{name}”未唯一匹配，请使用 OA 完整项目名称')
        result={'id':str(exact[0]['id']),'name':name,'code':exact[0].get('code','')}
        self.projects[name]=result
        return result

    def link_row(self, row, index):
        pending=list(k[5:] for k in row)
        seen=set()
        for _ in range(100):
            if not pending:return
            trigger=pending.pop(0)
            for cfg_name,endpoint in [('dataInputCfg','reqDataInputResult'),('fieldSqlCfg','reqFieldSqlResult')]:
                for rule in self.cfg.get(cfg_name,{}).get(trigger,[]):
                    related={f'field{f}_{index}':value(row.get('field'+f,{})) for f in rule['relateFields']}
                    key=(cfg_name,str(rule['config']),tuple(related.items()))
                    if key in seen:continue
                    seen.add(key)
                    config=str(rule['config'])
                    args=dict(self.base,triSource='1',showAI='1',linkageid=config,
                              linkageUUID=self.submit['linkageUUID'],wfTestStr='')
                    args.update({f'triFieldid_{config}':trigger,f'rowIndexStr_{config}':str(index),
                                 f'triTableMark_{config}':'detail_1',**related})
                    result=self.client.api('/api/workflow/linkage/'+endpoint,data=args)
                    info=result.get('assignInfo_'+config)
                    if not isinstance(info,dict) or info.get('resultOutOfLimit'):
                        raise ValueError('OA 字段联动未返回完整结果，未保存')
                    for target,data in info.get('changeValue',{}).items():
                        base=target.rsplit('_',1)[0]
                        if base[5:] not in self.fields:
                            raise ValueError('OA 联动返回了未识别的字段，未保存')
                        if value(row.get(base,{}))!=value(data):pending.append(base[5:])
                        row[base]=data
        raise ValueError('OA 字段联动未收敛，未保存')

    def prepare(self,plan,expected,progress):
        if self.base['f_weaver_belongto_userid']!=plan['employee']['id']:
            raise ValueError('OA 表单身份与当前员工不一致')
        if any(v.get('rowDatas') for v in self.detail.values()):
            raise ValueError('新 OA 表单已经存在明细，未保存')
        self.link_main()
        for position,item in enumerate(expected):
            progress(f'正在通过接口准备明细 {position+1}/{len(expected)}')
            project=self.resolve_project(item['project'])
            item['project_id']=project['id']
            row=copy.deepcopy(self.detail['detail_1']['addRowDefValue'])
            inputs={'ygxm':plan['employee']['id'],'dzxm':project['id'],'dzlx':item['direction'],
                    'dzyf':item['day'][:7],'ksrq':item['day'],'jsrq':item['day'],'dzgsl':item['hours']}
            for name,val in inputs.items():row['field'+self.names[name]]={'value':str(val)}
            row['field'+self.names['dzxm']]['specialobj']=[{'id':project['id'],'name':project['name']}]
            self.link_row(row,position)
            if value(row.get('field'+self.names['ygbh'],{}))!=plan['employee']['employee_code'] or value(row.get('field'+self.names['yglx'],{}))!='1':
                raise ValueError('OA 员工联动结果不匹配，未保存')
            for name,val in inputs.items():
                if value(row.get('field'+self.names[name],{}))!=str(val):
                    raise ValueError('OA 联动改变了调整明细，未保存')
            self.rows.append(row)
        self.apply_formulas()
        apply_save_rules(self.main,self.rows)
        reason=next(k for k,f in self.tables['main']['fieldinfomap'].items() if f.get('fieldname','').lower()=='sqyy')
        self.main['field'+reason]={'value':plan['application_reason']}
        return self.serialize()

    def apply_formulas(self):
        # Interpret only the observed declarative formulas; never evaluate remote JS/SQL.
        formulas=self.cfg.get('formulaCfg',{}).get('formulas',[])
        relevant=[f['formula'] for f in formulas]
        for formula in relevant:
            match=re.fullmatch(r"\[detail_1\.(\d+)\]=IF\(\[detail_1\.(\d+)\]=='([^']*)',(\d+),(\d+)\)",formula)
            if match:
                dest,source,wanted,yes,no=match.groups()
                for row in self.rows:row['field'+dest]={'value':yes if value(row.get('field'+source,{}))==wanted else no}
        assigns=[]
        for formula in relevant:
            match=re.fullmatch(r'\[main\.(\d+)\]=(SUM\()?\[detail_([123])\.(\d+)\]\)?',formula)
            if not match:
                if re.fullmatch(r"\[detail_1\.(\d+)\]=IF\(\[detail_1\.(\d+)\]=='([^']*)',(\d+),(\d+)\)",formula):continue
                raise ValueError('OA 新增了尚未支持的计算规则，未保存')
            dest,is_sum,detail,source=match.groups()
            vals=[value(row.get('field'+source,{})) for row in self.rows] if detail=='1' else []
            info=self.tables['main']['fieldinfomap'][dest]
            # OA supplies browser-field detail aggregates as comma-separated IDs,
            # not numeric arrays. Its SUM treats a multi-ID string as nonnumeric (0).
            # Preserve duplicates here; assignValue applies each destination's rules.
            joined=','.join(v for v in vals if v)
            source_info=self.tables['detail_'+detail]['fieldinfomap'][source]
            if is_sum and int(source_info['htmltype'])==3:
                try:computed=str(Decimal(joined or '0'))
                except InvalidOperation:computed='0'
            elif is_sum:
                computed=str(sum((Decimal(v or '0') for v in vals),Decimal(0)))
            else:computed=joined
            assigns.append(dict(formid=int(self.base['formid']),isbill='1',fieldid=dest,
                                fieldvalue=computed,requestid=self.base['requestid'],destFieldid='field'+dest))
        if assigns:
            result=self.client.api('/api/workflow/formula/assignValue',data={'arrayInfo':json.dumps(assigns)})
            rows=json.loads(result['result'])
            if len(rows)!=len(assigns):raise ValueError('OA 汇总字段未完整返回，未保存')
            for item in rows:self.main[item['destFieldid']]=item['destFieldValue']

    def serialize(self):
        if self.params.get('openDataVerify') in ('1',1):
            raise ValueError('OA 已启用额外数据签名，当前接口模式尚不支持，未保存')
        auth=self.client.api('/api/workflow/secondauth/getSecondAuthConfig',data={
            'workflowid':self.base['workflowid'],'nodeid':self.base['nodeid'],
            'requestid':'-1','src':'save'})
        if 'isEnableAuth' not in auth or 'isEnableProtect' not in auth:
            raise ValueError('OA 未返回完整的保存认证配置，未保存')
        if str(auth['isEnableAuth'])!='0' or str(auth['isEnableProtect'])!='0':
            raise ValueError('OA 保存需要额外认证或签名，当前接口暂不支持，未保存')
        payload=dict(self.submit)
        payload.update(isWorkflowDoc='false',isOdocRequest='0',actiontype='requestOperation',src='save',type='save',closePage='false',
                       requestid='-1',existChangeRange='main,detail_1',
                       signatureAttributesStr=self.params.get('signatureAttributesStr',''),
                       signatureSecretKey=self.params.get('signatureSecretKey',''),
                       selectNextFlow=self.params.get('selectNextFlow','0'),openDataVerify='0')
        def add(key,data,info):
            payload[key]=value(data)
            if info.get('htmltype')==3 and info.get('detailtype') in (161,162) and data.get('specialobj'):
                payload[key+'name']='##~~@@~~##'.join(o['name'] for o in data['specialobj'])
            if '_' not in key and info.get('htmltype')==3 and info.get('detailtype')==17:
                payload[key+'groupnum']='0'
        for field,data in self.main.items():
            key={'field-1':'requestname','field-2':'requestlevel','field-3':'messageType','field-5':'chatsType'}.get(field,field)
            add(key,data,self.tables['main']['fieldinfomap'].get(field[5:],{}))
        payload['mainFieldUnEmptyCount']=str(sum(bool(value(v)) for k,v in self.main.items() if k[5:].isdigit()))
        for i in range(3):
            payload['nodesnum'+str(i)]=str(len(self.rows) if i==0 else 0)
            payload['indexnum'+str(i)]=payload['nodesnum'+str(i)]
            payload['submitdtlid'+str(i)]=','.join(map(str,range(len(self.rows))))+',' if i==0 else ''
        count=0
        for index,row in enumerate(self.rows):
            for field,data in row.items():
                add(f'{field}_{index}',data,self.fields.get(field[5:],{}))
                count+=bool(value(data))
        payload['detailFieldUnEmptyCount']=str(count)
        return payload
