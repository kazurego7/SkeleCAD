"""Allowlisted viewer assets and same-origin, loopback-only image workflow API."""
import argparse
import gzip
import json
import mimetypes
import re
import secrets
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from viewer_delivery import accepts_gzip, representation

PROJECT = Path(__file__).resolve().parents[1]
FILES = {'viewer/index.html', 'viewer/app.js', 'viewer/style.css', 'config/parameters.json',
         'viewer/remote-print-ui.js',
         'viewer/workflow-ui.js', 'viewer/partition-ui.js', 'viewer/motion-core.js', 'viewer/motion-ui.js',
         'viewer/model-gallery.js', 'viewer/pose-snapshots.js', 'viewer/collision-worker.js',
         'viewer/mesh-worker.js', 'viewer/mesh-cache.js', 'viewer/manifest.json', 'viewer/mobile.css', 'viewer/mobile-ui.js',
         'viewer/icons/favicon-32x32.png', 'viewer/icons/favicon-48x48.png',
         'viewer/icons/apple-touch-icon.png', 'viewer/icons/pwa-192x192.png',
         'viewer/icons/pwa-512x512.png', 'viewer/icons/pwa-maskable-192x192.png',
         'viewer/icons/pwa-maskable-512x512.png'}


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = 'SkeleCADViewer/1'
    sys_version = ''

    def do_GET(self):
        self.respond(True)

    def do_HEAD(self):
        self.respond(False)

    def api_allowed(self, mutate=False):
        host = self.headers.get('Host', '')
        expected = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        tailscale_host = getattr(self.server, 'tailscale_host', None)
        if tailscale_host:
            expected.add(tailscale_host)
        if host not in expected or self.client_address[0] not in ('127.0.0.1', '::1'):
            return False
        origin = self.headers.get('Origin')
        if origin and origin != ('https://' if host == tailscale_host else 'http://') + host:
            return False
        if self.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site'):
            return False
        return not mutate or secrets.compare_digest(self.headers.get('X-SkeleCAD-Token', ''), self.server.workflow_token)

    def json_response(self, value, status=200, send_body=True):
        body = json.dumps(value, ensure_ascii=False).encode('utf-8')
        encoded = len(body) > 1024 and accepts_gzip(self.headers.get('Accept-Encoding', ''))
        if encoded:
            body = gzip.compress(body, compresslevel=6, mtime=0)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Vary', 'Accept-Encoding')
        if encoded:
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def do_POST(self):
        path=self.route_path()
        machine=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/machine',path)
        partition=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/partition',path)
        repartition=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/repartition',path)
        symmetry=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/symmetry',path)
        restore_symmetry=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/restore-symmetry',path)
        printing=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/print',path)
        open_print=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/open-print',path)
        remote_print=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/remote-print/(prepare|start|cancel)',path)
        pause=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/pause',path)
        resume=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/resume',path)
        cancel=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/cancel',path)
        trash=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/trash',path)
        restore_trash=re.fullmatch(r'/api/trash/([0-9a-f]{32})/restore',path)
        empty_trash=path=='/api/trash/empty'
        if path != '/api/jobs' and not machine and not partition and not repartition and not symmetry and not restore_symmetry and not printing and not open_print and not remote_print and not pause and not resume and not cancel and not trash and not restore_trash and not empty_trash:
            self.send_error(501)
            return
        if not getattr(self.server, 'workflows', None):
            self.json_response({'error': '画像の生成機能は起動していません。'}, 503)
            return
        if not self.api_allowed(mutate=True):
            self.json_response({'error': 'この操作は同じローカル画面から実行してください。'}, 403)
            return
        try:
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                raise ValueError('画像データの長さが不明です。')
            length = int(self.headers['Content-Length'])
            if machine or partition or repartition or symmetry or restore_symmetry or printing or open_print or remote_print or pause or resume or cancel or trash or restore_trash or empty_trash:
                if not 0<length<=65536 or self.headers.get('Content-Type')!='application/json':
                    raise ValueError('加工リクエストが不正です。')
                self.connection.settimeout(30)
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('加工リクエストが不正です。')
                if remote_print:
                    if self.headers.get('Host') != getattr(self.server, 'tailscale_host', None):
                        self.json_response({'error': '直接印刷はリモート画面から操作してください。'}, 403)
                        return
                    manager = self.server.remote_print
                    try:
                        result = getattr(manager, remote_print[2])(remote_print[1], data)
                    except (KeyError, OSError):
                        raise ValueError('印刷設定またはデータが見つかりません。')
                    self.json_response(result, 202)
                    return
                try:
                    if trash:job=self.server.workflows.trash_job(trash[1])
                    elif restore_trash:job=self.server.workflows.restore_job(restore_trash[1])
                    elif empty_trash:job=self.server.workflows.empty_trash()
                    elif pause:job=self.server.workflows.pause_generation(pause[1])
                    elif resume:job=self.server.workflows.resume_generation(resume[1])
                    elif cancel:job=self.server.workflows.cancel_generation(cancel[1])
                    elif partition:job=self.server.workflows.request_partition(partition[1],data.get('manifest_sha256'),data.get('markers'))
                    elif machine:job=self.server.workflows.request_machining(machine[1],data.get('manifest_sha256'),data.get('joints'))
                    elif repartition:job=self.server.workflows.return_to_partition(repartition[1])
                    elif symmetry:job=self.server.workflows.request_symmetry(symmetry[1],data.get('manifest_sha256'),data.get('source_side'))
                    elif restore_symmetry:job=self.server.workflows.restore_symmetry(restore_symmetry[1])
                    elif printing:job=self.server.workflows.request_print(printing[1],data)
                    else:
                        self.json_response(self.server.workflows.open_print_in_bambu(open_print[1],data))
                        return
                except KeyError:raise ValueError('モデルが見つかりません。')
                self.json_response(job,202)
                return
            if not 0 < length <= 20971520:
                self.close_connection = True
                self.json_response({'error': '画像は20 MB以内にしてください。'}, 413)
                return
            if self.headers.get('Content-Type', '').split(';')[0] not in ('image/png', 'image/jpeg', 'image/webp'):
                self.json_response({'error': 'PNG・JPEG・WebPを選んでください。'}, 415)
                return
            self.connection.settimeout(30)
            data = self.rfile.read(length)
            if len(data) != length:
                raise ValueError('画像の送信が途中で止まりました。')
            name = unquote(self.headers.get('X-Image-Name', '画像'))
            self.json_response(self.server.workflows.create(data, name), 201)
        except (ValueError, UnicodeDecodeError, TimeoutError) as exc:
            self.close_connection = True
            self.json_response({'error': str(exc)}, 400)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        super().end_headers()

    def route_path(self):
        path = unquote(urlsplit(self.path).path)
        return path[len('/skelecad'):] if path.startswith('/skelecad/') else path

    def respond(self, send_body):
        path = self.route_path()
        if path == '/skelecad':
            self.send_response(302)
            self.send_header('Location', '/skelecad/viewer/')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if path.startswith('/api/'):
            if not getattr(self.server, 'workflows', None):
                self.json_response({'error': '画像の生成機能は起動していません。'}, 503, send_body)
                return
            if not self.api_allowed():
                self.json_response({'error': 'ローカルのビュワーから開いてください。'}, 403, send_body)
                return
            store = self.server.workflows
            remote_status = re.fullmatch(r'/api/jobs/([0-9a-f]{32})/remote-print/([0-9a-f]{32})', path)
            if remote_status:
                try:
                    self.json_response(self.server.remote_print.status(*remote_status.groups()), send_body=send_body)
                except (KeyError, OSError, ValueError):
                    self.json_response({'error': '印刷の状態が見つかりません。'}, 404, send_body)
                return
            if path == '/api/session':
                self.json_response({'token': self.server.workflow_token}, send_body=send_body)
                return
            if path == '/api/jobs':
                self.json_response({'jobs': store.list()}, send_body=send_body)
                return
            if path == '/api/trash':
                self.json_response({'jobs':store.list_trash()},send_body=send_body)
                return
            trashed=re.fullmatch(r'/api/trash/([0-9a-f]{32})/files/([a-zA-Z0-9_.-]+)',path)
            if trashed:
                try:self.send_file(store.trash_artifact(trashed[1],trashed[2]),trashed[2],send_body);return
                except (KeyError,OSError):pass
            match = re.fullmatch(r'/api/jobs/([0-9a-f]{32})(?:/files/([a-zA-Z0-9_.-]+))?', path)
            if match:
                try:
                    job_id, name = match.groups()
                    if name:
                        query = parse_qs(urlsplit(self.path).query)
                        shared_preview = name.endswith('.stl') and query.get('detail') == ['preview-v3']
                        # target_length_mm is fixed when the image job is created;
                        # appearance, partition and mechanical revisions use it alike.
                        scale = store.read(job_id)['target_length_mm'] if shared_preview else None
                        self.send_file(store.artifact(job_id, name), name, send_body, model_scale=scale)
                    else:
                        self.json_response(store.public(job_id), send_body=send_body)
                    return
                except (KeyError, OSError):
                    pass
            self.json_response({'error': 'データが見つかりません。'}, 404, send_body)
            return
        # Relative redirects preserve the Tailscale /skelecad/ mount point.
        if path in ('', '/', '/viewer'):
            self.send_response(302)
            self.send_header('Location', './viewer/' if path != '/viewer' else 'viewer/')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if path == '/healthz':
            body = json.dumps({'app': 'skelecad-viewer', 'version': 3,
                               'tailscale_host': getattr(self.server, 'tailscale_host', None)}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)
            return
        name = 'viewer/index.html' if path == '/viewer/' else path.removeprefix('/')
        if name not in FILES:
            self.send_error(404)
            return
        target = PROJECT / name
        # Refuse symlinks/junctions, directory listing and arbitrary project files.
        if target.resolve() != target or not target.is_file():
            self.send_error(404)
            return
        self.send_file(target, name, send_body)

    def send_file(self, target, name, send_body, model_scale=None):
        try:
            query = parse_qs(urlsplit(self.path).query)
            thumbnail = target.name == 'source.png' and query.get('thumbnail') == ['1']
            display_image = target.name == 'source.png' and query.get('display') == ['1']
            compact = target.suffix == '.stl' and query.get('format') == ['mesh-v1']
            preview = compact and query.get('detail') in (['preview-v1'], ['preview-v2'], ['preview-v3'])
            compressible = target.suffix in ('.stl', '.js', '.css', '.html', '.json')
            if compressible or thumbnail or display_image:
                try:
                    raw, compressed, digest = representation(target, thumbnail, compact, preview, model_scale, display_image)
                except ValueError:
                    self.json_response({'error': '表示用の形状データを読み取れません。'}, 422, send_body)
                    return
                expected = query.get('sha256', [None])[0] if target.suffix == '.stl' else None
                source_digest = raw[16:48].hex() if compact else digest
                if expected and expected != source_digest:
                    self.json_response({'error': '生成データの照合に失敗しました。再読み込みしてください。'}, 409, send_body)
                    return
                encoded = compressible and len(compressed) < len(raw) and accepts_gzip(self.headers.get('Accept-Encoding', ''))
                body = compressed if encoded else raw
                etag = '"' + digest + ('-gzip' if encoded else '') + '"'
                matches = self.headers.get('If-None-Match', '').split(',')
                unchanged = any(value.strip().removeprefix('W/') in (etag, '*') for value in matches)
                self.send_response(304 if unchanged else 200)
                self.send_header('ETag', etag)
                if compact:
                    self.send_header('X-Content-SHA256', digest)
                if preview and model_scale is not None:
                    self.send_header('X-Preview-Model-Scale', str(model_scale))
                self.send_header('Vary', 'Accept-Encoding')
                self.send_header('Cache-Control', 'private, max-age=31536000, immutable' if expected else 'private, no-cache')
                if unchanged:
                    # A 304 carries no body. Avoid passing gzip body metadata
                    # through the HTTPS proxy on a cache-validation response.
                    self.end_headers()
                    return
                content_type = 'application/x-skelecad-mesh' if compact else ('image/jpeg' if thumbnail or display_image else ('text/javascript' if target.suffix == '.js' else mimetypes.guess_type(name)[0] or 'application/octet-stream'))
                self.send_header('Content-Type', content_type)
                if encoded:
                    self.send_header('Content-Encoding', 'gzip')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if send_body and not unchanged:
                    self.wfile.write(body)
                return
            with target.open('rb') as stream:
                self.send_response(200)
                content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
                if name.endswith('.js'):
                    content_type = 'text/javascript'
                self.send_header('Content-Type', content_type)
                if target.suffix=='.3mf':self.send_header('Content-Disposition',f'attachment; filename="{target.name}"')
                self.send_header('Content-Length', str(target.stat().st_size))
                self.send_header('Cache-Control', 'private, no-cache')
                self.end_headers()
                if send_body:
                    shutil.copyfileobj(stream, self.wfile)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--tailscale-host', help='Exact HTTPS tailnet hostname allowed through the loopback proxy')
    parser.add_argument('--workflow-root', type=Path, help='Isolated workflow directory for testing or a separate collection')
    args = parser.parse_args()
    # Fail at startup rather than dropping a later print request when somebody
    # launches the server with a Python environment that lacks geometry tools.
    try:
        import numpy  # noqa: F401
        import trimesh  # noqa: F401
        import scipy  # noqa: F401
        import manifold3d  # noqa: F401
        import fast_simplification  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError('Viewer requires the bundled modelling Python; start it with tools/open_3d_viewer.ps1') from exc
    server = ThreadingHTTPServer((args.bind, args.port), ViewerHandler)
    server.tailscale_host = args.tailscale_host
    from workflow_store import WorkflowStore
    server.workflows = WorkflowStore(root=args.workflow_root)
    from remote_print import RemotePrint
    server.remote_print = RemotePrint(server.workflows)
    server.workflow_token = secrets.token_urlsafe(32)
    print(f'SkeleCAD viewer: http://{args.bind}:{args.port}/viewer/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.workflows.close()
        server.server_close()


if __name__ == '__main__':
    main()
