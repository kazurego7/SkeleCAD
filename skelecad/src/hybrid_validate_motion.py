"""Sweep actual hybrid parts around the FreeCAD-authored joint centers."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import trimesh
from hybrid_context import H, HYBRID


ROOT = Path(__file__).resolve().parents[1]
PARTS = HYBRID / "parts"
REPORT = ROOT / "build" / "reports" / "hybrid_motion.json"
PARAMS = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=9)
def load(name):
    mesh = trimesh.load_mesh(PARTS / f"{name}.stl")
    mesh.fix_normals(multibody=True)
    return mesh


def overlap_volume(fixed, moving):
    if not bool(
        ((fixed.bounds[0] <= moving.bounds[1]) & (moving.bounds[0] <= fixed.bounds[1])).all()
    ):
        return 0.0
    overlap = trimesh.boolean.intersection([fixed, moving], engine="manifold")
    return abs(float(overlap.volume)) if len(overlap.faces) else 0.0


def rotated(mesh, center, axis, angle_deg):
    result = mesh.copy()
    matrix = trimesh.transformations.rotation_matrix(
        math.radians(angle_deg), np.asarray(axis, dtype=float), np.asarray(center, dtype=float)
    )
    result.apply_transform(matrix)
    return result


@lru_cache(maxsize=16)
def load_tool(name):
    mesh=trimesh.load_mesh(HYBRID/'joint_tools'/f'{name}.stl')
    mesh.fix_normals(multibody=True)
    return mesh


def intentional_preload(name,center,axis,angle):
    return overlap_volume(load_tool(name+'_socket_shell'),rotated(load_tool(name+'_ball_add'),center,axis,angle))


def sweep(name, fixed_name, moving_name, center, axes):
    moving_names = [moving_name]
    if moving_name.startswith("leg_"):
        moving_names.append(moving_name.replace("leg_", "foot_"))
    fixed_names = sorted(path.stem for path in PARTS.glob("*.stl") if path.stem not in moving_names)
    result = {"name": name, "fixed": fixed_name, "moving": moving_name,
              "moving_group": moving_names, "checked_against": fixed_names, "axes": []}
    for axis_name, axis, angles in axes:
        samples = []
        for angle in angles:
            overlaps = []
            preload=intentional_preload(name,center,axis,angle)
            for moving_part in moving_names:
                posed = rotated(load(moving_part), center, axis, angle)
                for fixed_part in fixed_names:
                    raw = overlap_volume(load(fixed_part), posed)
                    intentional=preload if fixed_part==fixed_name and moving_part==moving_name else 0.0
                    value=max(0.0,raw-intentional)
                    if raw > 0:
                        overlaps.append({"fixed":fixed_part,"moving":moving_part,"raw_overlap_mm3":raw,
                                         "intentional_joint_preload_mm3":intentional,"excess_overlap_mm3":value})
            volume = max((item["excess_overlap_mm3"] for item in overlaps), default=0.0)
            samples.append(
                {
                    "angle_deg": angle,
                    "excess_overlap_volume_mm3": volume,
                    "intentional_joint_preload_mm3": preload,
                    "clear": volume <= 0.30,
                    "overlaps": overlaps,
                }
            )
        result["axes"].append(
            {"axis": axis_name, "samples": samples, "passed": all(x["clear"] for x in samples)}
        )
    result["passed"] = all(item["passed"] for item in result["axes"])
    return result


def main():
    maximum = float(H["required_motion_angle_deg"])
    negative = (-maximum, -maximum / 2, 0.0)
    positive = (0.0, maximum / 2, maximum)
    both = negative + positive[1:]
    hip_left_angles = negative if "head_split_x_mm" in H else positive
    hip_right_angles = tuple(-a for a in hip_left_angles)
    spread=float(H.get('repositioned_motion_angle_deg',maximum))
    spread_positive=tuple(spread*i/3 for i in range(4))
    spread_negative=tuple(-a for a in spread_positive)
    left_spread=(("outward_spread",(1,0,0),spread_positive),) if H.get('part_translation_mm') else ()
    right_spread=(("outward_spread",(1,0,0),spread_negative),) if H.get('part_translation_mm') else ()
    tail_pitch=float(H.get('tail_pitch_review_deg',maximum))
    tail_angles=tuple(float(a) for a in np.linspace(-tail_pitch,tail_pitch,13)) if H.get('tail_pitch_review_deg') else both[1:]
    joints = [
        sweep("neck", "torso", "head", H["neck_center_mm"], (("pitch", (0, 1, 0), both), ("yaw", (0, 0, 1), both))),
        sweep("shoulder_left", "torso", "arm_left", H["shoulder_center_left_mm"], (("outward_yaw", (0, 0, 1), negative),)+left_spread),
        sweep("shoulder_right", "torso", "arm_right", H["shoulder_center_right_mm"], (("outward_yaw", (0, 0, 1), positive),)+right_spread),
        sweep("hip_left", "torso", "leg_left", H["hip_center_left_mm"], (("outward_yaw", (0, 0, 1), hip_left_angles),)+left_spread),
        sweep("hip_right", "torso", "leg_right", H["hip_center_right_mm"], (("outward_yaw", (0, 0, 1), hip_right_angles),)+right_spread),
        sweep("tail_root", "torso", "tail", H["tail_root_center_mm"], (("pitch", (0, 1, 0), tail_angles), ("yaw", (0, 0, 1), both[1:-1]))),
        sweep("ankle_left", "leg_left", "foot_left", H["ankle_center_left_mm"], (("pitch", (1, 0, 0), both), ("yaw", (0, 1, 0), both))),
        sweep("ankle_right", "leg_right", "foot_right", H["ankle_center_right_mm"], (("pitch", (1, 0, 0), both), ("yaw", (0, 1, 0), both))),
    ]

    result = {
        "motion_policy": "detail_first_directional",
        "scope": "One joint at a time against all other parts; feet follow hips. Discrete samples, not simultaneous or continuous motion.",
        "maximum_allowed_excess_overlap_mm3": 0.30,
        "maximum_test_angle_deg": max(maximum,spread,tail_pitch),
        "baseline_directional_angle_deg": maximum,
        "shoulder_hip_outward_spread_deg": H.get('repositioned_motion_angle_deg'),
        "tail_pitch_review_deg": H.get('tail_pitch_review_deg'),
        "ball_joints": joints,
        "head": {"mode": "fixed_one_piece", "jaw_motion": False},
        "passed": all(item["passed"] for item in joints),
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise RuntimeError("Hybrid actual-part motion validation failed")


if __name__ == "__main__":
    main()
