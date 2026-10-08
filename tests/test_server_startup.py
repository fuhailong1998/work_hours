import errno
import socket
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import ExitStack
from unittest.mock import patch

from server import create_local_server


class ServerStartupTests(unittest.TestCase):
    def test_skips_consecutive_occupied_ports_and_serves_actual_address(self):
        # Reserve three adjacent ports, then free only the last one.
        for _ in range(100):
            occupied = ExitStack()
            self.addCleanup(occupied.close)
            first = occupied.enter_context(socket.socket())
            first.bind(('127.0.0.1', 0))
            port = first.getsockname()[1]
            if port > 65533:
                occupied.close()
                continue
            try:
                second = occupied.enter_context(socket.socket())
                second.bind(('127.0.0.1', port + 1))
                with socket.socket() as probe:
                    probe.bind(('127.0.0.1', port + 2))
                first.listen()
                second.listen()
                break
            except OSError:
                occupied.close()
        else:
            self.fail('Could not reserve consecutive local ports')

        httpd = create_local_server(port)
        self.addCleanup(httpd.server_close)
        self.assertEqual(httpd.server_port, port + 2)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(httpd.shutdown)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        address = f'http://127.0.0.1:{httpd.server_port}'
        request = urllib.request.Request(address + '/', headers={'Origin': address})
        with opener.open(request, timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b'<!doctype html>', response.read().lower())
        request.add_header('Origin', f'http://127.0.0.1:{port}')
        with self.assertRaises(urllib.error.HTTPError) as failure:
            opener.open(request, timeout=3)
        self.assertEqual(failure.exception.code, 403)
        failure.exception.close()

    def test_stops_at_maximum_port(self):
        with patch('server.WorkbenchHTTPServer', side_effect=OSError(errno.EADDRINUSE, 'occupied')):
            with self.assertRaisesRegex(OSError, '65535.*不可用'):
                create_local_server(65535)

    def test_other_startup_errors_are_preserved(self):
        error = OSError(errno.EMFILE, 'too many open files')
        with patch('server.WorkbenchHTTPServer', side_effect=error):
            with self.assertRaises(OSError) as failure:
                create_local_server(18767)
        self.assertIs(failure.exception, error)
