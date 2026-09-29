import threading
import unittest
from unittest.mock import Mock
from oa_saved import _request_list, saved_adjustments

def saved_only(client, employee_id):
    if client.identity()["id"] != str(employee_id):
        raise ValueError("wrong account")
    items=_request_list(client,employee_id,{"nodetype":"0"},"saved")
    return {"items":sorted(items,key=lambda x:int(x["request_id"]),reverse=True),"total":len(items)}

class SavedTests(unittest.TestCase):
    def client(self, rows, count=None):
        c=Mock();c.lock=threading.RLock();c.identity.return_value={'id':'1'}
        c.api.side_effect=[{'sessionkey':'test'},{'status':True,'count':len(rows) if count is None else count},
                           {'status':True,'datas':rows}]
        return c

    def row(self, rid='123'):
        return {'requestid':rid,'creater':'1','workflowid':'110092','currentnodeidspan':'创建',
                'createdatespan':'2026-09-29 10:00:00','requestname':'非常规工时调整流程'}

    def test_pagination_and_trusted_links(self):
        c=self.client([self.row()],2)
        c.api.side_effect=[{'sessionkey':'test'},{'status':True,'count':2},
            {'status':True,'datas':[self.row()]},{'status':True,'datas':[self.row('124')]}]
        result=saved_only(c,'1')
        self.assertEqual(result['total'],2)
        self.assertEqual(result['items'][0]['request_id'],'124')
        self.assertTrue(result['items'][0]['url'].startswith('https://i.thundersoft.com/'))
        self.assertEqual(c.api.call_args.kwargs['data']['current'],2)

    def test_empty_is_success_only_with_valid_count(self):
        self.assertEqual(saved_only(self.client([]),'1')['items'],[])
        c=self.client([]);c.api.side_effect=[{'sessionkey':'test'},{'status':False}]
        with self.assertRaises(ValueError):saved_only(c,'1')

    def test_wrong_account_or_filters_rejected(self):
        c=self.client([])
        with self.assertRaises(ValueError):saved_adjustments(c,'2')
        c.api.assert_not_called()
        for field,value in [('creater','2'),('workflowid','9'),('currentnodeidspan','批准'),('requestid','javascript:')]:
            row=self.row();row[field]=value
            with self.assertRaises(ValueError):saved_only(self.client([row]),'1')

    def test_saved_and_pending_are_separate(self):
        pending=self.row('456');pending['currentnodeidspan']='PMO'
        c=self.client([])
        c.api.side_effect=[{'sessionkey':'saved'},{'status':True,'count':1},
            {'status':True,'datas':[self.row()]},{'sessionkey':'pending'},
            {'status':True,'count':1},{'status':True,'datas':[pending]}]
        result=saved_adjustments(c,'1')
        self.assertEqual({r['request_id']:r['category'] for r in result['items']},{'123':'saved','456':'pending'})
        self.assertEqual(result['items'][0]['node'],'PMO')
        self.assertEqual(c.api.call_args_list[3].kwargs['data']['archivestatus'],'2')

    def test_incomplete_page_is_not_reported_as_empty(self):
        with self.assertRaises(ValueError):saved_only(self.client([],1),'1')

if __name__=='__main__':unittest.main()
