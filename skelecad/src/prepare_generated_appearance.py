"""Remove image-ground artifacts and prepare a watertight appearance reference."""

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
    parser.add_argument("--ground-cut-y", type=float, default=-0.10)
    parser.add_argument("--skip-ground-cut", action="store_true")
    parser.add_argument("--minimum-faces", type=int, default=50)
    args = parser.parse_args()

    scene = trimesh.load(args.input, force="scene")
    raw = trimesh.util.concatenate(tuple(scene.geometry.values()))
    cropped = raw if args.skip_ground_cut else raw.slice_plane(
        plane_origin=(0.0, args.ground_cut_y, 0.0),
        plane_normal=(0.0, 1.0, 0.0),
        cap=True,
    )
    components = cropped.split(only_watertight=False)
    kept = [part for part in components if len(part.faces) >= args.minimum_faces]
    if not kept:
        raise SystemExit("Ground removal discarded every mesh component")
    clean = trimesh.util.concatenate(kept)
    clean.remove_unreferenced_vertices()
    clean.fix_normals(multibody=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    clean.export(args.output)
    report = {
        "input": str(args.input.resolve()),
        "output": str(args.output.resolve()),
        "ground_cut_y": args.ground_cut_y,
        "ground_cut_applied": not args.skip_ground_cut,
        "minimum_faces": args.minimum_faces,
        "source_faces": int(len(raw.faces)),
        "kept_components": int(len(kept)),
        "vertices": int(len(clean.vertices)),
        "faces": int(len(clean.faces)),
        "watertight": bool(clean.is_watertight),
        "winding_consistent": bool(clean.is_winding_consistent),
        "signed_volume_model_units3": float(clean.volume),
        "extents_model_units": np.round(clean.extents, 6).tolist(),
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
