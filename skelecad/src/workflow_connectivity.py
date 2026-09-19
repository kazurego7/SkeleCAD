"""Bounded, additive connections for image-derived closed shells."""
import io
import time
import numpy as np
import trimesh
import manifold3d
from scipy.spatial import cKDTree
from finish_cut_edges import solid


def repair_connectivity(mesh, cfg, mirror_yz=False):
    started = time.perf_counter()
    if not cfg['enabled']:
        return mesh.copy(), {'enabled': False, 'bridges': []}
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ValueError('接続修復には閉じた向きの整った表面が必要です。')
    shells = list(mesh.split(only_watertight=False))
    parts = sorted((p for p in shells if p.volume > 0), key=lambda p:-p.area)
    cavities = [p for p in shells if p.volume < 0]
    if not parts or len(shells) > cfg['maximum_components']:
        raise ValueError('接続修復の対象が空か、分離片が多すぎます。元形状は保存されています。')
    report = {'method':'bounded_additive_bridges_v1', 'enabled':True,
              'input_components':len(parts), 'output_components':len(parts),
              'cavity_shells':len(cavities), 'bridges':[], 'fully_connected':len(parts)==1}
    if len(parts) == 1:
        report['elapsed_seconds'] = time.perf_counter()-started
        return mesh.copy(), report
    radius = float(cfg['bridge_radius_mm']); gap = float(cfg['maximum_gap_mm'])
    tolerance = float(cfg['volume_tolerance_mm3'])
    if radius <= 0 or gap <= 0 or tolerance <= 0:
        raise ValueError('接続修復の寸法が不正です。')
    trees = [cKDTree(p.vertices) for p in parts]
    edges = []
    for i, part in enumerate(parts):
        for j in range(i):
            separation = np.maximum(np.maximum(part.bounds[0]-parts[j].bounds[1],
                                               parts[j].bounds[0]-part.bounds[1]), 0)
            if np.linalg.norm(separation) > gap:
                continue
            distances, indices = trees[j].query(part.vertices)
            k = int(np.argmin(distances))
            if distances[k] <= gap:
                edges.append((float(distances[k]), j, i,
                              parts[j].vertices[indices[k]].copy(), part.vertices[k].copy()))
    original = solid(mesh)
    cavity_solid = manifold3d.Manifold()
    for cavity in cavities:
        interior = cavity.copy(); interior.invert()
        cavity_solid = cavity_solid + solid(interior)
    if cavities and abs(float((cavity_solid-solid(trimesh.util.concatenate(parts))).volume())) > tolerance:
        raise ValueError('反転した面が内部空洞であることを確認できません。')
    parents = list(range(len(parts)))
    def root(i):
        while parents[i] != i:
            i = parents[i]
        return i
    result = original
    for distance, i, j, start, end in sorted(edges, key=lambda edge:edge[:3]):
        a, b = root(i), root(j)
        if a == b:
            continue
        ends = [manifold3d.Manifold.sphere(radius, int(cfg['circular_segments'])).translate(p)
                for p in (start, end)]
        bridge = manifold3d.Manifold.batch_hull(ends)
        if mirror_yz:
            bridge = bridge + bridge.transform([[-1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.]])
        result = result + (bridge-cavity_solid)
        parents[b] = a
        report['bridges'].append({'components':[i,j], 'gap_upper_bound_mm':distance,
                                  'start_mm':start.tolist(), 'end_mm':end.tolist(),
                                  'radius_mm':radius, 'mirrored_yz':mirror_yz})
    if not report['bridges']:
        report['elapsed_seconds'] = time.perf_counter()-started
        return mesh.copy(), report
    lost = abs(float((original-result).volume()))
    if lost > tolerance:
        raise ValueError(f'接続修復で元形状の保持を確認できません。loss={lost:.8g} mm3')
    data = result.simplify(float(cfg['export_tolerance_mm'])).to_mesh64()
    candidate = trimesh.Trimesh(data.vert_properties[:,:3], data.tri_verts, process=False)
    candidate = trimesh.load(io.BytesIO(candidate.export(file_type='stl')), file_type='stl', process=True)
    if not candidate.is_watertight or not candidate.is_winding_consistent or candidate.volume <= 0:
        raise ValueError('STL保存後の修復形状が閉じた正の立体ではありません。')
    actual = [p for p in candidate.split(only_watertight=False) if p.volume > 0]
    if len(actual) > len({root(i) for i in range(len(parts))}):
        raise ValueError('STL保存後の接続を確認できません。')
    exported = solid(candidate)
    lost = abs(float((original-exported).volume()))
    filled = abs(float((exported ^ cavity_solid).volume()))
    delta = abs(float(exported.volume()-result.volume()))
    if max(lost, filled, delta) > tolerance:
        raise ValueError(f'STL保存後の元形状の保持を確認できません。loss={lost:.8g}, cavity={filled:.8g}, delta={delta:.8g} mm3')
    report.update(output_components=len(actual), fully_connected=len(actual)==1,
                  source_loss_mm3=lost, filled_cavity_mm3=filled, export_volume_delta_mm3=delta,
                  added_volume_mm3=float(exported.volume()-original.volume()),
                  watertight=True, winding_consistent=True, volume_mm3=float(candidate.volume),
                  elapsed_seconds=time.perf_counter()-started)
    return candidate, report
