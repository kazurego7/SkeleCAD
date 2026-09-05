"""Read-only cut trials on the existing raw leg; never writes production meshes."""
from pathlib import Path
import numpy as np
import trimesh
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
if '--source' in sys.argv:
    from hybrid_local_partition import local_cutters
    from hybrid_context import H, INPUT
    mesh=trimesh.load_mesh(INPUT)
    for radius in [6.5,7.0,7.5,8.0]:
        H['local_cut_radii_mm']['hip_left']=radius
        H['local_cut_radii_mm']['hip_right']=radius
        cuts=[c for _,c in local_cutters()]
        for side in [1,-1]:
            cut=trimesh.creation.cylinder(radius=5,height=.4,sections=48)
            cut.apply_transform(trimesh.geometry.align_vectors([0,0,1],[1,0,0]))
            cut.apply_translation([-12,17*side,50])
            cuts.append(cut)
        severed=trimesh.boolean.difference([mesh,trimesh.boolean.union(cuts,engine='manifold')],engine='manifold')
        parts=severed.split(only_watertight=False)
        print(radius,[(round(p.volume,2),np.round(p.center_mass,2).tolist()) for p in parts],flush=True)
    raise SystemExit
side=-1 if '--right' in sys.argv else 1
mesh=trimesh.load_mesh(root/f'backups/revision_1_2_1_before_hip_transfer/hybrid_20260830/raw_split/leg_{"left" if side==1 else "right"}.stl')
for x,z in [(-12,51),(-11,51),(-12,50),(-11,50),(-10,50),(-13,51),(-12,49),(-11,49)]:
    for normal in [(1,0,-1),(1,0,0),(0,0,1)]:
        cut=trimesh.creation.cylinder(radius=5,height=.4,sections=48)
        cut.apply_transform(trimesh.geometry.align_vectors([0,0,1],np.array(normal)/np.linalg.norm(normal)))
        cut.apply_translation([x,17*side,z])
        result=trimesh.boolean.difference([mesh,cut],engine='manifold')
        parts=result.split(only_watertight=False)
        print(x,z,normal,[(round(p.volume,2),np.round(p.center_mass,2).tolist()) for p in parts],flush=True)
