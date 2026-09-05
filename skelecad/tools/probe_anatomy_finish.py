import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import trimesh
from hybrid_context import H,HYBRID,ROOT
from hybrid_local_partition import local_cutters,ring_seam
from finish_cut_edges import finish
name=sys.argv[1] if len(sys.argv)>1 else 'leg_left'
mesh=trimesh.load_mesh(HYBRID/'raw_split'/f'{name}.stl')
cutters=[m.copy() for _,m in local_cutters()]+[ring_seam(1),ring_seam(-1)]
for m in cutters:m.apply_translation(H['part_translation_mm'].get(name,[0,0,0]))
result,removal,record,segments=finish(mesh,cutters,H['cut_edge_finish'],name)
print(json.dumps(record),flush=True)
result.export(ROOT/'.runtime'/f'finished_{name}.stl')
mesh.export(ROOT/'.runtime'/f'before_{name}.stl')
