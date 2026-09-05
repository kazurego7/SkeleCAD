"""Repeatable local setup; external GUI applications stay user-installed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

from runtime_paths import PROJECT, tool_config

WORKSPACE = PROJECT.parent
HUNYUAN_COMMIT = '82920d643c0dc2f7bfd7255f45f62d386edfe60c'


def run(command, **kwargs):
    subprocess.run([str(x) for x in command], check=True, **kwargs)


FREECAD_ARCHIVE_URL = 'https://github.com/FreeCAD/FreeCAD/releases/download/1.1.3/FreeCAD_1.1.3-Windows-x86_64-py311.7z'
FREECAD_ARCHIVE_SHA256 = '9c6959dc9c4dba64dd818a62447e3dfedb4221d776fb044b239d462f150bcec4'
EXTRACTOR_URL = 'https://github.com/ip7z/7zip/releases/download/26.03/7zr.exe'
EXTRACTOR_SHA256 = 'ad4c82fadcbdf93c03b4fc440f300509c7d60c5c2f4d183e35d9d70d6957037d'


def file_digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download_verified(url, path, expected):
    if path.is_file() and file_digest(path) == expected:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as temp:
        partial = Path(temp) / 'download'
        received = 0
        with urllib.request.urlopen(url, timeout=30) as response, partial.open('wb') as stream:
            while chunk := response.read(1024*1024):
                stream.write(chunk)
                received += len(chunk)
                if received % (32*1024*1024) == 0:
                    print(f'{path.name}: {received//(1024*1024)} MiB downloaded', flush=True)
        if file_digest(partial) != expected:
            raise RuntimeError(f'Download checksum mismatch: {path.name}')
        partial.replace(path)
    return path


def check_freecad(python, version):
    run([python, '-c', 'import FreeCAD, Part, Mesh, MeshPart; '
         f'assert ".".join(FreeCAD.Version()[:3]) == {version!r}, "FreeCAD version mismatch"; '
         'shape=Part.makeSphere(3); assert shape.isValid() and shape.Volume > 0; '
         'print("FreeCAD ready")'])


def ensure_freecad(config):
    freecad = config['freecad']
    python = WORKSPACE / freecad['python']
    if python.is_file():
        check_freecad(python, freecad['version'])
        return python
    target = WORKSPACE / '.tools' / ('freecad-' + freecad['version'])
    if freecad['version'] != '1.1.3':
        raise RuntimeError('No verified portable download configured for this FreeCAD version')
    if target.exists():
        raise RuntimeError(f'Incomplete FreeCAD runtime: {target}')
    cache = WORKSPACE / '.tools/cache/downloads'
    print('Downloading FreeCAD portable runtime (about 399 MiB)...', flush=True)
    archive = download_verified(FREECAD_ARCHIVE_URL, cache/'FreeCAD-1.1.3.7z', FREECAD_ARCHIVE_SHA256)
    extractor = download_verified(EXTRACTOR_URL, cache/'7zr-26.03.exe', EXTRACTOR_SHA256)
    with tempfile.TemporaryDirectory(prefix='freecad-setup-', dir=target.parent) as temp:
        staging = Path(temp)
        print('Extracting FreeCAD portable runtime...', flush=True)
        run([extractor, 'x', archive, '-o'+str(staging), '-y', '-bso0', '-bsp0'])
        candidates = list(staging.glob('*/bin/python.exe'))
        if len(candidates) != 1:
            raise RuntimeError('Unexpected FreeCAD portable archive layout')
        check_freecad(candidates[0], freecad['version'])
        shutil.move(str(candidates[0].parents[1]), str(target))
    python = target / 'bin/python.exe'
    check_freecad(python, freecad['version'])
    return python


def setup(uv):
    print('External downloads retain their own licenses; see THIRD_PARTY_NOTICES.md.\n'
          'Hunyuan 2.1: community license with territory/use restrictions.\n'
          'https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE', flush=True)
    config = tool_config()
    bambu = WORKSPACE / config['bambu_studio']['executable']
    if not bambu.is_file():
        raise RuntimeError('Install Bambu Studio, or set its paths in skelecad/config/toolchain.local.json.')
    profiles = Path(config['bambu_studio']['profiles'])
    for kind, key in [('machine', 'machine_preset'), ('process', 'process_preset'), ('filament', 'filament_preset')]:
        if not list((profiles / kind).rglob(config['bambu_studio'][key] + '.json')):
            raise RuntimeError(f'Bambu Studio preset missing: {config["bambu_studio"][key]}')
    freecad = ensure_freecad(config)
    local_path = PROJECT / 'config/toolchain.local.json'
    local = json.loads(local_path.read_text(encoding='utf-8-sig')) if local_path.exists() else {}
    local['freecad'] = {**local.get('freecad', {}), 'python': str(freecad),
                        'executable': str(freecad.with_name('freecad.exe'))}
    local_path.write_text(json.dumps(local, indent=2) + '\n', encoding='utf-8')
    for name, lock in [('workflow_python', 'requirements-workflow.lock'),
                       ('inference_python', 'requirements-inference.lock')]:
        python = WORKSPACE / config[name]['executable']
        if not python.is_file():
            print(f'Creating {name}...', flush=True)
            run([uv, 'venv', python.parent.parent, '--python', config[name]['version']])
        command = [uv, 'pip', 'sync', '--python', python, PROJECT / lock]
        if name == 'inference_python':
            command += ['--torch-backend', config[name]['torch_backend']]
        run(command)
        run([uv, 'pip', 'check', '--python', python])
    source = WORKSPACE / '.tools/Hunyuan3D-2.1'
    if not (source / 'hy3dshape/hy3dshape/pipelines.py').is_file():
        if source.exists():
            raise RuntimeError(f'Incomplete Hunyuan source directory: {source}; resolve it before retrying.')
        print('Downloading Hunyuan shape source...', flush=True)
        with tempfile.TemporaryDirectory(dir=WORKSPACE / '.tools') as directory:
            archive = Path(directory) / 'source.zip'
            urllib.request.urlretrieve(f'https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/archive/{HUNYUAN_COMMIT}.zip', archive)
            with zipfile.ZipFile(archive) as package:
                package.extractall(directory, members=[i for i in package.infolist()
                    if '/hy3dshape/' in i.filename or i.filename.endswith(('/LICENSE', '/NOTICE'))])
            extracted = Path(directory) / ('Hunyuan3D-2.1-' + HUNYUAN_COMMIT)
            shutil.move(str(extracted), str(source))
    inference = WORKSPACE / config['inference_python']['executable']
    env = dict(os.environ, PYTHONUTF8='1', HF_HOME=str(WORKSPACE / '.tools/cache/huggingface'))
    # Use the upstream loader's own cache path and exact filenames. It avoids
    # downloading texture weights and reuses existing shape weights.
    code = f'''import sys
sys.path.insert(0, {str(source / 'hy3dshape')!r})
import torch
assert torch.cuda.is_available(), 'CUDA is unavailable: check the NVIDIA driver.'
from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
from hy3dshape.utils.utils import smart_load_model
from pathlib import Path
import os
from huggingface_hub import hf_hub_download
model_dir = Path(os.environ.get('HY3DGEN_MODELS', '~/.cache/hy3dgen')).expanduser() / 'tencent/Hunyuan3D-2.1'
for filename in ['hunyuan3d-dit-v2-1/config.yaml', 'hunyuan3d-dit-v2-1/model.fp16.ckpt']:
    if not (model_dir / filename).is_file():
        hf_hub_download('tencent/Hunyuan3D-2.1', filename, local_dir=str(model_dir))
config, weights = smart_load_model('tencent/Hunyuan3D-2.1', 'hunyuan3d-dit-v2-1', False, 'fp16')
assert Path(config).is_file() and Path(weights).is_file(), 'Shape model download is incomplete'
print('Hunyuan shape model and CUDA ready')
'''
    print('Checking CUDA and preparing shape weights (first download may take time)...', flush=True)
    run([inference, '-c', code], env=env)
    run([WORKSPACE / config['workflow_python']['executable'], '-c',
         'import cv2, numpy, trimesh, manifold3d, scipy, PIL, psutil; print("Workflow ready")'])
    print('Setup complete.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uv', required=True)
    args = parser.parse_args()
    setup(args.uv)
