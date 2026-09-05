import sys,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import trimesh,numpy as np
from hybrid_context import HYBRID
from hybrid_apply_joints import OWNERS,apply_socket,weld_quantized_micro_boundaries
from finish_cut_edges import solid,clean
if (HYBRID/'torso_precision_failure.npz').exists():
    data=np.load(HYBRID/'torso_precision_failure.npz');mesh=trimesh.Trimesh(data['vertices'],data['faces'],process=False)
else:
    mesh=trimesh.load_mesh(HYBRID/'edge_finish/torso_after.stl')
    for c,(_,female) in OWNERS.items():
        if female=='torso':mesh=apply_socket(mesh,c,False)
for tolerance in [0,0.00002,0.00005,0.0001,0.0002,0.0004,0.0008,0.0016]:
    original=solid(mesh);m=original.simplify(tolerance).to_mesh64()
    candidate=trimesh.Trimesh(m.vert_properties[:,:3],m.tri_verts,process=False)
    q=clean(trimesh.load_mesh(io.BytesIO(candidate.export(file_type='stl')),file_type='stl'))
    if tolerance:q=weld_quantized_micro_boundaries(q,tolerance,'probe')
    print(tolerance,q.is_volume,q.is_watertight,'delta',float(q.volume-mesh.volume),'bad_edges',int(np.sum(np.bincount(q.edges_unique_inverse)!=2)),[(len(c.faces),float(c.volume)) for c in q.split(only_watertight=False)],flush=True)
