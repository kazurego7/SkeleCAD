"""Generate exact FreeCAD joint tools for the image-to-3D appearance parts."""

from __future__ import annotations

import json
from pathlib import Path

import FreeCAD as App
import MeshPart
import Part

import trex_v2_project as trex
from joint_retention_trial import deep_c4
from hybrid_context import H, HYBRID


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
OUTPUT = HYBRID / "joint_tools"
REPORT = BUILD / "reports" / "hybrid_joint_tools.json"
PARAMS = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))
J = PARAMS["joint"]


def v(values):
    return App.Vector(*values)


def offset(point, direction, distance):
    return tuple(float(a + b * distance) for a, b in zip(point, direction))


def export_shape(doc, name, shape, report):
    if not shape.isValid():
        shape.fix(0.01, 0.01, 0.1)
    feature = doc.addObject("PartDesign::Feature", name)
    feature.Label = name
    feature.Shape = shape
    # Keep the established anatomical clearance cuts stable. Only the mating
    # hardware needs the finer export profile; recutting dense organic surfaces
    # with finer clearance spheres can create numerically collapsed triangles.
    profile = "clearance" if name.endswith("_clear") else "joint"
    linear_deflection = PARAMS["printing"][profile + "_linear_deflection_mm"]
    angular_deflection = PARAMS["printing"][profile + "_angular_deflection_rad"]
    mesh = MeshPart.meshFromShape(
        Shape=shape,
        LinearDeflection=linear_deflection,
        AngularDeflection=angular_deflection,
        Relative=False,
    )
    path = OUTPUT / f"{name}.stl"
    mesh.write(str(path))
    report.append(
        {
            "name": name,
            "file": str(path.relative_to(ROOT)),
            "valid": bool(shape.isValid()),
            "solid_count": len(shape.Solids),
            "volume_mm3": float(shape.Volume),
            "facets": int(mesh.CountFacets),
            "mesh_profile": profile,
            "linear_deflection_mm": linear_deflection,
            "angular_deflection_rad": angular_deflection,
        }
    )


def connection_tools(
    doc, name, center, mouth_direction, source_support, target_support, report,
    clearance_radius=None, source_clearance_radius=None, target_clear_side=None,
    source_support_radius=None, source_support_mode='capsule',
    source_stud_extension_mm=0.0,
):
    center = tuple(center)
    direction = tuple(mouth_direction)
    ball_r = J["ball_diameter_mm"] / 2.0
    neck_r = J["neck_diameter_mm"] / 2.0
    overlap = min(0.5, neck_r * 0.25)
    stem_start = offset(center, direction, ball_r - overlap)
    source_stud_extension_mm = float(source_stud_extension_mm)
    stem_length = J["stud_reach_mm"] + overlap + source_stud_extension_mm
    support_r = float(
        max(1.2, neck_r - 0.5)
        if source_support_radius is None else source_support_radius
    )
    ball_shapes = [
        Part.makeSphere(ball_r, v(center)),
        Part.makeCylinder(neck_r, stem_length, v(stem_start), v(direction)),
    ]
    if source_support_mode == 'capsule':
        ball_shapes.append(trex.capsule(
            offset(center, direction, ball_r + J["stud_reach_mm"] + source_stud_extension_mm),
            source_support,
            support_r,
        ))
    elif source_support_mode != 'embedded_stem':
        raise ValueError(f'Unknown source support mode: {source_support_mode}')
    ball = trex.fuse_all(ball_shapes)
    production_profile=H.get('production_joint_profile')
    if production_profile:
        if production_profile['type']!='deep_c4':raise ValueError('Unsupported production joint profile')
        trial=PARAMS[production_profile['source_trial']]
        variant=next(v for v in trial['variants'] if v['label']==production_profile['source_variant'])
        if trial['neck_diameter_mm']!=J['neck_diameter_mm']:raise ValueError('Trial/production stem mismatch')
        local_shell,local_void=deep_c4(
            {**variant,'neck_diameter_mm':trial['neck_diameter_mm'],'retention_diameter_mm':trial['retention_diameter_mm']},
            return_void=True,include_mount=False,include_labels=False)
        placement=App.Placement(v(center),App.Rotation(App.Vector(1,0,0),v(direction)))
        local_shell.Placement=placement;local_void.Placement=placement
        socket_outer=local_shell.copy();socket_cut=local_void.copy()
    else:
        socket_outer, socket_cut = trex.socket_components(center, direction)
    if J.get('socket_profile'):
        export_shape(doc, f"{name}_socket_shell", socket_outer.cut(socket_cut).removeSplitter(), report)
        # The new lip must not widen machining into preserved anatomy.
        _,anatomy_cut=trex.socket_local(legacy_profile=True)
        anatomy_cut=trex.oriented(anatomy_cut,center,direction)
        export_shape(doc, f"{name}_socket_anatomy_cut", anatomy_cut, report)
    socket_bridge = trex.capsule(target_support, center, 2.2)
    socket_outer = socket_outer.fuse(socket_bridge).removeSplitter()
    clearance_r = float(
        H["motion_clearance_radius_mm"] if clearance_radius is None else clearance_radius
    )
    source_clear = Part.makeSphere(float(
        H["male_source_clearance_radius_mm"]
        if source_clearance_radius is None else source_clearance_radius
    ), v(center))
    target_clear = Part.makeSphere(clearance_r, v(center))
    if target_clear_side == "left":
        target_clear = target_clear.common(
            Part.makeBox(200.0, 56.0, 200.0, App.Vector(-100.0, 4.0, -50.0))
        )
    elif target_clear_side == "right":
        target_clear = target_clear.common(
            Part.makeBox(200.0, 56.0, 200.0, App.Vector(-100.0, -60.0, -50.0))
        )
    export_shape(doc, f"{name}_ball_add", ball, report)
    export_shape(doc, f"{name}_source_clear", source_clear, report)
    export_shape(doc, f"{name}_target_clear", target_clear, report)
    export_shape(doc, f"{name}_socket_outer", socket_outer, report)
    export_shape(doc, f"{name}_socket_cut", socket_cut, report)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT.glob("*.stl"):
        stale.unlink()
    doc = App.newDocument("HybridJointTools")
    report = []

    if "connections" in H:
        for spec in H["connections"]:
            options = {k: val for k, val in spec.items() if k not in ("name", "center_key")}
            connection_tools(doc, spec["name"], H[spec["center_key"]], report=report, **options)
        finish(doc, report)
        return
    connection_tools(doc, "neck", H["neck_center_mm"], (-1.0, 0.0, 0.0), (-45.1, 1.1, 81.2), (-35.2, -7.0, 78.6), report, source_clearance_radius=7.2)
    connection_tools(
        doc, "shoulder_left", H["shoulder_center_left_mm"], (0.0, 1.0, 0.0),
        (-33.6, 13.0, 77.0), (-27.3, 9.0, 83.2), report,
        source_clearance_radius=H["shoulder_source_clearance_radius_mm"],
        source_support_radius=H["shoulder_buttress_radius_mm"],
    )
    connection_tools(
        doc, "shoulder_right", H["shoulder_center_right_mm"], (0.0, -1.0, 0.0),
        (-33.6, -13.1, 77.0), (-23.2, -8.4, 81.8), report,
        source_clearance_radius=H["shoulder_source_clearance_radius_mm"],
        source_support_radius=H["shoulder_buttress_radius_mm"],
    )
    connection_tools(
        doc, "hip_left", H["hip_center_left_mm"], (0.0, 1.0, 0.0), (-4.1, 14.2, 66.7), (-2.0, 6.8, 69.6), report,
        clearance_radius=6.2,
        source_clearance_radius=H["hip_source_clearance_radius_mm"],
        source_support_radius=H["hip_buttress_radius_mm"],
    )
    connection_tools(
        doc, "hip_right", H["hip_center_right_mm"], (0.0, -1.0, 0.0), (-4.1, -14.5, 66.5), (-13.6, -6.8, 69.1), report,
        clearance_radius=6.2,
        source_clearance_radius=H["hip_source_clearance_radius_mm"],
        source_support_radius=H["hip_buttress_radius_mm"],
    )
    connection_tools(doc, "tail_root", H["tail_root_center_mm"], (1.0, 0.0, 0.0), (22.8, 0.0, 62.3), (8.2, 0.5, 58.6), report, clearance_radius=6.5, source_clearance_radius=6.5)
    connection_tools(doc, "ankle_left", H["ankle_center_left_mm"], (0.0, 0.0, -1.0), (4.3, 20.6, 8.6), (1.1, 22.7, 20.6), report, source_clearance_radius=6.5)
    connection_tools(doc, "ankle_right", H["ankle_center_right_mm"], (0.0, 0.0, -1.0), (4.2, -20.5, 8.5), (2.2, -16.4, 20.6), report, source_clearance_radius=6.5)
    finish(doc, report)


def finish(doc, report):
    for relief in H.get('local_reliefs',[]):
        lo=relief['box_min_mm'];hi=relief['box_max_mm']
        if relief.get('shape')=='sloped_relief':
            points=[v(lo),v([relief['lower_front_x_mm'],lo[1],lo[2]]),
                    v([hi[0],lo[1],hi[2]]),v([lo[0],lo[1],hi[2]]),v(lo)]
            shape=Part.Face(Part.makePolygon(points)).extrude(v([0,hi[1]-lo[1],0]))
        else:
            shape=Part.makeBox(*(b-a for a,b in zip(lo,hi)),v(lo))
        shape=shape.makeFillet(relief['edge_radius_mm'],shape.Edges)
        export_shape(doc,relief['name'],shape,report)
    doc.recompute()
    doc.saveAs(str(HYBRID / "joint_tools.FCStd"))
    Part.export([obj for obj in doc.Objects if hasattr(obj, "Shape")], str(HYBRID / "joint_tools.step"))
    result = {
        "joint_version": J["version"],
        "ball_diameter_mm": J["ball_diameter_mm"],
        "socket_diameter_mm": J["socket_diameter_mm"],
        "socket_outer_diameter_mm": J["socket_outer_diameter_mm"],
        "relief_slot_mm": J["relief_slot_mm"],
        "socket_profile": H.get('production_joint_profile',J.get('socket_profile')),
        "mesh_linear_deflection_mm": PARAMS["printing"]["joint_linear_deflection_mm"],
        "mesh_angular_deflection_rad": PARAMS["printing"]["joint_angular_deflection_rad"],
        "tools": report,
        "passed": all(
            item["valid"] and item["solid_count"] >= 1 and item["volume_mm3"] > 0
            for item in report
        ),
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise RuntimeError("FreeCAD hybrid joint tool validation failed")


if __name__ == "__main__":
    main()
