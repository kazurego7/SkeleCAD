"""Read-only diagnostic, with explicit quantization cleanup, not certification."""
import sys,itertools
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from hybrid_context import HYBRID
from finish_cut_edges import clean,solid
import trimesh
meshes={p.stem:clean(trimesh.load_mesh(p)) for p in (HYBRID/'parts').glob('*.stl')}
for a,b in itertools.combinations(meshes,2):
    m,n=meshes[a],meshes[b]
    if ((m.bounds[0]<=n.bounds[1])&(n.bounds[0]<=m.bounds[1])).all():
        vol=(solid(m)^solid(n)).volume()
        if vol>.001:print(a,b,vol,flush=True)
