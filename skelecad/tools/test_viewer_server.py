import http.client
import gzip
import hashlib
import tempfile
import threading
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
from viewer_server import ViewerHandler, FILES


class QuietHandler(ViewerHandler):
    def log_message(self, *args):
        pass


class ViewerServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        cls.server.workflow_token = 'test-token'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, method='GET', headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request(method, path, headers=headers or {})
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

    def test_mount_with_and_without_slash(self):
        self.assertEqual(self.request('/skelecad')[1]['Location'], '/skelecad/viewer/')
        self.assertEqual(self.request('/skelecad/')[1]['Location'], './viewer/')
        self.assertEqual(self.request('/skelecad/viewer/')[0], 200)
        self.assertEqual(self.request('/skelecad/viewer/app.js')[0], 200)
        self.assertEqual(self.request('/skelecad/config/toolchain.json')[0], 404)

    def test_lossless_gzip_conditional_requests_and_head(self):
        path = '/skelecad/viewer/app.js'
        _, plain, raw = self.request(path)
        status, compressed, body = self.request(path, headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(status, 200)
        self.assertEqual(gzip.decompress(body), raw)
        self.assertLess(len(body), len(raw) // 2)
        self.assertEqual(compressed['Content-Encoding'], 'gzip')
        self.assertNotEqual(plain['ETag'], compressed['ETag'])
        headers = {'Accept-Encoding': 'gzip', 'If-None-Match': compressed['ETag']}
        self.assertEqual(self.request(path, headers=headers)[::2], (304, b''))
        head = self.request(path, 'HEAD', {'Accept-Encoding': 'gzip'})
        self.assertEqual(head[1]['Content-Length'], str(len(body)))
        self.assertEqual(head[2], b'')
        self.assertNotIn('Content-Encoding', self.request(path, headers={'Accept-Encoding': 'gzip;q=0, *;q=1'})[1])

    def test_model_cache_updates_and_remote_host_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / 'appearance.stl'
            raw = b'lossless STL transport fixture' * 100
            model.write_bytes(raw)
            self.server.workflows = SimpleNamespace(artifact=lambda *_: model, list=lambda: [])
            self.server.tailscale_host = 'test.ts.net'
            try:
                path = '/skelecad/api/jobs/' + 'a' * 32 + '/files/appearance.stl'
                sha = hashlib.sha256(raw).hexdigest()
                status, headers, body = self.request(path + '?sha256=' + sha, headers={'Accept-Encoding': 'gzip', 'Host': 'test.ts.net', 'Origin': 'https://test.ts.net'})
                self.assertEqual(status, 200)
                self.assertEqual(gzip.decompress(body), raw)
                self.assertIn('immutable', headers['Cache-Control'])
                model.write_bytes(b'updated mesh')
                self.assertEqual(self.request(path + '?sha256=' + sha)[0], 409)
                status, updated, body = self.request(path, headers={'If-None-Match': headers['ETag']})
                self.assertEqual(status, 200)
                self.assertEqual(body, b'updated mesh')
                self.assertNotEqual(updated['ETag'], headers['ETag'])
                for bad in ({'Host': 'other.ts.net'}, {'Host': 'test.ts.net', 'Origin': 'https://evil.example'}, {'Host': 'test.ts.net', 'Sec-Fetch-Site': 'cross-site'}):
                    self.assertEqual(self.request(path, headers=bad)[0], 403)
                self.assertEqual(self.request('/skelecad/api/jobs', 'POST', {'Host': 'test.ts.net'})[0], 403)
            finally:
                self.server.workflows = None
                self.server.tailscale_host = None

    def test_remote_print_api_is_token_protected_and_separate_from_local(self):
        from unittest.mock import Mock
        manager = Mock()
        manager.prepare.return_value = {'ticket': 'c'*32, 'stage':'preparing'}
        self.server.workflows = object()
        self.server.remote_print = manager
        self.server.tailscale_host = 'pc.example.ts.net'
        path = '/api/jobs/' + 'a'*32 + '/remote-print/prepare'
        def post(host, token):
            conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
            conn.request('POST',path,body='{}',headers={'Host':host,'Content-Type':'application/json','X-SkeleCAD-Token':token})
            response=conn.getresponse();response.read();conn.close();return response.status
        try:
            self.assertEqual(post('pc.example.ts.net','wrong'),403)
            self.assertEqual(post('127.0.0.1:'+str(self.server.server_port),'test-token'),403)
            manager.prepare.assert_not_called()
            self.assertEqual(post('pc.example.ts.net','test-token'),202)
            manager.prepare.assert_called_once_with('a'*32,{})
        finally:
            self.server.workflows=None
            self.server.tailscale_host=None

    def test_thumbnail_is_small_and_source_is_preserved(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.png'
            Image.new('RGB', (1920, 1080), 'red').save(source)
            original = source.read_bytes()
            self.server.workflows = SimpleNamespace(artifact=lambda *_: source)
            try:
                status, headers, body = self.request('/api/jobs/' + 'a' * 32 + '/files/source.png?thumbnail=1')
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Type'], 'image/jpeg')
                self.assertLess(len(body), len(original))
                self.assertEqual(source.read_bytes(), original)
            finally:
                self.server.workflows = None

    def test_display_image_is_progressive_cached_and_does_not_wait_for_meshes(self):
        import io
        import viewer_delivery
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.png'
            Image.new('RGBA', (1600, 1200), (255, 0, 0, 0)).save(source)
            original = source.read_bytes()
            self.server.workflows = SimpleNamespace(artifact=lambda *_: source)
            url = '/api/jobs/' + 'a' * 32 + '/files/source.png?display=1'
            completed = threading.Event()
            results = []
            def load_image():
                try:
                    results.append(self.request(url))
                finally:
                    completed.set()
            try:
                with viewer_delivery._mesh_lock:
                    worker = threading.Thread(target=load_image)
                    worker.start()
                    responsive = completed.wait(3)
                worker.join(10)
                self.assertTrue(responsive, 'image delivery must not wait for mesh conversion')
                status, headers, body = results[0]
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Type'], 'image/jpeg')
                image = Image.open(io.BytesIO(body))
                self.assertEqual(image.size, (960, 720))
                self.assertTrue(image.info.get('progressive'))
                self.assertLess(len(body), len(original))
                self.assertTrue(all(abs(a-b) <= 3 for a, b in zip(image.getpixel((0, 0)), (245, 243, 239))))
                status, _, cached = self.request(url, headers={'If-None-Match': headers['ETag']})
                self.assertEqual(status, 304)
                self.assertEqual(cached, b'')
                self.assertEqual(source.read_bytes(), original)
            finally:
                self.server.workflows = None

    def test_compact_mesh_preserves_coordinates_faces_and_source_identity(self):
        import numpy as np
        triangles = np.array([[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]],
                              [[-0., 0., 0.], [0., 1., 0.], [0., 0., 2.]]], dtype='<f4')
        raw = bytes(80) + struct.pack('<I', 2) + b''.join(
            bytes(12) + face.tobytes() + bytes(2) for face in triangles)
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / 'part.stl'
            model.write_bytes(raw)
            self.server.workflows = SimpleNamespace(artifact=lambda *_: model)
            try:
                digest = hashlib.sha256(raw).hexdigest()
                route = '/api/jobs/' + 'a' * 32 + '/files/part.stl?format=mesh-v1'
                status, headers, body = self.request(route + '&sha256=' + digest, headers={'Accept-Encoding': 'gzip'})
                self.assertEqual(status, 200)
                packed = gzip.decompress(body) if headers.get('Content-Encoding') == 'gzip' else body
                self.assertEqual(packed[:8], b'SKMESH1\0')
                self.assertEqual(packed[16:48].hex(), digest)
                self.assertEqual(hashlib.sha256(packed).hexdigest(), headers['X-Content-SHA256'])
                vertices, faces = struct.unpack_from('<II', packed, 8)
                table = np.frombuffer(packed, dtype=np.uint8, offset=48, count=vertices*12).reshape(12, vertices).T.copy()
                indices = np.frombuffer(packed, dtype=np.uint8, offset=48+vertices*12).reshape(12, faces).T.copy().view('<u4').ravel()
                self.assertEqual(table[indices].tobytes(), triangles.tobytes())
                self.assertEqual(model.read_bytes(), raw)
                self.assertNotEqual(headers['ETag'], self.request(route.replace('?format=mesh-v1', ''))[1]['ETag'])
                self.assertEqual(self.request(route + '&sha256=' + digest, headers={'Accept-Encoding': 'gzip', 'If-None-Match': headers['ETag']})[0], 304)
                self.assertEqual(self.request(route + '&sha256=' + '0'*64)[0], 409)
                self.assertEqual(self.request(route, 'HEAD')[2], b'')
                model.write_bytes(b'invalid')
                self.assertEqual(self.request(route)[0], 422)
            finally:
                self.server.workflows = None

    def test_preview_is_small_and_never_changes_the_print_mesh(self):
        import trimesh
        from viewer_delivery import representation
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'sphere.stl'
            source = trimesh.creation.icosphere(subdivisions=5).export(file_type='stl')
            target.write_bytes(source)
            raw, compressed, digest = representation(target, compact=True, preview=True)
            self.assertEqual(raw[:8], b'SKMESH2\0')
            self.assertEqual(raw[16:48].hex(), hashlib.sha256(source).hexdigest())
            self.assertLess(struct.unpack_from('<I', raw, 12)[0], struct.unpack_from('<I', source, 80)[0]//4)
            self.assertLess(len(compressed), len(gzip.compress(source, 6)) // 3)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            self.assertEqual(target.read_bytes(), source)

    def test_preview_increases_detail_when_simplification_distorts_shape(self):
        import fast_simplification
        import trimesh
        from unittest.mock import patch
        from viewer_delivery import compact_mesh
        source = trimesh.creation.icosphere(subdivisions=5).export(file_type='stl')
        simplify = fast_simplification.simplify
        budgets = []
        def distorted_first(*args, **kwargs):
            budgets.append(kwargs['target_count'])
            vertices, faces = simplify(*args, **kwargs)
            return (vertices + 10 if len(budgets) == 1 else vertices), faces
        with patch.object(fast_simplification, 'simplify', side_effect=distorted_first):
            packed = compact_mesh(source, preview=True)
        self.assertEqual(budgets[:2], [128, 256])
        self.assertGreater(struct.unpack_from('<I', packed, 12)[0], 128)

    def test_shared_scale_across_stages_and_small_parts(self):
        import trimesh
        with tempfile.TemporaryDirectory() as folder:
            big = trimesh.creation.icosphere(subdivisions=4, radius=10)
            small = trimesh.creation.icosphere(subdivisions=4, radius=1)
            small.apply_translation([25, 0, 0])
            shapes = {'appearance.stl': trimesh.util.concatenate([big, small]),
                      'preview_big.stl': big, 'preview_small.stl': small,
                      'r_revision_big.stl': big}
            paths = {}
            for name, mesh in shapes.items():
                paths[name] = Path(folder)/name
                paths[name].write_bytes(mesh.export(file_type='stl'))
            self.server.workflows = SimpleNamespace(artifact=lambda _, name: paths[name], read=lambda _: {'target_length_mm': 120})
            try:
                bodies = {}
                for name in paths:
                    route = '/api/jobs/'+'a'*32+'/files/'+name+'?format=mesh-v1&detail=preview-v3'
                    status, headers, body = self.request(route)
                    self.assertEqual(status, 200)
                    self.assertEqual(headers['X-Preview-Model-Scale'], '120')
                    bodies[name] = body
                self.assertEqual(bodies['preview_big.stl'], bodies['r_revision_big.stl'], 'same surface retains same detail across stages')
                self.assertLess(struct.unpack_from('<I', bodies['preview_small.stl'], 12)[0],
                                struct.unpack_from('<I', bodies['preview_big.stl'], 12)[0], 'tiny part has no fixed per-part face minimum')
                from viewer_delivery import representation
                strict = representation(paths['preview_big.stl'], compact=True, preview=True, model_scale=12)
                broad = representation(paths['preview_big.stl'], compact=True, preview=True, model_scale=120)
                self.assertGreater(struct.unpack_from('<I', strict[0], 12)[0], struct.unpack_from('<I', broad[0], 12)[0])
                self.assertNotEqual(strict[2], broad[2], 'cache includes the shared model scale')
            finally:
                self.server.workflows = None


if __name__ == '__main__':
    unittest.main()
