"""Orient and scale the approved appearance mesh for FreeCAD review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import trimesh


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--length-mm", default=200.0, type=float)
    args = parser.parse_args()

    scene = trimesh.load(args.input, force="scene")
    mesh = trimesh.util.concatenate(tuple(scene.geometry.values()))
    # Hunyuan/glTF: X=width, Y=up, Z=head-to-tail. SkeleCAD: X=length,
    # Y=width, Z=up, with the skull on negative X like the existing assembly.
    vertices = mesh.vertices.copy()
    oriented = np.column_stack((-vertices[:, 2], vertices[:, 0], vertices[:, 1]))
    scale = args.length_mm / float(np.ptp(oriented[:, 0]))
    oriented *= scale
    oriented[:, 2] -= oriented[:, 2].min()
    oriented[:, 0] -= (oriented[:, 0].min() + oriented[:, 0].max()) * 0.5
    oriented[:, 1] -= (oriented[:, 1].min() + oriented[:, 1].max()) * 0.5
    mesh.vertices = oriented
    # (-Z, X, Y) changes handedness. Reorient faces as well as vertex positions,
    # otherwise a closed mesh gets negative volume and vanishes with back-face culling.
    mesh.fix_normals(multibody=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(args.output)
    report = {
        "input": str(args.input.resolve()),
        "output": str(args.output.resolve()),
        "scale_mm_per_model_unit": scale,
        "dimensions_mm": np.round(mesh.extents, 3).tolist(),
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "signed_volume_mm3": float(mesh.volume),
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
