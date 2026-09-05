import json
import sys

import FreeCAD as App
import Part

import trex_v2_project as project


REPORT = project.REPORTS_DIR / "joint_motion_report.json"


def inserted_stud():
    ball_r = project.JOINT["ball_diameter_mm"] / 2
    neck_r = project.JOINT["neck_diameter_mm"] / 2
    ball = Part.makeSphere(ball_r)
    neck = Part.makeCylinder(neck_r, 14, App.Vector(0, 0, 0), App.Vector(1, 0, 0))
    return ball.fuse(neck).removeSplitter()


def socket():
    outer, cutter = project.socket_local()
    return outer.cut(cutter).removeSplitter()


def rotated_about_center(shape, axis, angle):
    copy = shape.copy()
    copy.rotate(App.Vector(0, 0, 0), App.Vector(*axis), angle)
    return copy


def axis_sweep(socket_shape, stud, axis):
    samples = []
    maximum = 0
    for angle in range(0, 46, 5):
        overlap = socket_shape.common(rotated_about_center(stud, axis, angle)).Volume
        clear = overlap <= 0.01
        samples.append({"angle_deg": angle, "overlap_volume_mm3": overlap, "clear": clear})
        if clear:
            maximum = angle
        else:
            break
    return maximum, samples


def main():
    socket_shape = socket()
    stud = inserted_stud()
    pitch, pitch_samples = axis_sweep(socket_shape, stud, (0, 1, 0))
    yaw, yaw_samples = axis_sweep(socket_shape, stud, (0, 0, 1))
    required = project.JOINT.get('socket_profile',{}).get('required_motion_deg',25)
    report = {
        "joint_version": project.JOINT["version"],
        "required_collision_free_angle_deg": required,
        "pitch_collision_free_deg": pitch,
        "yaw_collision_free_deg": yaw,
        "pitch_samples": pitch_samples,
        "yaw_samples": yaw_samples,
        "passed": pitch >= required and yaw >= required,
        "scope": "Rigid CAD interference sweep; snap force and fatigue require physical calibration",
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    if not report["passed"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
