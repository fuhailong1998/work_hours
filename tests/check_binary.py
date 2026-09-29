"""Smoke-test a standalone build without source files or a Python command on PATH."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

binary=Path(sys.argv[1] if len(sys.argv)>1 else 'dist/work_hours').resolve()
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    env=dict(os.environ,WORK_HOURS_DATA_DIR=str(root/'personal'),PATH='/nonexistent')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base=f'http://127.0.0.1:{port}'
    for run in range(2):
        process=subprocess.Popen([str(binary),'--port',str(port)],cwd=root,env=env,
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        try:
            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError(process.communicate()[0].decode())
                try:
                    with opener.open(base+'/api/bootstrap',timeout=1) as response:
                        data=json.load(response)
                    break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Standalone server failed to start')
            assert data['profile']['id']=='', 'Personal identity accidentally bundled'
            assert data['report'] is None, 'Personal report accidentally bundled'
            for path in ['/','/static/app.js','/static/styles.css','/favicon.svg']:
                with opener.open(base+path,timeout=3) as response:assert response.status==200 and response.read()
            if run==0:
                # Exercise packaged QR/Pillow and HTTPS dependencies; no scan or login performed.
                req=urllib.request.Request(base+'/api/auth/start',data=b'{}',headers={'Content-Type':'application/json'})
                with opener.open(req,timeout=60) as response:auth=json.load(response)
                assert auth['status']=='waiting' and auth['qr'].startswith('data:image/png;base64,')
                assert (root/'personal/oa-http/auth-flow.json').exists()
            else:
                assert (root/'personal/oa-http/auth-flow.json').exists(), 'Session lost on restart'
        finally:
            process.terminate()
            try:process.communicate(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.communicate()
    print('Standalone binary: assets, clean identity, QR HTTPS, persistent data and restart passed')
