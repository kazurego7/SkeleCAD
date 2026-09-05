"""Sever only finite joint-local discs, then retain complete connected anatomy."""
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.optimize import linear_sum_assignment
from hybrid_context import H, HYBRID, INPUT

ROOT = Path(__file__).resolve().parents[1]


def local_cutters():
    result = []
    for spec in H['connections']:
        name = spec['name']
        axis = np.asarray(spec['mouth_direction'], dtype=float)
        center = np.asarray(H.get('partition_centers_mm', {}).get(name,H[spec['center_key']]), dtype=float)
        center += axis * H['local_cut_offsets_mm'].get(name, 0.0)
        radius = H['local_cut_radii_mm'][name]
        # Bound the polygonal chord error using the configured CAD export profile.
        params = json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
        error = params['printing']['clearance_linear_deflection_mm']
        sections = max(32, int(np.ceil(np.pi/np.arccos(1-error/radius))))
        cut = trimesh.creation.cylinder(radius=radius, height=H['part_gap_mm'], sections=sections)
        cut.apply_transform(trimesh.geometry.align_vectors([0,0,1], axis))
        cut.apply_translation(center)
        result.append((name, cut))
    return result


def ring_seam(side):
    spec=H['hip_ring_transfer']
    center=np.array(spec['seam_center_left_mm'],dtype=float)
    center[1]*=side
    cut=trimesh.creation.cylinder(radius=spec['seam_radius_mm'],height=spec['seam_gap_mm'],sections=48)
    cut.apply_transform(trimesh.geometry.align_vectors([0,0,1],spec['seam_normal']))
    cut.apply_translation(center)
    return cut


def transfer_hip_rings(parts):
    """Move the intact decorative hip rims to torso ownership, before posing."""
    report=[]
    spec=H['hip_ring_transfer']
    for side,label in [(1,'left'),(-1,'right')]:
        name='leg_'+label
        separated=trimesh.boolean.difference([parts[name],ring_seam(side)],engine='manifold')
        pieces=separated.split(only_watertight=False)
        if len(pieces)!=2:
            raise RuntimeError(f'{name}: ring seam must make exactly two pieces, got {len(pieces)}')
        seed=np.array(spec['ring_seed_left_mm'],dtype=float);seed[1]*=side
        ring=min(pieces,key=lambda m:np.linalg.norm(m.center_mass-seed))
        leg=next(m for m in pieces if m is not ring)
        # Fill the original 1.2 mm separation at the ring's inner face. The rim
        # stays in its original world position; only a hidden inward lap is added.
        bridge=ring.copy()
        bridge.apply_translation([0,-side*(H['part_gap_mm']+spec['torso_bridge_overlap_mm']),0])
        torso=trimesh.boolean.union([parts['torso'],ring,bridge],engine='manifold')
        if len(torso.split(only_watertight=False))!=1 or not torso.is_volume:
            raise RuntimeError(f'{label} ring did not join the torso')
        parts['torso']=torso;parts[name]=leg
        ring_path=HYBRID/'ownership_reference'/f'hip_ring_{label}.stl'
        ring_path.parent.mkdir(parents=True,exist_ok=True);ring.export(ring_path)
        report.append({'ring':label,'owner':'torso','volume_mm3':float(ring.volume),
                       'reference':str(ring_path.relative_to(ROOT))})
    return report


def partition():
    if H.get('palm_size',{}).get('enabled'):
        from prepare_palm_source import prepare
        prepare()
    source = trimesh.load_mesh(INPUT)
    cuts = local_cutters()
    cut_union = trimesh.boolean.union([m for _,m in cuts], engine='manifold')
    severed = trimesh.boolean.difference([source, cut_union], engine='manifold')
    pieces = severed.split(only_watertight=False)
    names = list(H['part_assignment_seeds_mm'])
    # Never silently discard disconnected anatomy: unexpected fragments are errors.
    if len(pieces) != len(names):
        diagnostics = [{'volume':float(m.volume),'center':m.center_mass.tolist()} for m in pieces]
        raise RuntimeError(f'Expected exactly {len(names)} intact parts; got {diagnostics}')
    seeds = np.array([H['part_assignment_seeds_mm'][n] for n in names])
    centers = np.array([p.center_mass for p in pieces])
    rows, cols = linear_sum_assignment(np.linalg.norm(seeds[:,None]-centers[None,:],axis=2))
    parts = {names[i]:pieces[j] for i,j in zip(rows,cols)}
    transfers=transfer_hip_rings(parts) if H.get('hip_ring_transfer') else []
    out = HYBRID/'raw_split'
    out.mkdir(parents=True,exist_ok=True)
    items=[]
    for name, mesh in parts.items():
        translation=H.get('part_translation_mm',{}).get(name,[0,0,0])
        mesh.apply_translation(translation)
        mesh.fix_normals(multibody=True)
        if not mesh.is_volume:
            raise RuntimeError(f'Invalid local partition: {name}')
        path=out/f'{name}.stl'
        mesh.export(path)
        items.append({'name':name,'file':str(path.relative_to(ROOT)),
                      'vertices':len(mesh.vertices),'faces':len(mesh.faces),
                      'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),
                      'volume_mm3':float(mesh.volume),'bounds_mm':mesh.extents.tolist(),
                      'translation_mm':translation})
    report={'source':str(INPUT.relative_to(ROOT)),'part_gap_mm':H['part_gap_mm'],
            'method':'local_joint_discs','discarded_components':0,'head_mode':H['head_mode'],
            'parts':items,'ownership_transfers':transfers,'passed':True}
    (ROOT/'build/reports/hybrid_partition.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    partition()
