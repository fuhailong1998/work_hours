"""OA HTTP session. No browser, CDP, DOM, or browser automation required."""
import json
from pathlib import Path
import threading
import requests

from app_paths import DATA_ROOT

SESSION_FILE = DATA_ROOT / 'oa-http' / 'cookies.json'
OA_ORIGIN = 'https://i.thundersoft.com'


class OAAuthRequired(ValueError):
    pass


class OASession:
    def __init__(self, path=SESSION_FILE):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.http = requests.Session()  # Respect the environment's corporate network proxy.
        self.http.headers.update({'User-Agent':'Mozilla/5.0', 'Accept':'application/json, text/plain, */*',
                                  'Referer': OA_ORIGIN + '/wui/index.html'})
        if self.path.exists():
            for c in json.loads(self.path.read_text(encoding='utf-8')):
                self.http.cookies.set(c['name'], c['value'], domain=c['domain'], path=c.get('path', '/'),
                                      secure=c.get('secure', True), expires=c.get('expires'))

    def persist(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            data=[dict(name=c.name,value=c.value,domain=c.domain,path=c.path,secure=c.secure,expires=c.expires)
                  for c in self.http.cookies]
            temporary=self.path.with_suffix('.tmp')
            temporary.touch(mode=0o600, exist_ok=True)
            temporary.chmod(0o600)
            temporary.write_text(json.dumps(data),encoding='utf-8')
            temporary.replace(self.path)

    def request(self, method, path, **kwargs):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('OA 请求必须使用本站路径')
        with self.lock:
            response=self.http.request(method, OA_ORIGIN+path, timeout=45, allow_redirects=False, **kwargs)
            if response.status_code in (301,302,303,307,308,401):
                raise OAAuthRequired('OA 会话已失效，请重新扫码授权')
            response.raise_for_status()
            self.persist()
            return response

    def api(self, path, data=None, params=None):
        response=self.request('GET' if data is None else 'POST', path, data=data, params=params)
        try:return response.json()
        except ValueError:raise OAAuthRequired('OA 未返回有效数据，请重新扫码授权') from None

    def identity(self):
        payload=self.api('/api/hrm/login/getAccountList')
        data=payload.get('data', {})
        if str(payload.get('status'))!='1' or not data.get('userid'):
            raise OAAuthRequired('OA 会话已失效，请重新扫码授权')
        return {'id':str(data['userid']), 'name':data.get('username',''), 'department':data.get('deptname','')}


_session = None
_session_lock = threading.Lock()


def get_session():
    global _session
    with _session_lock:
        if _session is None:
            _session=OASession()
        return _session
