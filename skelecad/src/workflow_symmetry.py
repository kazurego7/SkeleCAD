"""Exact, non-destructive appearance symmetrisation across the YZ plane."""
from __future__ import annotations

import hashlib

import numpy as np
import trimesh

from finish_cut_edges import from_solid, solid


SIDES = {'negative_x', 'positive_x'}


def symmetrize_yz(mesh, source_side):
    """Keep one closed half, mirror it, and weld both halves at x=0.

    This intentionally does not average the two sides: averaging can soften small
    features and still leave ambiguous joint centres.  The chosen half is the
    immutable source of truth and therefore every reflected point is exact.
    """
    if source_side not in SIDES:
        raise ValueError('左右対称化の基準側が不正です。')
    mesh = mesh.copy()
    if not mesh.is_volume:
        raise ValueError('左右対称化する形状が閉じた立体ではありません。')
    bounds = np.asarray(mesh.bounds, dtype=float)
    if not np.isfinite(bounds).all() or not bounds[0, 0] < 0 < bounds[1, 0]:
        raise ValueError('YZ面をまたぐ形状ではないため、左右対称化できません。')
    padding = max(float(np.max(bounds[1] - bounds[0])) * .02, 1.0)
    if source_side == 'positive_x':
        size = [bounds[1, 0] + padding,
                bounds[1, 1] - bounds[0, 1] + padding * 2,
                bounds[1, 2] - bounds[0, 2] + padding * 2]
        offset = [0.0, bounds[0, 1] - padding, bounds[0, 2] - padding]
    else:
        size = [-bounds[0, 0] + padding,
                bounds[1, 1] - bounds[0, 1] + padding * 2,
                bounds[1, 2] - bounds[0, 2] + padding * 2]
        offset = [bounds[0, 0] - padding, bounds[0, 1] - padding, bounds[0, 2] - padding]

    import manifold3d
    clip = manifold3d.Manifold.cube(size).translate(offset)
    kept = solid(mesh) ^ clip
    if kept.is_empty():
        raise ValueError('基準側の形状を取り出せませんでした。')
    mirrored = kept.transform([[-1.0, 0.0, 0.0, 0.0],
                               [0.0, 1.0, 0.0, 0.0],
                               [0.0, 0.0, 1.0, 0.0]])
    result = from_solid(kept + mirrored)
    if not result.is_volume:
        raise ValueError('中央の継ぎ目を閉じた左右対称形状を作れませんでした。')
    tolerance = 2e-4
    if abs(float(result.bounds[0, 0] + result.bounds[1, 0])) > tolerance:
        raise ValueError('左右対称化後の中心面を検証できませんでした。')
    return result


def geometry_report(mesh, output, previous, source_side):
    report = dict(previous or {})
    report.update(vertices=len(mesh.vertices), faces=len(mesh.faces),
                  watertight=bool(mesh.is_watertight),
                  winding_consistent=bool(mesh.is_winding_consistent),
                  extents_mm=np.asarray(mesh.extents, dtype=float).tolist(),
                  sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                  yz_symmetry={'method':'authoritative_half_mirror_v1',
                               'plane':'x=0', 'source_side':source_side,
                               'maximum_bound_mismatch_mm':abs(float(mesh.bounds[0, 0] + mesh.bounds[1, 0]))})
    return report
