"""Package the validated hybrid mesh parts for FreeCAD review and printing."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import FreeCAD as App
import Mesh
from hybrid_context import H, HYBRID


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
PARTS = HYBRID / "parts"
PRINT = HYBRID / "print"
REPORT = BUILD / "reports" / "hybrid_package.json"
PARAMS = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))
J = PARAMS["joint"]

NAMES = [
    "head", "torso", "arm_left", "arm_right", "leg_left", "leg_right",
    "foot_left", "foot_right", "tail",
]


def add_mesh(doc, name, mesh, label, color):
    obj = doc.addObject("Mesh::Feature", name)
    obj.Label = label
    obj.Mesh = mesh
    obj.addProperty("App::PropertyString", "JointStandard", "SkeleCAD")
    obj.JointStandard = (
        f"joint v{J['version']} / ball {J['ball_diameter_mm']:.1f} mm / "
        f"socket {J['socket_diameter_mm']:.1f} mm"
    )
    if obj.ViewObject:
        obj.ViewObject.ShapeColor = color
        obj.ViewObject.LineColor = (0.18, 0.12, 0.07)
    return obj


def loaded(name):
    return Mesh.Mesh(str(PARTS / f"{name}.stl"))


def make_assembly():
    doc = App.newDocument("SkeleCAD_Hybrid_Assembly")
    group = doc.addObject("App::DocumentObjectGroup", "PrintableParts")
    group.Label = "Validated hybrid T. rex - 9 printable parts / 8 annotated joints"
    combined = Mesh.Mesh()
    for name in NAMES:
        mesh = loaded(name)
        color = (0.90, 0.78, 0.58)
        obj = add_mesh(doc, name, mesh, name.replace("_", " ").title(), color)
        group.addObject(obj)
        combined.addMesh(mesh)
    note = doc.addObject("App::FeaturePython", "DesignAuthority")
    note.addProperty("App::PropertyString", "Appearance")
    note.Appearance = H.get("appearance_mesh", H["appearance_source"])
    note.addProperty("App::PropertyString", "Mechanics")
    note.Mechanics = f"FreeCAD-authored joint v{J['version']}; fixed one-piece head"
    note.addProperty("App::PropertyString", "Validation")
    note.Validation = (
        f"Watertight; static collision 0/36; detail-first directional motion "
        f"up to {H['required_motion_angle_deg']} deg"
    )
    doc.recompute()
    path = HYBRID / "SkeleCAD_Hybrid_Assembly.FCStd"
    doc.saveAs(str(path))
    review_stl = HYBRID / "trex_hybrid_assembly.stl"
    combined.write(str(review_stl))
    bounds = {
        "x": round(combined.BoundBox.XLength, 3),
        "y": round(combined.BoundBox.YLength, 3),
        "z": round(combined.BoundBox.ZLength, 3),
    }
    return path, review_stl, bounds


def make_print_plate():
    PRINT.mkdir(parents=True, exist_ok=True)
    for stale in PARTS.glob("*.3mf"):
        stale.unlink()
    doc = App.newDocument("SkeleCAD_Hybrid_Print_Plate")
    combined = Mesh.Mesh()
    placements = []
    gap = 7.0
    bed_x = 240.0
    cursor_x = gap
    cursor_y = gap
    row_depth = 0.0
    for name in NAMES:
        mesh = loaded(name)
        box = mesh.BoundBox
        width, depth = box.XLength, box.YLength
        if cursor_x + width + gap > bed_x:
            cursor_x = gap
            cursor_y += row_depth + gap
            row_depth = 0.0
        shift = App.Vector(cursor_x - box.XMin, cursor_y - box.YMin, -box.ZMin)
        mesh.translate(shift.x, shift.y, shift.z)
        combined.addMesh(mesh)
        obj = add_mesh(
            doc, f"plate_{name}", mesh,
            f"Print plate - {name.replace('_', ' ')}", (0.90, 0.78, 0.58),
        )
        placements.append({
            "part": name,
            "x_mm": round(cursor_x, 3),
            "y_mm": round(cursor_y, 3),
            "width_mm": round(width, 3),
            "depth_mm": round(depth, 3),
            "height_mm": round(mesh.BoundBox.ZLength, 3),
        })
        cursor_x += width + gap
        row_depth = max(row_depth, depth)
        # Also provide one independently loadable 3MF per printable part.
        loaded(name).write(str(PARTS / f"{name}.3mf"))
    doc.recompute()
    fcstd = HYBRID / "SkeleCAD_Hybrid_Print_Plate.FCStd"
    doc.saveAs(str(fcstd))
    plate_3mf = PRINT / "trex_hybrid_full_print_plate.3mf"
    combined.write(str(plate_3mf))
    combined.write(str(PRINT / "trex_hybrid_full_print_plate.stl"))
    return fcstd, plate_3mf, placements, combined


def main():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    assembly, review_stl, assembly_bounds = make_assembly()
    print_fcstd, plate_3mf, placements, combined = make_print_plate()
    result = {
        "revision": PARAMS["project"]["revision"],
        "appearance_source": H["appearance_source"],
        "appearance_mesh": H.get("appearance_mesh"),
        "appearance_mesh_sha256": hashlib.sha256((ROOT / H.get("appearance_mesh", H["appearance_source"])).read_bytes()).hexdigest(),
        "assembly_fcstd": str(assembly.relative_to(ROOT)),
        "assembly_review_stl": str(review_stl.relative_to(ROOT)),
        "assembly_bounds_mm": assembly_bounds,
        "print_plate_fcstd": str(print_fcstd.relative_to(ROOT)),
        "print_plate_3mf": str(plate_3mf.relative_to(ROOT)),
        "parts": [str((PARTS / f"{name}.stl").relative_to(ROOT)) for name in NAMES],
        "part_3mf_count": len(NAMES),
        "placements": placements,
        "plate_bounds_mm": [
            round(combined.BoundBox.XLength, 3),
            round(combined.BoundBox.YLength, 3),
            round(combined.BoundBox.ZLength, 3),
        ],
        "passed": all((PARTS / f"{name}.3mf").exists() for name in NAMES)
        and assembly.exists() and print_fcstd.exists() and plate_3mf.exists(),
        "note": "Use slicer auto-orient/support analysis before production printing.",
    }
    if H.get('palm_size',{}).get('enabled'):
        target=H['palm_size']['target_assembly_length_mm']
        result['palm_size']={'target_length_mm':target,'actual_length_mm':assembly_bounds['x'],
                             'passed':abs(assembly_bounds['x']-target)<0.05}
        result['passed'] &= result['palm_size']['passed']
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise RuntimeError("Hybrid packaging failed")


if __name__ == "__main__":
    main()
