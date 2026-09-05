"""Regression: round a machined hemisphere without touching its remote pole."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import trimesh
from hybrid_context import H
from finish_cut_edges import finish,cut_seams

sphere=trimesh.creation.icosphere(subdivisions=3,radius=5)
tool=trimesh.creation.box([10,20,20]);tool.apply_translation([5,0,0])
before=trimesh.boolean.difference([sphere,tool],engine='manifold')
cfg=H['cut_edge_finish']
after,cutter,record,seams=finish(before,[tool],cfg,'hemisphere')
assert after.is_volume and len(after.split())==1
assert after.volume<before.volume
assert record['max_vertex_shift_mm']<=cfg['max_displacement_mm']+1e-8
assert record['certified_removal_band_mm']<=cfg['audit_band_mm']
assert len(cut_seams(after,[tool],cfg))<len(seams)
assert abs(after.bounds[0,0]-before.bounds[0,0])<1e-6
assert not len(cut_seams(sphere,[tool],cfg)), 'Do not round untouched organic edges'
print('PASS: local rounding, sharp-edge reduction, watertightness, remote pole preservation',record)
