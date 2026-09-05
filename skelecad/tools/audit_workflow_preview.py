"""Audit actual generated files; no production checks can certify an unfinished job."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def rows(triangles):
    return np.sort(np.ascontiguousarray(triangles,dtype='<f4').reshape(-1,9).view('V36').ravel())


def audit(directory):
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    inference=json.loads((directory/'inference.json').read_text(encoding='utf-8'))
    assert manifest['source_sha256']==sha(directory/'source_original.bin')==inference['source_original_sha256']
    assert sha(directory/'inference.glb')==inference['output_sha256']
    assert sha(directory/'input.png')==inference['input_sha256']
    source=trimesh.load(directory/'appearance.stl',force='mesh')
    assert sha(directory/'appearance.stl')==manifest['geometry']['sha256']
    assert source.is_watertight and source.is_winding_consistent and source.volume>0
    assert abs(max(source.extents)-manifest['target_length_mm'])<1e-4
    parts=[]
    for part in manifest['parts']:
        path=directory/part.get('filename','appearance.stl')
        assert sha(path)==part['sha256']
        mesh=trimesh.load(path,force='mesh',process=False)
        parts.append(mesh)
    actual=trimesh.util.concatenate(parts)
    assert len(actual.faces)==len(source.faces)
    assert np.array_equal(rows(actual.triangles),rows(source.triangles)), 'Preview changed source surface'
    assert manifest['print_ready'] is False
    result={'passed':True,'source_image_hash_matches':True,'inference_hash_matches':True,
            'appearance_watertight':True,'appearance_length_mm':float(max(source.extents)),
            'preview_parts':len(parts),'preview_faces':len(actual.faces),'all_source_faces_preserved_once':True,
            'preview_is_printable':False,'joints_machined':False,'manufacturing_validation':'not performed'}
    (directory/'preview_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
    print(json.dumps(audit(args.directory),indent=2))
