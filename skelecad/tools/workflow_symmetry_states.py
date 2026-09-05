"""Independent editing states for the original, left and right appearances."""
import hashlib
import json
import os
import shutil
import uuid

from workflow_store import now, write_json


def choice(state):
    symmetry = state.get('appearance_symmetry') or {}
    return symmetry['source_side'] if symmetry.get('active') else 'original'


def save(directory, state):
    # Publish the pointer last so an interrupted save cannot damage a prior state.
    root = directory / 'symmetry' / 'states' / choice(state)
    snapshot = root / uuid.uuid4().hex
    snapshot.mkdir(parents=True)
    hashes = {}
    for name in ('appearance.stl', 'manifest.json'):
        shutil.copy2(directory / name, snapshot / name)
        hashes[name] = hashlib.sha256((snapshot / name).read_bytes()).hexdigest()
    write_json(snapshot / 'state.json', state)
    write_json(root / 'current.json', {'revision':snapshot.name, 'hashes':hashes})


def restore(directory, target):
    root = directory / 'symmetry' / 'states' / target
    pointer = root / 'current.json'
    if not pointer.exists():
        return None
    record = json.loads(pointer.read_text(encoding='utf-8'))
    revision = record['revision']
    if len(revision) != 32 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('保存した作業状態を照合できません。')
    snapshot = root / revision
    state = json.loads((snapshot / 'state.json').read_text(encoding='utf-8'))
    for name, expected in record['hashes'].items():
        if name not in ('appearance.stl', 'manifest.json') or hashlib.sha256((snapshot / name).read_bytes()).hexdigest() != expected:
            raise ValueError('保存した作業状態を照合できません。')
    for name in ('appearance.stl', 'manifest.json'):
        temporary = directory / (name + '.' + uuid.uuid4().hex + '.tmp')
        shutil.copy2(snapshot / name, temporary)
        os.replace(temporary, directory / name)
    for key in ('pid', 'process_identity'):
        state.pop(key, None)
    state['updated_at'] = now()
    write_json(directory / 'state.json', state)
    return state
