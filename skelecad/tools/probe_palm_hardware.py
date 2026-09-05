"""Fast candidate diagnostic using already finished anatomy; never certifies a build."""
import sys,json,itertools
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import trimesh
from hybrid_context import HYBRID
from hybrid_apply_joints import OWNERS,apply_ball,apply_socket
from finish_cut_edges import solid,from_solid
parts={n:trimesh.load_mesh(HYBRID/'edge_finish'/f'{n}_after.stl') for n in set(sum((list(v) for v in OWNERS.values()),[]))}
for connection,(male,female) in OWNERS.items():
    parts[female]=apply_socket(parts[female],connection,False)
    parts[male]=apply_ball(parts[male],connection,False)
out=HYBRID/'candidate';out.mkdir(exist_ok=True)
for n,m in parts.items():
    m.export(out/f'{n}.stl')
    print(n,'solid',m.is_volume,'components',[(round(c.volume,6),c.centroid.tolist()) for c in m.split()],flush=True)
for a,b in itertools.combinations(sorted(parts),2):
    ma,mb=parts[a],parts[b]
    if ((ma.bounds[0]<=mb.bounds[1])&(mb.bounds[0]<=ma.bounds[1])).all():
        vol=(solid(ma)^solid(mb)).volume()
        if vol>.001: print('OVERLAP',a,b,vol,flush=True)
trimesh.util.concatenate(list(parts.values())).export(out/'assembly.stl')
