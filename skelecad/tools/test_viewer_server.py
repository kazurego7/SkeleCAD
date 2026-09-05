import http.client
import threading
import unittest
from http.server import ThreadingHTTPServer
from viewer_server import ViewerHandler, FILES


class QuietHandler(ViewerHandler):
    def log_message(self, *args):
        pass


class ViewerServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, method='GET'):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request(method, path)
        response = conn.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        conn.close()
        return result

    def test_entry_is_relative_redirect(self):
        status, headers, _ = self.request('/')
        self.assertEqual(status, 302)
        self.assertEqual(headers['Location'], './viewer/')
        self.assertEqual(self.request('/viewer/')[0], 200)

    def test_all_required_assets(self):
        for name in FILES:
            with self.subTest(name=name):
                status, headers, body = self.request('/' + name, 'HEAD')
                self.assertEqual(status, 200)
                self.assertGreater(int(headers['Content-Length']), 0)
                self.assertEqual(body, b'')

    def test_forbidden_paths(self):
        for path in ('/build/', '/config/', '/viewer/tests/', '/AGENTS.md', '/config/toolchain.json',
                     '/build/edge-profile-assembly/Default/Preferences',
                     '/viewer/../config/toolchain.json', '/%2e%2e/README.md',
                     '/viewer/%2e%2e/index.html', '/%252e%252e/README.md', '/viewer%5cindex.html'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_health_and_query(self):
        self.assertIn(b'skelecad-viewer', self.request('/healthz')[2])
        self.assertEqual(self.request('/viewer/app.js?v=1.8.0')[0], 200)
        self.assertEqual(self.request('/viewer/', 'POST')[0], 501)


if __name__ == '__main__':
    unittest.main()
