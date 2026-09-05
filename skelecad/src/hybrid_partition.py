"""Partition the approved image-to-3D appearance into mechanical part regions."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh
from hybrid_context import H, HYBRID, INPUT


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
OUTPUT = HYBRID / "raw_split"
REPORT = BUILD / "reports" / "hybrid_partition.json"
PARAMS = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))


def box(lo, hi):
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    shape = trimesh.creation.box(extents=hi - lo)
    shape.apply_translation((lo + hi) / 2.0)
    return shape


def largest_volume(mesh):
    parts = mesh.split(only_watertight=False)
    if not parts:
        raise RuntimeError("Partition produced no mesh components")
    result = max(parts, key=lambda item: abs(item.volume))
    result.fix_normals(multibody=True)
    return result


def forward_component(mesh):
    """Select the detached lower jaw, which is the most forward head component."""
    parts = mesh.split(only_watertight=False)
    if not parts:
        raise RuntimeError("Jaw partition produced no mesh components")
    result = min(parts, key=lambda item: item.center_mass[0])
    result.fix_normals(multibody=True)
    return result


def leg_selector(side, inner_y, margin=0.0):
    y_outer = 45.0 if side == "left" else -45.0
    y0, y1 = sorted((inner_y, y_outer))
    lower = box(
        (H["leg_selector_lower_x_mm"]-margin, y0, -2.0),
        (45.0, y1, H["leg_selector_step_z_mm"]+margin),
    )
    upper = box(
        (H["leg_selector_upper_x_mm"]-margin, y0, H["leg_selector_step_z_mm"]+margin),
        (45.0, y1, H["leg_selector_top_z_mm"]+margin),
    )
    return trimesh.boolean.union([lower, upper], engine="manifold")


def arm_selector(side, inner_y, margin=0.0):
    y_outer = 45.0 if side == "left" else -45.0
    y0, y1 = sorted((inner_y, y_outer))
    return box(
        (H["arm_selector_min_x_mm"]-margin, y0, H["arm_selector_min_z_mm"]-margin),
        (H["arm_selector_max_x_mm"]+margin, y1, H["arm_selector_max_z_mm"]+margin),
    )


def half_box(axis, lower, upper):
    lo = [-150.0, -60.0, -5.0]
    hi = [150.0, 60.0, 130.0]
    lo[axis] = lower
    hi[axis] = upper
    return box(lo, hi)


def main():
    if H.get("partition_method") == "local_joint_discs":
        from hybrid_local_partition import partition
        partition()
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT.glob("*.stl"):
        stale.unlink()

    source = trimesh.load_mesh(INPUT)
    source_parts = sorted(
        source.split(only_watertight=False), key=lambda item: len(item.faces), reverse=True
    )
    if "head_split_x_mm" in H:
        split = H["head_split_x_mm"]
        gap = H["part_gap_mm"]
        head = largest_volume(trimesh.boolean.intersection([source, half_box(0, -150.0, split-gap/2)], engine="manifold"))
        body = largest_volume(trimesh.boolean.intersection([source, half_box(0, split+gap/2, 150.0)], engine="manifold"))
    elif len(source_parts) != 2:
        raise RuntimeError(f"Expected generated head and body, got {len(source_parts)} components")
    else:
        body, head = source_parts
    body.fix_normals(multibody=True)
    head.fix_normals(multibody=True)

    gap = float(H["part_gap_mm"])
    shoulder_y = float(H["shoulder_split_y_mm"])
    margin = gap/2 if "head_split_x_mm" in H else 0.0
    select_arm_left = arm_selector("left", shoulder_y + gap / 2.0, -margin)
    remove_arm_left = arm_selector("left", shoulder_y - gap / 2.0, margin)
    select_arm_right = arm_selector("right", -shoulder_y - gap / 2.0, -margin)
    remove_arm_right = arm_selector("right", -shoulder_y + gap / 2.0, margin)

    arm_left = largest_volume(
        trimesh.boolean.intersection([body, select_arm_left], engine="manifold")
    )
    arm_right = largest_volume(
        trimesh.boolean.intersection([body, select_arm_right], engine="manifold")
    )
    body_core = trimesh.boolean.difference([body, remove_arm_left], engine="manifold")
    body_core.fix_normals(multibody=True)
    body_core = trimesh.boolean.difference([body_core, remove_arm_right], engine="manifold")
    body_core = largest_volume(body_core)

    hip_y = float(H["hip_split_y_mm"])
    select_left = leg_selector("left", hip_y + gap / 2.0, -margin)
    remove_left = leg_selector("left", hip_y - gap / 2.0, margin)
    select_right = leg_selector("right", -hip_y - gap / 2.0, -margin)
    remove_right = leg_selector("right", -hip_y + gap / 2.0, margin)

    leg_left = largest_volume(
        trimesh.boolean.intersection([body_core, select_left], engine="manifold")
    )
    leg_right = largest_volume(
        trimesh.boolean.intersection([body_core, select_right], engine="manifold")
    )
    body_core = trimesh.boolean.difference([body_core, remove_left], engine="manifold")
    body_core.fix_normals(multibody=True)
    body_core = trimesh.boolean.difference([body_core, remove_right], engine="manifold")
    body_core = largest_volume(body_core)

    tail_root = float(H["tail_root_split_x_mm"])
    tail_region = half_box(0, tail_root + gap / 2.0, 150.0)
    tail_remove = half_box(0, tail_root - gap / 2.0, 150.0)
    tail = largest_volume(
        trimesh.boolean.intersection([body_core, tail_region], engine="manifold")
    )
    torso = largest_volume(
        trimesh.boolean.difference([body_core, tail_remove], engine="manifold")
    )

    ankle_z = float(H["ankle_split_z_mm"])
    foot_left = largest_volume(
        trimesh.boolean.intersection(
            [leg_left, half_box(2, -5.0, ankle_z - gap / 2.0)],
            engine="manifold",
        )
    )
    leg_left = largest_volume(
        trimesh.boolean.intersection(
            [leg_left, half_box(2, ankle_z + gap / 2.0, 130.0)],
            engine="manifold",
        )
    )
    foot_right = largest_volume(
        trimesh.boolean.intersection(
            [leg_right, half_box(2, -5.0, ankle_z - gap / 2.0)],
            engine="manifold",
        )
    )
    leg_right = largest_volume(
        trimesh.boolean.intersection(
            [leg_right, half_box(2, ankle_z + gap / 2.0, 130.0)],
            engine="manifold",
        )
    )

    parts = {
        "head": head,
        "torso": torso,
        "arm_left": arm_left,
        "arm_right": arm_right,
        "leg_left": leg_left,
        "leg_right": leg_right,
        "foot_left": foot_left,
        "foot_right": foot_right,
        "tail": tail,
    }
    report_parts = []
    for name, mesh in parts.items():
        mesh.fix_normals(multibody=True)
        path = OUTPUT / f"{name}.stl"
        mesh.export(path)
        report_parts.append(
            {
                "name": name,
                "file": str(path.relative_to(ROOT)),
                "vertices": int(len(mesh.vertices)),
                "faces": int(len(mesh.faces)),
                "watertight": bool(mesh.is_watertight),
                "winding_consistent": bool(mesh.is_winding_consistent),
                "volume_mm3": float(mesh.volume),
                "bounds_mm": np.round(mesh.extents, 3).tolist(),
            }
        )
    report = {
        "source": str(INPUT.relative_to(ROOT)),
        "part_gap_mm": gap,
        "head_mode": H["head_mode"],
        "parts": report_parts,
        "passed": all(
            item["watertight"]
            and item["winding_consistent"]
            and item["volume_mm3"] > 0
            for item in report_parts
        ),
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise RuntimeError("Hybrid appearance partition validation failed")


if __name__ == "__main__":
    main()
