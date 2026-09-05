"""Compare local inference outputs in a common coordinate system (no registration)."""
import argparse
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree


def compare(reference_path, candidate_path, length_mm):
    reference = trimesh.load(reference_path, force="mesh")
    candidate = trimesh.load(candidate_path, force="mesh")
    scale = length_mm / reference.extents.max()
    distances = np.concatenate([
        cKDTree(reference.vertices).query(candidate.vertices, workers=-1)[0],
        cKDTree(candidate.vertices).query(reference.vertices, workers=-1)[0],
    ]) * scale
    surface_distances = np.concatenate([
        trimesh.proximity.closest_point(reference, trimesh.sample.sample_surface(candidate, 5000, seed=3407)[0])[1],
        trimesh.proximity.closest_point(candidate, trimesh.sample.sample_surface(reference, 5000, seed=3407)[0])[1],
    ]) * scale
    def describe(mesh):
        return dict(faces=len(mesh.faces), watertight=bool(mesh.is_watertight),
                    winding_consistent=bool(mesh.is_winding_consistent),
                    euler_number=int(mesh.euler_number),
                    components=len(mesh.split(only_watertight=False)),
                    volume_mm3=float(mesh.volume * scale**3))
    return dict(reference=describe(reference), candidate=describe(candidate),
                common_scale_mm=scale,
                nearest_vertex_mm=dict(mean=float(distances.mean()),
                                       p95=float(np.quantile(distances, .95)),
                                       maximum=float(distances.max())),
                volume_change_percent=float(100 * (candidate.volume / reference.volume - 1)),
                sampled_surface_mm=dict(samples_per_direction=5000, seed=3407,
                                        mean=float(surface_distances.mean()),
                                        p95=float(np.quantile(surface_distances, .95)),
                                        sampled_maximum=float(surface_distances.max())),
                note="Bidirectional nearest-vertex approximation, not exact surface distance; no alignment or independent scaling.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--length-mm", type=float, default=120)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.reference, args.candidate, args.length_mm)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
