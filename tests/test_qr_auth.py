import unittest
import json
import tempfile
import threading
from pathlib import Path
import requests
from unittest.mock import Mock, patch
from oa_auth_api import QRFlow, follow, consent_config, APP_ID, CALLBACK, clear_login
from oa_http import OASession
from urllib.parse import urlencode


class QRAuthTests(unittest.TestCase):
    def test_clear_login_removes_credentials_and_scanned_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            client=OASession(root/'cookies.json')
            client.http.cookies.set('session','test-secret',domain='i.thundersoft.com')
            client.persist()
            flow_file=root/'auth-flow.json';flow_file.write_text('{}')
            flow_file.with_suffix('.tmp').write_text('{}')
            report=root/'hours.json';report.write_text('cached report')
            with patch('oa_auth_api.FLOW_FILE',flow_file), patch('oa_auth_api._flow',Mock()):
                self.assertEqual(clear_login(client)['status'],'missing')
                import oa_auth_api
                self.assertIsNone(oa_auth_api._flow)
                self.assertFalse(client.http.cookies)
                self.assertFalse(client.path.exists())
                self.assertFalse(flow_file.exists())
                self.assertFalse(flow_file.with_suffix('.tmp').exists())
                self.assertEqual(report.read_text(),'cached report')
                self.assertEqual(clear_login(client)['status'],'missing')

    def flow(self,step):
        flow=QRFlow.__new__(QRFlow)
        flow.http=Mock();flow.http.cookies={}
        flow.done=False;flow.qr='data:image/png;base64,test';flow.redirect='https://open.feishu.cn/open-apis/authen/v1/index'
        flow.api=Mock(return_value=step)
        flow.step={'next_step':'qr_login_polling'}
        flow.persist=Mock()
        return flow

    def consent(self):
        url='https://accounts.feishu.cn/open-apis/authen/v1/index?'+urlencode({'app_id':APP_ID,'redirect_uri':CALLBACK})
        config={'version':'v1','X-Auth-Flow-Key':'test-flow','data':{'app_info':{'app_id':APP_ID},
                'current_user':{'user_id':'test-user','all_scope_key_list':['auth:user.id:read']}}}
        return Mock(url=url,text='window.serverInjectRes = '+json.dumps(config)+';')

    def test_consent_validates_application_and_callback(self):
        r=self.consent()
        self.assertEqual(consent_config(r.url,r.text)['version'],'v1')
        for url in [r.url.replace(APP_ID,'unexpected'),r.url.replace('larkapproval','untrusted')]:
            with self.assertRaises(ValueError):consent_config(url,r.text)
        with self.assertRaises(ValueError):consent_config(r.url,r.text.replace(APP_ID,'unexpected'))

    @patch('oa_auth_api.follow')
    def test_confirmation_uses_csrf_and_persists_callback(self,follow_mock):
        flow=self.flow({});flow.http.cookies=requests.cookies.RequestsCookieJar()
        flow.http.cookies.set('open_csrf_token','csrf',domain='.feishu.cn')
        flow.http.post.return_value.json.return_value={'code':0,'data':{'redirect_uri':CALLBACK+'?code=test'}}
        flow.complete_consent(self.consent())
        kwargs=flow.http.post.call_args.kwargs
        self.assertEqual(kwargs['headers']['open-csrf-token'],'csrf')
        self.assertEqual(kwargs['headers']['X-Auth-Flow-Key'],'test-flow')
        self.assertEqual(kwargs['json'],{'app_id':APP_ID,'user_id':'test-user','scope':'auth:user.id:read'})
        follow_mock.assert_called_once_with(flow.http,CALLBACK+'?code=test')
        self.assertEqual(flow.callback_url,CALLBACK+'?code=test')

    @patch('oa_auth_api.follow')
    def test_enter_app_does_not_poll_consumed_qr_and_wrong_account_rolls_back(self,follow_mock):
        flow=self.flow({});flow.step={'next_step':'enter_app','step_info':{}}
        follow_mock.return_value=Mock(url='https://i.thundersoft.com/wui/index.html',text='')
        client=Mock();client.lock=threading.RLock();client.http.cookies={'old':'cookie'}
        client.identity.return_value={'id':'other'}
        self.assertEqual(flow.poll(client,{'id':'1','name':'Test'})['status'],'wrong_account')
        self.assertEqual(client.http.cookies,{'old':'cookie'})
        flow.api.assert_not_called()

    def test_resume_preserves_scanned_step(self):
        with tempfile.TemporaryDirectory() as directory, patch('oa_auth_api.FLOW_FILE',Path(directory)/'flow.json'):
            flow=QRFlow.__new__(QRFlow);flow.http=requests.Session()
            flow.step={'next_step':'enter_app'};flow.done=False
            flow.http.cookies.set('test','value',domain='accounts.feishu.cn')
            flow.persist()
            restored=QRFlow.restore()
            self.assertEqual(restored.step,flow.step)
            self.assertEqual(restored.http.cookies.get('test'),'value')

    @patch('oa_auth_api.follow')
    def test_expired_sso_state_reuses_scanned_session(self,follow_mock):
        flow=self.flow({});flow.step={'next_step':'enter_app'}
        flow.complete_consent=Mock(return_value=Mock(url='https://i.thundersoft.com/wui/index.html',text='OA'))
        follow_mock.side_effect=[Mock(url=CALLBACK,text='Unknown RedirectUrl'),self.consent()]
        client=Mock();client.lock=threading.RLock();client.http.cookies={}
        client.identity.return_value={'id':'1'}
        self.assertEqual(flow.poll(client,{'id':'1','name':'Test'})['status'],'authenticated')
        flow.api.assert_not_called()
        flow.complete_consent.assert_called_once()

    @patch('oa_auth_api.follow')
    def test_landed_session_does_not_replay_callback(self,follow_mock):
        flow=self.flow({});flow.step={'next_step':'enter_app'}
        flow.last_url='https://i.thundersoft.com/wui/index.html';flow.callback_url=CALLBACK+'?code=consumed'
        follow_mock.return_value=Mock(url=flow.last_url,text='OA')
        client=Mock();client.lock=threading.RLock();client.http.cookies={};client.identity.return_value={'id':'1'}
        self.assertEqual(flow.poll(client,{'id':'1','name':'Test'})['status'],'authenticated')
        follow_mock.assert_called_once_with(flow.http,flow.last_url)

    def test_scanned_pending_keeps_qr_active(self):
        flow=self.flow({'next_step':'qr_login_polling','step_info':{'status':2}})
        self.assertEqual(flow.poll(Mock(),{'id':'1','name':'Test'})['status'],'waiting')

    def test_expired_qr_does_not_claim_authentication(self):
        flow=self.flow({'next_step':'qr_login_polling','step_info':{'status':5}})
        self.assertEqual(flow.poll(Mock(),{'id':'1','name':'Test'})['status'],'expired')

    def test_unknown_additional_steps_are_explicit(self):
        flow=self.flow({'next_step':'verify_code','step_info':{}})
        self.assertEqual(flow.poll(Mock(),{'id':'1','name':'Test'})['status'],'error')

    def test_redirect_host_is_checked_before_request(self):
        http=Mock()
        for url in ['http://i.thundersoft.com/','https://example.com/']:
            with self.assertRaises(ValueError):follow(http,url)
        http.get.assert_not_called()

if __name__=='__main__':unittest.main()
