"""Compare saved inference runs without adding connections or changing settings."""
import argparse
import json
from pathlib import Path
import trimesh
from scipy.spatial import cKDTree
from workflow_worker import normalize_mesh


def inspect_run(path, length):
    info = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    target = path.parent/(path.stem+'_comparison_unrepaired.stl')
    geometry = normalize_mesh(path, target, length, connectivity={'enabled':False})
    mesh = trimesh.load(target, force='mesh')
    shells = list(mesh.split(only_watertight=False))
    bodies = sorted([c for c in shells if c.volume > 0], key=lambda c:-c.area)
    tree = cKDTree(bodies[0].vertices)
    return {'source':str(path), 'input_sha256':info.get('input_sha256'),
            'seed':info['seed'], 'steps':info['steps'], 'resolution':info['octree_resolution'],
            'decoder':info.get('actual_decoder', 'unrecorded'),
            'load_seconds':info.get('load_seconds'), 'inference_seconds':info.get('inference_seconds'),
            'total_seconds':info.get('total_seconds'), 'faces':len(mesh.faces),
            'watertight':bool(mesh.is_watertight), 'winding_consistent':bool(mesh.is_winding_consistent),
            'positive_components':len(bodies), 'negative_cavity_shells':sum(int(c.volume < 0) for c in shells),
            'detached':[{'faces':len(c.faces), 'centroid_mm':c.centroid.tolist(),
                         'volume_mm3':float(c.volume),
                         'nearest_body_vertex_mm':float(tree.query(c.vertices)[0].min())}
                        for c in bodies[1:]], 'geometry':geometry}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, action='append', required=True)
    parser.add_argument('--length-mm', type=float, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = [inspect_run(path, args.length_mm) for path in args.input]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    for result in results:
        print(json.dumps({k:v for k,v in result.items() if k not in ('geometry', 'source', 'input_sha256')}))
