import unittest
from unittest.mock import Mock
from urllib.parse import urlencode
from oa_draft import validate_save_request, send_save_request


class SaveTransportTests(unittest.TestCase):
    def request(self, **overrides):
        fields = dict(src='save', requestid='-1', actiontype='requestOperation', workflowid='110092')
        fields.update(overrides)
        return {'url':'https://i.thundersoft.com/api/workflow/reqform/requestOperation',
                'body':urlencode(fields), 'headers':{'content-type':'application/x-www-form-urlencoded',
                                                     'cookie':'must-use-context', 'content-length':'1'}}

    def test_forbids_submit_existing_requests_and_wrong_workflow(self):
        for change in [dict(src='submit'),dict(requestid='123'),dict(workflowid='123'),
                       dict(isaffirmance='1'),dict(actiontype='remarkOperation')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_save_request(self.request(**change))
        req=self.request();req['url']='https://example.com/api/workflow/reqform/requestOperation'
        with self.assertRaises(ValueError): validate_save_request(req)

    def test_save_sends_once_with_original_payload_and_shared_session(self):
        context=Mock()
        context.request.return_value.ok=True
        context.request.return_value.json.return_value={'data':{'type':'SUCCESS','resultInfo':{'requestid':123}}}
        req=self.request()
        self.assertEqual(send_save_request(context,req),'123')
        context.request.assert_called_once()
        args=context.request.call_args.kwargs
        self.assertEqual(args['data'],req['body'])
        self.assertNotIn('cookie',args['headers'])

    def test_failure_or_missing_id_is_not_success_or_retried(self):
        for data in [{'data':{'type':'FAILD'}},{'data':{'type':'SUCCESS','resultInfo':{}}}]:
            context=Mock()
            context.request.return_value.ok=True
            context.request.return_value.json.return_value=data
            with self.assertRaises(ValueError): send_save_request(context,self.request())
            context.request.assert_called_once()

if __name__=='__main__': unittest.main()
