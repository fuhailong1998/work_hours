import ast
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from oa_http import OASession, OAAuthRequired
from oa_rules import apply_save_rules
from query_hours import query_report


class HTTPWorkflowTests(unittest.TestCase):
    def test_runtime_has_no_browser_automation_imports(self):
        for path in Path('.').glob('*.py'):
            tree=ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import): names=[x.name for x in node.names]
                elif isinstance(node,ast.ImportFrom): names=[node.module or '']
                else:continue
                self.assertFalse(any(n.startswith(('playwright','selenium','pyppeteer')) for n in names),path)

    def test_http_uses_proxy_environment_no_redirect_or_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            client=OASession(Path(folder)/'cookies.json')
            self.assertTrue(client.http.trust_env)
            response=Mock(status_code=200)
            with patch.object(client.http,'request',return_value=response) as send:
                client.request('POST','/api/workflow/reqform/requestOperation',data='src=save')
            send.assert_called_once()
            self.assertFalse(send.call_args.kwargs['allow_redirects'])
            self.assertEqual(client.http.adapters['https://'].max_retries.total,0)
            self.assertEqual(client.path.stat().st_mode & 0o777,0o600)
            with self.assertRaises(ValueError):client.request('GET','//example.com')

    def test_login_redirect_requires_authorization(self):
        with tempfile.TemporaryDirectory() as folder:
            client=OASession(Path(folder)/'cookies.json')
            with patch.object(client.http,'request',return_value=Mock(status_code=302)):
                with self.assertRaises(OAAuthRequired):client.api('/api/hrm/login/getAccountList')

    def test_report_parses_http_html_and_verifies_identity(self):
        client=Mock()
        client.identity.return_value={'id':'1','name':'Test'}
        client.request.return_value.text='''<div>2026-09-21至2026-09-21人员工时报表</div>
        <table><tr><td><table><tr><td>项目名称</td><td>PUBLIC</td><td>合计</td></tr>
        <tr><td>2026-09-21</td><td>8</td><td>8</td></tr><tr><td>合计</td><td>8</td><td>8</td></tr></table></td></tr></table>'''
        client.request.return_value.url='https://i.thundersoft.com/report'
        report=query_report(client,date(2026,9,21),date(2026,9,21),'PUBLIC','1')
        self.assertEqual(report['public_hours_candidates'],[{'date':'2026-09-21','hours':'8'}])
        with self.assertRaises(ValueError):query_report(client,date(2026,9,21),date(2026,9,21),'PUBLIC','2')

    def test_native_browser_sum_and_project_duplicates_are_preserved(self):
        from oa_form_api import OAForm
        f=OAForm.__new__(OAForm)
        f.cfg={'formulaCfg':{'formulas':[
            {'formula':'[main.1]=SUM([detail_1.2])'},
            {'formula':'[main.3]=[detail_1.4]'},
            {'formula':'[main.5]=SUM([detail_1.6])'}]}}
        f.rows=[{'field2':{'value':'10'},'field4':{'value':'20'},'field6':{'value':'0.25'}}]*2
        f.tables={'main':{'fieldinfomap':{'1':{'htmltype':3},'3':{'htmltype':3},'5':{'htmltype':1}}},
                  'detail_1':{'fieldinfomap':{'2':{'htmltype':3},'4':{'htmltype':3},'6':{'htmltype':1}}}}
        f.base={'formid':'-1099','requestid':'-1'};f.main={};f.client=Mock()
        f.client.api.return_value={'result':json.dumps([
            {'destFieldid':'field1','destFieldValue':{'value':'0'}},
            {'destFieldid':'field3','destFieldValue':{'value':'20,20'}},
            {'destFieldid':'field5','destFieldValue':{'value':'0.50'}}])}
        f.apply_formulas()
        values=json.loads(f.client.api.call_args.kwargs['data']['arrayInfo'])
        self.assertEqual([v['fieldvalue'] for v in values],['0','20,20','0.50'])

    def test_save_rules_balance_manager_approval_and_copy(self):
        def row(project,direction,manager,am):
            values={'61126':project,'60578':direction,'60585':manager,'71074':am,'60588':'30',
                    '60607':'2026-09','60580':'2026-09-21','122710':'1'}
            return {'field'+k:{'value':v} for k,v in values.items()}
        main={};rows=[row('OS_PUBLIC','0','10','20'),row('PROJECT','1','11','21')]
        apply_save_rules(main,rows,date(2026,9,29))
        self.assertEqual(main['field80554']['value'],'11')
        self.assertEqual(main['field80555']['value'],'10')
        self.assertEqual(main['field71063']['value'],'21')
        self.assertEqual(main['field71073']['value'],'0')
        self.assertEqual(rows[1]['field122708']['value'],'1')
        rows[1]['field60585']['value']='10'
        apply_save_rules(main,rows,date(2026,9,29))
        self.assertEqual(main['field80555']['value'],'')

if __name__=='__main__':unittest.main()
