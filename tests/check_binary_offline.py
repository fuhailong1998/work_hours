"""Run a standalone build without OA access or Python on PATH, including Windows data paths."""
import argparse
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def stop(process):
    if process.poll() is not None:
        return
    if sys.platform == 'win32':
        # A one-file executable has a bootloader parent and an application child.
        taskkill = Path(os.environ['SystemRoot']) / 'System32/taskkill.exe'
        subprocess.run([str(taskkill), '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def check(binary, check_qr=False):
    with tempfile.TemporaryDirectory(prefix='work-hours-中文路径-') as folder:
        root = Path(folder)
        personal = root / '个人配置'
        (root / 'empty-path').mkdir()
        env = dict(os.environ, WORK_HOURS_DATA_DIR=str(personal), PATH=str(root/'empty-path'))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'

        def get(path):
            with opener.open(base+path, timeout=2) as response:
                return response.read()

        for run in range(3):
            if run == 1:
                # Deliberately invalid credentials and a synthetic cached report: bootstrap
                # reads these locally. This test never calls an OA endpoint.
                write_json(personal/'oa-http/cookies.json', [
                    {'name':'offline-test','value':'not-a-valid-session',
                     'domain':'i.thundersoft.com','path':'/','secure':True,'expires':None}])
                write_json(personal/'workbench/profile.json', {
                    'id':'1','name':'测试员工','employee_code':'TEST','department':'研发',
                    'public_project':'个人公共项目','public_project_confirmed':True})
                write_json(personal/'oa/hours.json', {
                    'start_date':'2025-01-06','end_date':'2025-01-06',
                    'public_project':'个人公共项目',
                    'daily':[{'date':'2025-01-06','hours':{'个人公共项目':'4','合计':'4'}}]})
            with (root/f'run-{run}.log').open('wb') as log:
                process = subprocess.Popen([str(binary),'--port',str(port)], cwd=root, env=env,
                                           stdout=log, stderr=log, stdin=subprocess.DEVNULL)
                try:
                    deadline = time.monotonic()+45
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            raise RuntimeError((root/f'run-{run}.log').read_text(encoding='utf-8', errors='replace'))
                        try:
                            data = json.loads(get('/api/bootstrap'))
                            break
                        except OSError:
                            time.sleep(.1)
                    else:
                        raise RuntimeError('Standalone server did not start')
                    for path in ['/', '/static/app.js', '/static/styles.css', '/favicon.svg']:
                        assert get(path), path
                    if run == 0:
                        assert data['profile']['id'] == '' and data['report'] is None, 'Personal data was bundled'
                        if check_qr:
                            request = urllib.request.Request(base+'/api/auth/start', data=b'{}',
                                headers={'Content-Type':'application/json'})
                            with opener.open(request,timeout=60) as response:
                                auth = json.load(response)
                            assert auth['status'] == 'waiting'
                            assert base64.b64decode(auth['qr'].split(',',1)[1]).startswith(b'\x89PNG\r\n\x1a\n')
                            assert (personal/'oa-http/auth-flow.json').exists()
                    else:
                        assert data['profile']['name'] == '测试员工'
                        day = data['report']['daily'][0]
                        assert day['calendar']['known'], 'Packaged calendar is missing'
                        assert day['calendar']['missing_hours'] == '4', 'Timezone or working-day calculation failed'
                        if run == 1:
                            request = urllib.request.Request(base+'/api/profile',
                                data=json.dumps({'public_project':'修改后的公共项目'}, ensure_ascii=False).encode('utf-8'),
                                headers={'Content-Type':'application/json'})
                            with opener.open(request,timeout=5) as response:
                                assert json.load(response)['profile']['public_project'] == '修改后的公共项目'
                        else:
                            assert data['profile']['public_project'] == '修改后的公共项目', 'Local settings lost on restart'
                finally:
                    stop(process)
        print('Standalone offline checks passed: assets, clean identity, Unicode paths/settings, timezone, calendar and restart')
        if check_qr:
            print('Additional online check passed: HTTPS QR initialization and PNG generation (no scan or OA save)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', nargs='?', default='dist/work_hours.exe' if sys.platform=='win32' else 'dist/work_hours')
    parser.add_argument('--check-qr', action='store_true', help='Also initialize an unscanned QR over HTTPS')
    args = parser.parse_args()
    check(Path(args.binary).resolve(), args.check_qr)
