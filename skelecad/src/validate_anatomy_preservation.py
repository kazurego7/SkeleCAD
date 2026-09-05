"""Require original surface vertices outside joint-local envelopes to survive."""
import argparse
import hashlib
import json
from pathlib import Path
from functools import lru_cache

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from hybrid_context import H, HYBRID, INPUT

ROOT=Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def addition_bounds():
    return [trimesh.load_mesh(p).bounds for p in (HYBRID/'joint_tools').glob('*.stl')
            if p.stem.endswith(('_ball_add','_socket_outer'))]


def protected_mask(vertices):
    protected=np.ones(len(vertices),dtype=bool)
    for spec in H['connections']:
        center=np.asarray(H.get('partition_centers_mm',{}).get(spec['name'],H[spec['center_key']]),dtype=float)
        # Encloses the finite partition disc, original clearance sphere and
        # precision socket machining. No permissions extend along an entire limb.
        radius=H['local_cut_radii_mm'][spec['name']]
        radius += abs(H['local_cut_offsets_mm'].get(spec['name'],0)) + H['part_gap_mm']/2
        protected &= np.linalg.norm(vertices-center,axis=1)>radius
    return protected


def check(source, target):
    points=source.vertices[protected_mask(source.vertices)]
    distance=cKDTree(target.vertices).query(points)[0]
    missing=distance>H['preservation_tolerance_mm']
    # A support union can bury an original surface vertex without removing any
    # anatomy. Distinguish added material from the actual subtractive regression.
    candidates=np.flatnonzero(missing)
    possible=np.zeros(len(candidates),dtype=bool)
    for bounds in addition_bounds():
        possible |= ((points[candidates]>=bounds[0]) & (points[candidates]<=bounds[1])).all(axis=1)
    covered=np.zeros(len(candidates),dtype=bool)
    eligible=np.flatnonzero(possible)
    # Bound ray-query memory even when checking a badly damaged regression mesh.
    for start in range(0,len(eligible),64):
        chunk=eligible[start:start+64]
        covered[chunk]=target.contains(points[candidates[chunk]])
    missing[candidates[covered]]=False
    lost=points[missing]
    return {'protected_vertices':len(points),'missing_vertices':int(missing.sum()),
            'original_vertices_covered_by_added_support':int(covered.sum()),
            'maximum_nearest_vertex_distance_mm':float(distance.max()) if len(distance) else 0,
            'missing_bounds_mm':np.array([lost.min(0),lost.max(0)]).tolist() if len(lost) else None,
            'passed':not bool(missing.any())}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--assembly')
    parser.add_argument('--report',default='build/reports/anatomy_preservation.json')
    args=parser.parse_args()
    if H.get('part_translation_mm') and not args.assembly:
        from validate_repositioned_anatomy import validate
        validate(ROOT/args.report)
        return
    source=trimesh.load_mesh(INPUT)
    if args.assembly:
        targets=[trimesh.load_mesh(ROOT/args.assembly)]
        per_part={}
    else:
        paths=sorted((HYBRID/'parts').glob('*.stl'))
        targets=[trimesh.load_mesh(p) for p in paths]
        per_part={p.stem:check(trimesh.load_mesh(HYBRID/'raw_split'/p.name),mesh)
                  for p,mesh in zip(paths,targets)}
    overall=check(source,trimesh.util.concatenate(targets))
    result={'source':str(INPUT.relative_to(ROOT)),
            'source_sha256':hashlib.sha256(INPUT.read_bytes()).hexdigest(),
            'scope':'Every original vertex outside the finite joint-local machining envelopes; each full raw part also checked against its own finished part.',
            'tolerance_mm':H['preservation_tolerance_mm'],'overall':overall,'parts':per_part,
            'passed':overall['passed'] and all(p['passed'] for p in per_part.values())}
    (ROOT/args.report).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if not result['passed']: raise SystemExit(2)


if __name__=='__main__': main()
