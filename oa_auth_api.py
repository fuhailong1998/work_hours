"""Feishu QR authorization over HTTP. QR generation and polling require no browser."""
import base64
import io
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs, urljoin
import qrcode
import requests
from oa_http import OAAuthRequired

LOGIN_URL='https://larkapproval.thundersoft.com/sso/login?'+urlencode({
    'redirectUrl':'https://i.thundersoft.com/wui/index.html?#/main?menuIds=-76,-122&menuPathIds=-76,-121,-122'})
ALLOWED={'larkapproval.thundersoft.com','i.thundersoft.com','accounts.feishu.cn','open.feishu.cn','passport.feishu.cn','login.feishu.cn'}
HEADERS={'User-Agent':'Mozilla/5.0','x-api-version':'1.0.31','x-app-id':'12','x-terminal-type':'2',
         'x-device-info':'device_id=0;device_name=Chrome;device_os=Linux;device_model=Chrome;lark_version=;channel=Release;package_name=feishu;tt_app_id=1658;is_dpop_support=true;is_iframe=false',
         'x-lgw-os-type':'2','x-lgw-terminal-type':'2','x-locale':'zh-CN','x-lsc-terminal':'web',
         'x-lsc-version':'1','x-passport-ka-package':'0'}
_lock=threading.Lock()
_flow=None
from app_paths import DATA_ROOT
FLOW_FILE=DATA_ROOT / "oa-http/auth-flow.json"
APP_ID='cli_a11b74bf89b9d00b'
CALLBACK='https://larkapproval.thundersoft.com/sso/feishuCallback'


def consent_config(url, html):
    parts=urlsplit(url)
    query=parse_qs(parts.query)
    if (parts.scheme!='https' or parts.hostname!='accounts.feishu.cn'
            or parts.path!='/open-apis/authen/v1/index'
            or query.get('app_id')!=[APP_ID] or query.get('redirect_uri')!=[CALLBACK]):
        raise ValueError('授权页面不是预期的公司 OA 应用')
    match=re.search(r'window\.serverInjectRes\s*=\s*',html)
    if not match:raise ValueError('飞书授权页面缺少应用信息')
    config,_=json.JSONDecoder().raw_decode(html[match.end():])
    if config.get('version')!='v1' or config.get('data',{}).get('app_info',{}).get('app_id')!=APP_ID:
        raise ValueError('飞书授权应用或协议不匹配')
    return config


def follow(session,url):
    for _ in range(12):
        parts=urlsplit(url)
        if parts.scheme!='https' or parts.hostname not in ALLOWED:
            raise ValueError('登录跳转目标不在公司 OA 授权链中')
        response=session.get(url,allow_redirects=False,timeout=25)
        if response.is_redirect:
            url=urljoin(url,response.headers['Location']);continue
        response.raise_for_status()
        return response
    raise ValueError('OA 登录跳转次数过多，请重新授权')


class QRFlow:
    def __init__(self):
        self.http=requests.Session()
        self.http.headers['User-Agent']=HEADERS['User-Agent']
        response=follow(self.http,LOGIN_URL)
        self.redirect=parse_qs(urlsplit(response.url).query).get('redirect_uri',[''])[0]
        if not self.redirect:raise ValueError('登录接口未返回授权地址，请重试')
        self.headers=dict(HEADERS,Referer=response.url,Origin='https://accounts.feishu.cn')
        self.token=''
        self.qr=''
        self.done=False
        self.step=self.api('qrlogin/init',{'biz_type':None,'redirect_uri':self.redirect})
        token=self.step.get('step_info',{}).get('token')
        if not token:raise ValueError('登录接口未返回二维码，请重试')
        data=json.dumps({'qrlogin':{'token':token}},separators=(',',':'))
        out=io.BytesIO();qrcode.make(data).save(out,format='PNG')
        self.qr='data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
        self.persist()

    def persist(self):
        FLOW_FILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        data={k:getattr(self,k,None) for k in ['redirect','headers','qr','done','step','last_url','last_html','callback_url']}
        data['cookies']=[dict(name=c.name,value=c.value,domain=c.domain,path=c.path,secure=c.secure,expires=c.expires) for c in self.http.cookies]
        temp=FLOW_FILE.with_suffix('.tmp');temp.touch(mode=0o600,exist_ok=True);temp.chmod(0o600)
        temp.write_text(json.dumps(data));temp.replace(FLOW_FILE)

    @classmethod
    def restore(cls):
        data=json.loads(FLOW_FILE.read_text());flow=cls.__new__(cls)
        flow.http=requests.Session();flow.http.headers['User-Agent']=HEADERS['User-Agent']
        for c in data.pop('cookies'):flow.http.cookies.set(**c)
        for k,v in data.items():setattr(flow,k,v)
        return flow

    def api(self,action,body):
        response=self.http.post('https://accounts.feishu.cn/accounts/'+action,json=body,
                                headers=self.headers,timeout=20,allow_redirects=False)
        response.raise_for_status()
        data=response.json()
        if response.headers.get('x-flow-key'):self.headers['X-Flow-Key']=response.headers['x-flow-key']
        if data.get('code')!=0:raise ValueError('飞书授权未完成，请刷新二维码后重试')
        return data['data']

    def complete_consent(self,response):
        config=consent_config(response.url,response.text)
        user=config['data'].get('current_user') or {}
        # Match the native authorization page's v1 confirmation request.
        csrf=next((c.value for c in self.http.cookies if c.name=='open_csrf_token'
                   and 'accounts.feishu.cn'.endswith(c.domain.lstrip('.'))), '')
        if not csrf or not user.get('user_id') or not config.get('X-Auth-Flow-Key'):
            raise ValueError('飞书授权会话缺少确认信息，请重新授权')
        result=self.http.post('https://accounts.feishu.cn/open-apis/authen/v1/confirm',
            json={'app_id':APP_ID,'user_id':user['user_id'],
                  'scope':' '.join(user.get('all_scope_key_list',[]))},
            headers={'Referer':response.url,'Origin':'https://accounts.feishu.cn',
                     'open-csrf-token':csrf,'X-Auth-Flow-Key':config['X-Auth-Flow-Key']},
            timeout=25,allow_redirects=False)
        self.persist()
        result.raise_for_status()
        payload=result.json()
        if payload.get('code')!=0:
            raise ValueError('飞书应用授权确认失败（错误码：'+str(payload.get('code'))+'）')
        target=payload.get('data',{}).get('redirect_uri','')
        parts=urlsplit(target)
        if parts.scheme!='https' or parts.netloc!='larkapproval.thundersoft.com' or parts.path!='/sso/feishuCallback':
            raise ValueError('飞书未返回预期的公司 OA 回调地址')
        self.callback_url=target
        self.persist()
        return follow(self.http,target)

    def poll(self,client,expected):
        if self.done:
            identity=client.identity()
            if expected and identity['id']!=expected['id']:return {'status':'wrong_account','message':'OA 接口账号与工作台不一致'}
            return {'status':'authenticated','employee':identity,'message':'OA 接口会话有效'}
        if self.step.get('next_step')=='qr_login_polling':
            self.step=self.api('qrlogin/polling',{})
            self.persist()
        step=self.step.get('next_step');info=self.step.get('step_info',{})
        if step=='qr_login_polling':
            status=info.get('status',0)
            if status not in (0,1,2):return {'status':'expired','message':'二维码已失效，请刷新后重新扫码'}
            return {'status':'waiting','message':'请用飞书扫码并在手机上确认登录','qr':self.qr}
        if step not in ('enter_app','web_url'):
            return {'status':'error','message':'飞书返回了额外账号验证步骤，当前接口暂不支持；请使用已授权的公司账号重新扫码'}
        last_url=getattr(self,'last_url',None)
        landed=last_url and urlsplit(last_url).hostname=='i.thundersoft.com'
        url=(last_url if landed else None) or getattr(self,'callback_url',None) or info.get('url') or info.get('redirect_url') or self.redirect
        response=follow(self.http,url)
        self.last_url=response.url;self.last_html=response.text;self.persist()
        if urlsplit(response.url).hostname=='accounts.feishu.cn' and urlsplit(response.url).path=='/open-apis/authen/v1/index':
            response=self.complete_consent(response)
            self.last_url=response.url;self.last_html=response.text;self.persist()
        if (urlsplit(response.url).hostname=='larkapproval.thundersoft.com'
                and 'Unknown RedirectUrl' in response.text):
            # The company SSO state expires independently of the scanned Feishu session.
            # Renew it once, keeping the authenticated cookies and avoiding another scan.
            self.callback_url=None
            response=follow(self.http,LOGIN_URL)
            self.last_url=response.url;self.last_html=response.text;self.persist()
            if urlsplit(response.url).hostname=='accounts.feishu.cn' and urlsplit(response.url).path=='/open-apis/authen/v1/index':
                response=self.complete_consent(response)
                self.last_url=response.url;self.last_html=response.text;self.persist()
        if urlsplit(response.url).hostname!='i.thundersoft.com':
            # Never claim authentication until the OA account endpoint confirms it.
            return {'status':'error','message':'扫码已确认，但 OA 授权回调未完成；请重新授权后重试'}
        with client.lock:
            old=client.http.cookies.copy()
            client.http.cookies.update(self.http.cookies)
            try:identity=client.identity()
            except Exception:
                client.http.cookies=old;client.persist();raise
            if expected and identity['id']!=expected['id']:
                client.http.cookies=old;client.persist()
                return {'status':'wrong_account','message':f"请使用{expected['name']}的飞书账号授权"}
            client.persist()
        self.done=True
        self.persist()
        return {'status':'authenticated','message':'工作台已通过接口连接 OA','employee':identity}


def login_status(client,expected,start=False):
    global _flow
    with _lock:
        if _flow is None and FLOW_FILE.exists():_flow=QRFlow.restore()
        if start:
            _flow=QRFlow()
            return {'status':'waiting','message':'请用飞书扫码并在手机上确认登录','qr':_flow.qr}
        if _flow is None:
            try:
                identity=client.identity()
                if not expected or identity['id']==expected['id']:return {'status':'authenticated','employee':identity,'message':'OA 接口会话有效'}
            except OAAuthRequired:pass
            return {'status':'missing','message':'请点击开始登录，获取授权二维码'}
        return _flow.poll(client,expected)


def clear_login(client):
    """Discard local credentials while serializing against QR polling and OA calls."""
    global _flow
    with _lock, client.lock:
        client.http.cookies.clear()
        _flow=None
        for path in (FLOW_FILE, FLOW_FILE.with_suffix('.tmp'), client.path,
                     client.path.with_suffix('.tmp')):
            path.unlink(missing_ok=True)
        return {'status':'missing','message':'登录态已清除，请重新扫码登录 OA'}
