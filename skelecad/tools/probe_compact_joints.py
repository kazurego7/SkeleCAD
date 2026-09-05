"""Read-only geometric probes for compact sockets and the annotated tail stop."""
import sys
from pathlib import Path
import numpy as np
import trimesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hybrid_context import HYBRID,H,PARAMS
from hybrid_validate_motion import overlap_volume,rotated

torso=trimesh.load_mesh(HYBRID/'raw_split/torso.stl')
if '--tail' in sys.argv:
    tail=trimesh.load_mesh(HYBRID/'parts/tail.stl')
    finished=trimesh.load_mesh(HYBRID/'parts/torso.stl')
    for angle in [-5,-7.5,-10,-12.5,-15,5,10,15]:
        posed=rotated(tail,H['tail_root_center_mm'],[0,1,0],angle)
        overlap=trimesh.boolean.intersection([finished,posed],engine='manifold')
        # Locate the interfering region in the original tail frame.
        overlap=rotated(overlap,H['tail_root_center_mm'],[0,1,0],-angle) if len(overlap.faces) else overlap
        print(angle,round(abs(overlap.volume),4),np.round(overlap.bounds,2).tolist() if len(overlap.faces) else [],flush=True)
    raise SystemExit
for joint in ['shoulder_left','hip_left']:
    center=np.array(H[joint.replace('_left','_center_left_mm')],dtype=float)
    for y in range(int(center[1]),7,-1):
        center[1]=y
        sphere=trimesh.creation.icosphere(subdivisions=3,radius=PARAMS['joint']['socket_outer_diameter_mm']/2)
        sphere.apply_translation(center)
        overlap=overlap_volume(torso,sphere)
        print(joint,y,round(overlap,4),flush=True)
for name in ['arm_left','arm_right']:
    mesh=trimesh.load_mesh(HYBRID/'raw_split'/f'{name}.stl')
    mesh.apply_translation(-np.array(H['part_translation_mm'][name]))
    v=mesh.vertices;v=v[v[:,2]>60]
    print(name,'upper bounds',np.round([v.min(0),v.max(0)],2).tolist(),flush=True)
