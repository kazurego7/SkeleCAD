"""Compact and preview HTTP representations; bounded and separate from CAD outputs."""
from collections import OrderedDict
import gzip
import hashlib
import io
import threading

_cache = OrderedDict()
_lock = threading.Lock()
_mesh_lock = threading.Lock()
_limit = 64 * 1024 * 1024
_size = 0


def accepts_gzip(header):
    values = {}
    for entry in header.lower().split(','):
        name, *params = entry.strip().split(';')
        quality = 1.0
        for param in params:
            if param.strip().startswith('q='):
                try:
                    quality = float(param.strip()[2:])
                except ValueError:
                    quality = 0.0
        values[name] = quality
    return values.get('gzip', values.get('*', 0)) > 0


def compact_mesh(raw, preview=False, model_scale=None):
    """Viewer-only indexed transport: preserve every float32 vertex and face.

    Face normals are reconstructed by the viewer. Byte planes improve gzip;
    the source digest binds this representation to the requested STL revision.
    No generated CAD/STL file is changed.
    """
    import numpy as np
    import struct
    if len(raw) < 84:
        raise ValueError('Invalid binary STL')
    count = struct.unpack_from('<I', raw, 80)[0]
    if not count or len(raw) != 84 + count * 50:
        raise ValueError('Invalid binary STL')
    records = np.frombuffer(raw, dtype=np.uint8, offset=84).reshape(count, 50)
    vertices = records[:, 12:48].copy().reshape(-1, 12)
    if not np.isfinite(vertices.copy().view('<f4')).all():
        raise ValueError('Invalid mesh coordinates')
    table, indices = np.unique(vertices.view('V12').ravel(), return_inverse=True)
    if preview and count > 128:
        import fast_simplification
        import trimesh
        points = table.view('<f4').reshape(-1, 3).astype(np.float64)
        original = trimesh.Trimesh(points, indices.reshape(-1, 3), process=True)
        # All stages and parts share the job's original target length. Neither
        # splitting a part nor adding joint details changes the error budget.
        sample, _ = trimesh.sample.sample_surface(original, 1024, seed=42)
        extrema = np.concatenate((np.argmin(original.vertices, axis=0), np.argmax(original.vertices, axis=0)))
        sample = np.vstack((sample, original.vertices[extrema]))
        scale = float(model_scale) if model_scale is not None else float(original.extents.max())
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError('Invalid model scale')
        tolerance = max(scale * .0015, 1e-8)
        points, faces = original.vertices, original.faces
        budget = 128
        while budget < len(original.faces) and budget <= 65536:
            candidate_points, candidate_faces = fast_simplification.simplify(original.vertices, original.faces, target_count=budget)
            candidate = trimesh.Trimesh(candidate_points, candidate_faces, process=False)
            if not len(candidate_faces) or not np.isfinite(candidate_points).all():
                budget *= 2
                continue
            _, forward, _ = trimesh.proximity.closest_point(candidate, sample)
            reverse_sample, _ = trimesh.sample.sample_surface(candidate, 512, seed=42)
            _, reverse, _ = trimesh.proximity.closest_point(original, reverse_sample)
            errors = np.concatenate((forward, reverse))
            if np.percentile(errors, 99) <= tolerance and errors.max() <= tolerance*2:
                points, faces = candidate_points, candidate_faces
                break
            budget = max(budget*2, len(candidate_faces)*2)
        if not len(points) or not len(faces) or not np.isfinite(points).all():
            raise ValueError('Invalid simplified mesh')
        table = np.asarray(points, dtype='<f4').view(np.uint8).reshape(-1, 12)
        indices = np.asarray(faces, dtype='<u4').ravel()
        count = len(faces)
    return ((b'SKMESH2\0' if preview else b'SKMESH1\0') + struct.pack('<II', len(table), count)
            + hashlib.sha256(raw).digest()
            + table.view(np.uint8).reshape(-1, 12).T.tobytes()
            + indices.astype('<u4').view(np.uint8).reshape(-1, 12).T.tobytes())


def representation(target, thumbnail=False, compact=False, preview=False, model_scale=None, display_image=False):
    """Cache by file identity; never modify or simplify source meshes."""
    global _size
    stat = target.stat()
    key = (str(target), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, thumbnail, compact, preview, model_scale if preview else None, display_image)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    raw = target.read_bytes()
    if compact:
        # The simplifier has shared native state. Only meshes need to wait for
        # it; never block image or application delivery on geometry work.
        with _mesh_lock:
            with _lock:
                if key in _cache:
                    _cache.move_to_end(key)
                    return _cache[key]
            raw = compact_mesh(raw, preview, model_scale)
    if thumbnail or display_image:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((960, 960) if display_image else (320, 240))
            image = image.convert('RGBA')
            background = Image.new('RGB', image.size, '#f5f3ef')
            background.paste(image, mask=image.getchannel('A'))
            output = io.BytesIO()
            background.save(output, format='JPEG', quality=78 if display_image else 75, optimize=True, progressive=display_image)
            raw = output.getvalue()
    compressed = gzip.compress(raw, compresslevel=6, mtime=0) if not (thumbnail or display_image) else raw
    digest = hashlib.sha256(raw).hexdigest()
    result = (raw, compressed, digest)
    size = len(raw) + len(compressed)
    with _lock:
        # Concurrent cache misses may finish together; account for a key once.
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        if size <= _limit:
            while _cache and _size + size > _limit:
                _, previous = _cache.popitem(last=False)
                _size -= len(previous[0]) + len(previous[1])
            _cache[key] = result
            _size += size
        return result
