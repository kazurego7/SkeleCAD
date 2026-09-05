"""Regression: micro-boundary cleanup must not fill ordinary holes."""
import sys
from pathlib import Path
import numpy as np
import trimesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hybrid_apply_joints import weld_quantized_micro_boundaries

cube=trimesh.creation.box()
unchanged=weld_quantized_micro_boundaries(cube.copy(),0.00005,'cube')
assert np.array_equal(unchanged.faces,cube.faces)
assert np.array_equal(unchanged.vertices,cube.vertices)
open_cube=cube.copy();open_cube.update_faces(np.arange(len(cube.faces)-1))
result=weld_quantized_micro_boundaries(open_cube.copy(),0.00005,'large hole')
assert np.array_equal(result.faces,open_cube.faces) and not result.is_watertight
# A triangle split into two nearly coincident vertices produces a microscopic
# open boundary. Collapsing it restores the original surface without filling.
broken=cube.copy();f=broken.faces.copy();v=broken.vertices.copy()
corner=int(f[0,0]);v=np.vstack((v,v[corner]+np.array([0.000001,0,0])))
f[0,0]=len(v)-1
broken=trimesh.Trimesh(v,f,process=False)
result=weld_quantized_micro_boundaries(broken,0.00005,'long boundary')
# This crack includes full-length cube edges, so it is intentionally untouched.
assert not result.is_watertight and np.array_equal(result.faces,broken.faces)
print('PASS: closed mesh unchanged; large holes and extended cracks not welded')
