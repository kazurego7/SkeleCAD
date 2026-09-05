"""Verify useful motion with the real T. rex parts, not only joint coupons."""

import json
import sys

import FreeCAD as App

import trex_v2_project as project


REPORT = project.REPORTS_DIR / "assembly_motion_report.json"
DETAIL_FIRST_ANGLE = float(project.PARAMS["hybrid"]["required_motion_angle_deg"])
BALL_ANGLES = (-DETAIL_FIRST_ANGLE, -DETAIL_FIRST_ANGLE / 2, 0, DETAIL_FIRST_ANGLE / 2, DETAIL_FIRST_ANGLE)
JAW_ANGLES = (-30, -20, -10, 0)
MAX_OVERLAP_MM3 = 0.01


def rotated(shape, center, axis, angle):
    result = shape.copy()
    result.rotate(App.Vector(*center), App.Vector(*axis), angle)
    return result


def samples(fixed, moving, center, axis, angles):
    result = []
    for angle in angles:
        overlap = fixed.common(rotated(moving, center, axis, angle)).Volume
        result.append({
            "angle_deg": angle,
            "overlap_volume_mm3": overlap,
            "clear": overlap <= MAX_OVERLAP_MM3,
        })
    return result


def main():
    parts = {
        "skull_upper": project.upper_skull(),
        "jaw_lower": project.lower_jaw(),
        "torso_front": project.torso_front(),
        "torso_rear": project.torso_rear(),
        "leg_left": project.leg("left"),
        "leg_right": project.leg("right"),
        "tail_front": project.tail_front(),
        "tail_rear": project.tail_rear(),
    }
    cases = (
        ("neck", "skull_upper", "torso_front", (-59, 0, 82)),
        ("torso", "torso_front", "torso_rear", (6, 0, 75)),
        ("left_hip", "torso_rear", "leg_left", (23, 17, 65)),
        ("right_hip", "torso_rear", "leg_right", (23, -17, 65)),
        ("tail_root", "torso_rear", "tail_front", (41, 0, 72)),
        ("tail_mid", "tail_front", "tail_rear", (87, 0, 65)),
    )
    joints = []
    for name, fixed_name, moving_name, center in cases:
        pitch = samples(parts[fixed_name], parts[moving_name], center, (0, 1, 0), BALL_ANGLES)
        yaw = samples(parts[fixed_name], parts[moving_name], center, (0, 0, 1), BALL_ANGLES)
        joints.append({
            "name": name,
            "fixed_part": fixed_name,
            "moving_part": moving_name,
            "center_mm": center,
            "pitch": pitch,
            "yaw": yaw,
            "passed": all(item["clear"] for item in pitch + yaw),
        })

    jaw = samples(
        parts["skull_upper"], parts["jaw_lower"], (-74, 0, 69),
        (0, 1, 0), JAW_ANGLES,
    )
    report = {
        "ball_joint_test_angles_deg": BALL_ANGLES,
        "jaw_hinge_test_angles_deg": JAW_ANGLES,
        "maximum_allowed_overlap_mm3": MAX_OVERLAP_MM3,
        "motion_policy": "detail_first",
        "ball_joints": joints,
        "jaw_hinge": {
            "fixed_part": "skull_upper",
            "moving_part": "jaw_lower",
            "samples": jaw,
            "passed": all(item["clear"] for item in jaw),
        },
        "passed": all(item["passed"] for item in joints) and all(item["clear"] for item in jaw),
        "scope": "Rigid CAD interference sweep of the actual adjacent T. rex parts under the detail-first motion policy",
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
