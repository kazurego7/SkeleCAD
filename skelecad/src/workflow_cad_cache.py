"""Exact per-joint artifacts; incomplete entries are never reusable."""
import hashlib
import json
import shutil
import uuid
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cache_key(context,joint):
    geometry={k:v for k,v in joint.items() if k!='calculation_source'}
    return hashlib.sha256(json.dumps([context,geometry],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read_entry(root,key):
    directory=root/key
    if not directory.exists():return None
    record=json.loads((directory/'entry.json').read_text(encoding='utf-8'))
    if record['key']!=key:raise ValueError('CAD cache key mismatch')
    for name,expected in record['files'].items():
        if Path(name).name!=name or digest(directory/name)!=expected:
            raise ValueError('CAD cache artifact integrity mismatch')
    return directory,record


def save_entry(root,key,source,names,parts,fallbacks):
    root.mkdir(parents=True,exist_ok=True)
    pending=root/('pending_'+uuid.uuid4().hex);pending.mkdir()
    for name in names:shutil.copy2(source/name,pending/name)
    record={'key':key,'files':{n:digest(pending/n) for n in names},'parts':parts,'fallbacks':fallbacks}
    (pending/'entry.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    pending.rename(root/key)
