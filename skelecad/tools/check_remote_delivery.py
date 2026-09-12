"""Read-only transfer/hash/cache checks against a running SkeleCAD URL."""
import argparse
import gzip
import hashlib
import http.client
import json
import struct
import numpy as np
from pathlib import Path
from urllib.parse import urljoin, urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', help='Viewer URL, including /skelecad/viewer/')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    def get(path, headers=None):
        url = urlsplit(urljoin(args.url, path))
        cls = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
        conn = cls(url.netloc, timeout=30)
        try:
            conn.request('GET', url.path + ('?' + url.query if url.query else ''), headers=headers or {})
            response = conn.getresponse()
            return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
        finally:
            conn.close()

    status, _, body = get('../api/jobs')
    assert status == 200, status
    jobs = json.loads(body)['jobs']
    job = next((j for j in jobs if j.get('mechanical_revision')), next(j for j in jobs if j.get('manifest')))
    status, _, body = get(job['manifest'])
    assert status == 200, status
    manifest = json.loads(body)
    rows = []
    for part in manifest['parts']:
        path = part['path'] + '?sha256=' + part['sha256']
        status, headers, body = get(path, {'Accept-Encoding': 'gzip'})
        assert status == 200 and headers['content-encoding'] == 'gzip'
        raw = gzip.decompress(body)
        assert hashlib.sha256(raw).hexdigest() == part['sha256']
        assert get(path, {'Accept-Encoding': 'gzip', 'If-None-Match': headers['etag']})[0] == 304
        sizes = {}
        for detail in ('full', 'preview'):
            compact_path = path + '&format=mesh-v1' + ('&detail=preview-v3' if detail == 'preview' else '')
            packed_status, packed_headers, packed_body = get(compact_path, {'Accept-Encoding': 'gzip'})
            assert packed_status == 200
            packed = gzip.decompress(packed_body) if packed_headers.get('content-encoding') == 'gzip' else packed_body
            assert hashlib.sha256(packed).hexdigest() == packed_headers['x-content-sha256']
            assert packed[16:48].hex() == part['sha256']
            if detail == 'preview':
                assert float(packed_headers['x-preview-model-scale']) == job['target_length_mm']
            vertices, faces = struct.unpack_from('<II', packed, 8)
            table = np.frombuffer(packed, dtype=np.uint8, offset=48, count=vertices*12).reshape(12, vertices).T.copy()
            indices = np.frombuffer(packed, dtype=np.uint8, offset=48+vertices*12).reshape(12, faces).T.copy().view('<u4').ravel()
            assert len(packed) == 48 + vertices*12 + faces*12
            assert indices.max() < vertices
            assert np.isfinite(table.copy().view('<f4')).all()
            if detail == 'full':
                original = np.frombuffer(raw, dtype=np.uint8, offset=84).reshape(-1, 50)[:, 12:48]
                assert table[indices].tobytes() == original.tobytes(), 'Coordinates or face order changed'
            assert get(compact_path, {'Accept-Encoding': 'gzip', 'If-None-Match': packed_headers['etag']})[0] == 304
            sizes[detail + '_gzip'] = len(packed_body)
            sizes[detail + '_faces'] = faces
        rows.append({'part': part['name'], 'raw': len(raw), 'gzip': len(body), **sizes, 'url': urljoin(args.url, path)})
    assets = []
    for name in (Path(__file__).resolve().parents[1] / 'viewer').iterdir():
        if name.suffix not in ('.js', '.css', '.html'):
            continue
        status, headers, body = get(name.name, {'Accept-Encoding': 'gzip'})
        assert status == 200
        assets.append({'file': name.name, 'raw': name.stat().st_size, 'gzip': len(body)})
    thumb = get('../api/jobs/' + job['id'] + '/files/source.png?thumbnail=1')
    source = get('../api/jobs/' + job['id'] + '/files/source.png')
    assert thumb[0] == source[0] == 200
    report = {'model': rows, 'assets': assets,
              'model_total': {key: sum(r[key] for r in rows) for key in ('raw', 'gzip', 'full_gzip', 'preview_gzip', 'full_faces', 'preview_faces')},
              'assets_total': {key: sum(r[key] for r in assets) for key in ('raw', 'gzip')},
              'thumbnail_bytes': len(thumb[2]), 'source_bytes': len(source[2])}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('model', 'assets')}, indent=2))


if __name__ == '__main__':
    main()
