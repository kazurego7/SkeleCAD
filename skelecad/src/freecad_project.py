import json
import math
import sys
from html import escape
from pathlib import Path

import FreeCAD as App
import MeshPart
import Part


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
PARTS_DIR = BUILD / "parts"
ASSEMBLY_DIR = BUILD / "assembly"
REPORTS_DIR = BUILD / "reports"
PRINT_DIR = BUILD / "print"
PARAMS = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))

for directory in (PARTS_DIR, ASSEMBLY_DIR, REPORTS_DIR, PRINT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def joint_values():
    j = PARAMS["legacy_peg_joint"]
    peg_d = j["peg_diameter_mm"]
    clearance = j["socket_clearance_mm"]
    return {
        **j,
        "peg_radius": peg_d / 2,
        "socket_radius": (peg_d + clearance) / 2,
        "socket_depth": j["peg_length_mm"] + j["socket_extra_depth_mm"],
    }


J = joint_values()


def cylinder_x(radius, length, x0=0.0):
    return Part.makeCylinder(radius, length, App.Vector(x0, 0, 0), App.Vector(1, 0, 0))


def capsule_between(start, end, radius):
    start_vector = App.Vector(*start)
    end_vector = App.Vector(*end)
    direction = end_vector.sub(start_vector)
    length = direction.Length
    if length <= 0:
        raise ValueError("Capsule endpoints must be different")
    body = Part.makeCylinder(radius, length, start_vector, direction)
    return body.fuse(Part.makeSphere(radius, start_vector)).fuse(
        Part.makeSphere(radius, end_vector)
    )


def socket_negative_from_left(depth=None, radius=None):
    depth = J["socket_depth"] if depth is None else depth
    radius = J["socket_radius"] if radius is None else radius
    main = cylinder_x(radius, depth + 0.02, -0.01)
    lead = cylinder_x(radius + 0.6, J["lead_in_mm"] + 0.02, -0.02)
    return main.fuse(lead)


def socket_at(surface, inward):
    cut = socket_negative_from_left()
    cut.Placement = App.Placement(
        App.Vector(*surface), App.Rotation(App.Vector(1, 0, 0), App.Vector(*inward))
    )
    return cut


def double_connector():
    peg_len = J["peg_length_mm"]
    collar_t = J["collar_thickness_mm"]
    r = J["peg_radius"]
    rib_r = r + J["retention_rib_height_mm"]
    rib_w = J["retention_rib_width_mm"]
    left = cylinder_x(r, peg_len, -collar_t / 2 - peg_len)
    right = cylinder_x(r, peg_len, collar_t / 2)
    left_rib = cylinder_x(rib_r, rib_w, -collar_t / 2 - peg_len + 0.8)
    right_rib = cylinder_x(rib_r, rib_w, collar_t / 2 + peg_len - rib_w - 0.8)
    collar = cylinder_x(J["collar_diameter_mm"] / 2, collar_t, -collar_t / 2)
    return left.fuse(right).fuse(left_rib).fuse(right_rib).fuse(collar).removeSplitter()


def straight_bone(length):
    bones = PARAMS["bones"]
    end_r = bones["end_diameter_mm"] / 2
    shaft_r = bones["shaft_diameter_mm"] / 2
    if length <= 2 * J["socket_depth"] + 2:
        raise ValueError("Bone is too short for two sockets")
    shaft_len = length - 2 * end_r
    body = cylinder_x(shaft_r, shaft_len, -shaft_len / 2)
    body = body.fuse(Part.makeSphere(end_r, App.Vector(-length / 2 + end_r, 0, 0)))
    body = body.fuse(Part.makeSphere(end_r, App.Vector(length / 2 - end_r, 0, 0)))
    # Short flat annuli preserve the named overall length around each socket mouth.
    body = body.fuse(cylinder_x(end_r, 1.6, -length / 2))
    body = body.fuse(cylinder_x(end_r, 1.6, length / 2 - 1.6))
    left_socket = socket_negative_from_left()
    left_socket.translate(App.Vector(-length / 2, 0, 0))
    right_socket = socket_negative_from_left()
    right_socket.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), 180)
    right_socket.translate(App.Vector(length / 2, 0, 0))
    return body.cut(left_socket.fuse(right_socket)).removeSplitter()


def bent_bone(length, bend_z):
    """Two-socket bone with aligned endpoints and a bowed shaft."""
    bones = PARAMS["bones"]
    end_r = bones["end_diameter_mm"] / 2
    shaft_r = bones["shaft_diameter_mm"] / 2
    if length <= 2 * J["socket_depth"] + 2:
        raise ValueError("Bent bone is too short for two sockets")
    left_center = (-length / 2 + end_r, 0, 0)
    right_center = (length / 2 - end_r, 0, 0)
    middle = (0, 0, bend_z)
    body = capsule_between(left_center, middle, shaft_r).fuse(
        capsule_between(middle, right_center, shaft_r)
    )
    body = body.fuse(Part.makeSphere(end_r, App.Vector(*left_center)))
    body = body.fuse(Part.makeSphere(end_r, App.Vector(*right_center)))
    body = body.fuse(cylinder_x(end_r, 1.6, -length / 2))
    body = body.fuse(cylinder_x(end_r, 1.6, length / 2 - 1.6))
    left_socket = socket_negative_from_left()
    left_socket.translate(App.Vector(-length / 2, 0, 0))
    right_socket = socket_negative_from_left()
    right_socket.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), 180)
    right_socket.translate(App.Vector(length / 2, 0, 0))
    return body.cut(left_socket.fuse(right_socket)).removeSplitter()


def trex_rib_cage():
    trex = PARAMS["trex"]
    length = trex["rib_cage_length_mm"]
    half_width = trex["rib_cage_half_width_mm"]
    depth = trex["rib_cage_depth_mm"]
    rib_radius = trex["rib_diameter_mm"] / 2
    count = int(trex["rib_count"])
    body = straight_bone(length)
    rib_segments = []
    x_positions = [
        -length * 0.32 + index * (length * 0.64 / max(count - 1, 1))
        for index in range(count)
    ]
    for index, x in enumerate(x_positions):
        fullness = 0.82 + 0.18 * math.sin(math.pi * index / max(count - 1, 1))
        side = half_width * fullness
        lower = depth * (0.88 + 0.12 * fullness)
        for sign in (-1, 1):
            points = [
                (x, 0, 0),
                (x, sign * side * 0.72, -depth * 0.12),
                (x, sign * side, -depth * 0.48),
                (x, sign * side * 0.62, -lower * 0.86),
                (x, sign * 2.2, -lower),
            ]
            for start, end in zip(points, points[1:]):
                rib_segments.append(capsule_between(start, end, rib_radius))
    sternum_start = (x_positions[0], 0, -depth * 0.92)
    sternum_end = (x_positions[-1], 0, -depth * 0.92)
    rib_segments.append(capsule_between(sternum_start, sternum_end, rib_radius + 0.25))
    cage = body.multiFuse(rib_segments).removeSplitter()
    cage.fix(0.01, 0.01, 0.1)
    return cage


def three_way_hub():
    radius = PARAMS["bones"]["hub_diameter_mm"] / 2
    body = Part.makeSphere(radius)
    cuts = [
        socket_at((-radius, 0, 0), (1, 0, 0)),
        socket_at((radius, 0, 0), (-1, 0, 0)),
        socket_at((0, 0, -radius), (0, 0, 1)),
    ]
    return body.cut(cuts[0].fuse(cuts[1]).fuse(cuts[2])).removeSplitter()


def cross_hub():
    radius = PARAMS["bones"]["hub_diameter_mm"] / 2
    body = Part.makeSphere(radius)
    cuts = [
        socket_at((-radius, 0, 0), (1, 0, 0)),
        socket_at((radius, 0, 0), (-1, 0, 0)),
        socket_at((0, -radius, 0), (0, 1, 0)),
        socket_at((0, radius, 0), (0, -1, 0)),
    ]
    combined = cuts[0]
    for cut in cuts[1:]:
        combined = combined.fuse(cut)
    return body.cut(combined).removeSplitter()


def trex_skull():
    """Original toy-like tyrannosaur skull with an open jaw silhouette."""
    trex = PARAMS["trex"]
    length = trex["skull_length_mm"]
    width = trex["skull_width_mm"]
    height = trex["skull_height_mm"]
    rear_radius = height * 0.46
    nose_x = rear_radius - length
    cranium = Part.makeSphere(rear_radius, App.Vector(0, 0, 1.2))
    muzzle = Part.makeBox(
        length - rear_radius * 0.55,
        width * 0.72,
        height * 0.48,
        App.Vector(nose_x, -width * 0.36, -height * 0.16),
    )
    brow = capsule_between(
        (nose_x + 3.0, 0, height * 0.22),
        (rear_radius * 0.25, 0, height * 0.30),
        height * 0.20,
    )
    body = cranium.fuse(muzzle).fuse(brow)

    gap_height = trex["jaw_gap_mm"]
    mouth_gap = Part.makeBox(
        length - rear_radius * 0.3,
        width,
        gap_height,
        App.Vector(nose_x - 0.2, -width / 2, -height * 0.30),
    )
    body = body.cut(mouth_gap)

    jaw_z = -height * 0.38 - gap_height
    jaw_radius = max(2.0, PARAMS["printing"]["min_wall_mm"] / 2 + 1.0)
    for sign in (-1, 1):
        body = body.fuse(capsule_between(
            (nose_x + 2.0, sign * width * 0.29, jaw_z),
            (rear_radius * 0.42, sign * width * 0.32, jaw_z + 1.4),
            jaw_radius,
        ))
        body = body.fuse(capsule_between(
            (rear_radius * 0.20, sign * width * 0.30, jaw_z + 1.0),
            (rear_radius * 0.24, sign * width * 0.28, -height * 0.10),
            jaw_radius,
        ))
    body = body.fuse(capsule_between(
        (nose_x + 2.0, -width * 0.29, jaw_z),
        (nose_x + 2.0, width * 0.29, jaw_z),
        jaw_radius,
    ))

    tooth_base_z = -height * 0.085
    for x in (nose_x + 7.0, nose_x + 14.0, nose_x + 21.0):
        for sign in (-1, 1):
            tooth = Part.makeCone(
                1.45, 1.0, 3.8,
                App.Vector(x, sign * width * 0.27, tooth_base_z),
                App.Vector(0, 0, -1),
            )
            body = body.fuse(tooth)

    eye_a = Part.makeCylinder(3.7, width + 2, App.Vector(-2.5, -width / 2 - 1, 2.5), App.Vector(0, 1, 0))
    nasal_a = Part.makeCylinder(2.2, width + 2, App.Vector(nose_x + 7.0, -width / 2 - 1, 1.0), App.Vector(0, 1, 0))
    rear_socket = socket_at((rear_radius, 0, 0), (-1, 0, 0))
    return body.cut(eye_a.fuse(nasal_a).fuse(rear_socket)).removeSplitter()


def arm_claw():
    trex = PARAMS["trex"]
    palm_radius = PARAMS["bones"]["end_diameter_mm"] / 2
    finger_radius = max(1.25, PARAMS["printing"]["min_wall_mm"] * 0.7)
    body = Part.makeSphere(palm_radius)
    length = trex["arm_claw_length_mm"]
    for y_offset in (-2.3, 2.3):
        body = body.fuse(capsule_between(
            (-palm_radius * 0.35, y_offset * 0.45, -0.6),
            (-length, y_offset, -1.8),
            finger_radius,
        ))
    rear_socket = socket_at((palm_radius, 0, 0), (-1, 0, 0))
    return body.cut(rear_socket).removeSplitter()


def calibration_coupon():
    clearances = PARAMS["printing"]["calibration_clearances_mm"]
    plate = Part.makeBox(44, 20, 4, App.Vector(-22, -10, 0))
    for index, clearance in enumerate(clearances):
        x = -12 + 12 * index
        hole = Part.makeCylinder((J["peg_diameter_mm"] + clearance) / 2, 4.2,
                                 App.Vector(x, 0, -0.1), App.Vector(0, 0, 1))
        plate = plate.cut(hole)
    return plate.removeSplitter()


def add_feature(doc, name, label, shape, color):
    obj = doc.addObject("Part::Feature", name)
    obj.Label = label
    obj.Shape = shape
    obj.addProperty("App::PropertyString", "GeneratedBy", "SkeleCAD")
    obj.GeneratedBy = "src/freecad_project.py"
    if obj.ViewObject is not None:
        obj.ViewObject.ShapeColor = color
    return obj


def export_shape(name, shape):
    if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
        raise RuntimeError(f"Invalid CAD solid: {name}")
    temp = App.newDocument(f"Export_{name}")
    obj = add_feature(temp, name, name, shape, (0.86, 0.82, 0.70))
    Part.export([obj], str(PARTS_DIR / f"{name}.step"))
    # Match fit coupons and standalone joint exports to the production joint mesh.
    precision_joint = name in {
        "joint_calibration_v2", "ball_test_key_v2",
        "ball_connector_v2", "ball_stud_specimen_v2",
    }
    prefix = "joint_" if precision_joint else ""
    mesh = MeshPart.meshFromShape(
        Shape=shape,
        LinearDeflection=PARAMS["printing"][prefix + "linear_deflection_mm"],
        AngularDeflection=PARAMS["printing"][prefix + "angular_deflection_rad"],
        Relative=False,
    )
    mesh.write(str(PARTS_DIR / f"{name}.stl"))
    mesh.write(str(PARTS_DIR / f"{name}.3mf"))
    info = {
        "name": name,
        "valid": shape.isValid(),
        "solid_count": len(shape.Solids),
        "volume_mm3": shape.Volume,
        "area_mm2": shape.Area,
        "bounds_mm": {
            "x": shape.BoundBox.XLength,
            "y": shape.BoundBox.YLength,
            "z": shape.BoundBox.ZLength,
        },
        "mesh_facets": mesh.CountFacets,
    }
    App.closeDocument(temp.Name)
    return info


def make_print_package(shapes):
    coupon = shapes["calibration_coupon"].copy()
    connector = shapes["connector_v1"].copy()
    connector.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), -90)
    connector.translate(App.Vector(30, 0, -connector.BoundBox.ZMin))
    kit = Part.makeCompound([coupon, connector])
    mesh = MeshPart.meshFromShape(
        Shape=kit,
        LinearDeflection=PARAMS["printing"]["linear_deflection_mm"],
        AngularDeflection=PARAMS["printing"]["angular_deflection_rad"],
        Relative=False,
    )
    mesh.write(str(PRINT_DIR / "starter_fit_kit.3mf"))
    mesh.write(str(PRINT_DIR / "starter_fit_kit.stl"))
    return {
        "file": "build/print/starter_fit_kit.3mf",
        "facets": mesh.CountFacets,
        "bounds_mm": {
            "x": kit.BoundBox.XLength,
            "y": kit.BoundBox.YLength,
            "z": kit.BoundBox.ZLength,
        },
        "contents": ["calibration_coupon", "connector_v1_vertical"]
    }


def placed(shape, xyz, axis=(0, 0, 1), angle=0):
    copy = shape.copy()
    copy.Placement = App.Placement(App.Vector(*xyz), App.Rotation(App.Vector(*axis), angle))
    return copy


def oriented(shape, center, direction):
    copy = shape.copy()
    copy.Placement = App.Placement(
        App.Vector(*center), App.Rotation(App.Vector(1, 0, 0), App.Vector(*direction))
    )
    return copy


def render_assembly_svg(instances, output_path):
    """Create a dependency-free isometric review image from FreeCAD tessellation."""
    triangles = []
    for name, shape, color in instances:
        preview_mesh = MeshPart.meshFromShape(
            Shape=shape, LinearDeflection=0.45, AngularDeflection=0.45, Relative=False
        )
        vertices, faces = preview_mesh.Topology
        points = [(vertex.x, vertex.y, vertex.z) for vertex in vertices]
        for face in faces:
            tri = [points[index] for index in face]
            if len(tri) != 3:
                continue
            a, b, c = tri
            ab = tuple(b[i] - a[i] for i in range(3))
            ac = tuple(c[i] - a[i] for i in range(3))
            normal = (ab[1]*ac[2]-ab[2]*ac[1],
                      ab[2]*ac[0]-ab[0]*ac[2],
                      ab[0]*ac[1]-ab[1]*ac[0])
            nlen = math.sqrt(sum(value * value for value in normal)) or 1.0
            light = max(0.0, (normal[0]*-0.25 + normal[1]*-0.35 + normal[2]*0.9) / nlen)
            shade = 0.52 + 0.48 * light
            projected = []
            depth = 0.0
            for x, y, z in tri:
                # Near-side profile: x stays horizontal and z stays upright,
                # while a small y offset keeps paired limbs and ribs readable.
                projected.append((x - y * 0.30, z + y * 0.18))
                depth += (y + x * 0.002 + z * 0.001) / 3.0
            rgb = tuple(max(0, min(255, round(channel * shade * 255))) for channel in color)
            triangles.append((depth, projected, rgb, name))
    if not triangles:
        raise RuntimeError("Assembly preview has no triangles")
    all_xy = [point for _, projected, _, _ in triangles for point in projected]
    min_x, max_x = min(p[0] for p in all_xy), max(p[0] for p in all_xy)
    min_y, max_y = min(p[1] for p in all_xy), max(p[1] for p in all_xy)
    width, height, margin = 1200, 760, 42
    scale = min((width - 2*margin) / max(max_x-min_x, 1),
                (height - 2*margin) / max(max_y-min_y, 1))
    polygons = []
    for _, projected, rgb, name in sorted(triangles, key=lambda item: item[0]):
        coords = " ".join(
            f"{margin + (x-min_x)*scale:.2f},{height-margin-(y-min_y)*scale:.2f}"
            for x, y in projected
        )
        polygons.append(
            f'<polygon points="{coords}" fill="rgb{rgb}" stroke="rgb(70,67,60)" '
            f'stroke-width="0.20" stroke-opacity="0.55"><title>{escape(name)}</title></polygon>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="#f3f1ec"/>'
        + "".join(polygons)
        + '<rect x="24" y="18" width="470" height="44" rx="8" fill="#f3f1ec" opacity="0.92"/>'
        + f'<text x="42" y="48" font-family="Segoe UI, sans-serif" font-size="24" '
        f'fill="#303438">SkeleCAD T. rex review — {escape(PARAMS["project"]["revision"])}</text>'
        + "</svg>"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")


def render_orthographic_svg(instances, output_path):
    """Render side, front, and top projections for proportion review."""
    triangles = []
    for name, shape, color in instances:
        preview_mesh = MeshPart.meshFromShape(
            Shape=shape, LinearDeflection=4.0, AngularDeflection=1.55, Relative=False
        )
        vertices, faces = preview_mesh.Topology
        points = [(vertex.x, vertex.y, vertex.z) for vertex in vertices]
        for face in faces:
            if len(face) == 3:
                triangles.append(([points[index] for index in face], color, name))

    views = [
        ("SIDE", 24, 54, 750, 290, lambda p: (p[0], p[2]), lambda p: p[1]),
        ("FRONT", 800, 54, 376, 290, lambda p: (p[1], p[2]), lambda p: -p[0]),
        ("TOP", 24, 398, 750, 290, lambda p: (p[0], -p[1]), lambda p: p[2]),
    ]
    elements = ['<rect width="100%" height="100%" fill="#f3f1ec"/>']
    for label, px, py, pw, ph, project, depth in views:
        projected = []
        for tri, color, name in triangles:
            xy = [project(point) for point in tri]
            projected.append((sum(depth(point) for point in tri) / 3, xy, color, name))
        all_xy = [point for _, tri, _, _ in projected for point in tri]
        min_x, max_x = min(p[0] for p in all_xy), max(p[0] for p in all_xy)
        min_y, max_y = min(p[1] for p in all_xy), max(p[1] for p in all_xy)
        inset = 22
        scale = min(
            (pw - 2 * inset) / max(max_x - min_x, 1),
            (ph - 2 * inset) / max(max_y - min_y, 1),
        )
        elements.append(
            f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="8" '
            'fill="#faf9f6" stroke="#b9b4aa" stroke-width="1.5"/>'
        )
        for _, tri, color, name in sorted(projected, key=lambda item: item[0]):
            coords = " ".join(
                f"{px + inset + (x-min_x)*scale:.2f},{py + ph - inset - (y-min_y)*scale:.2f}"
                for x, y in tri
            )
            rgb = tuple(round(channel * 255) for channel in color)
            elements.append(
                f'<polygon points="{coords}" fill="rgb{rgb}" stroke="#514d44" '
                f'stroke-width="0.18" stroke-opacity="0.50"><title>{escape(name)}</title></polygon>'
            )
        elements.append(
            f'<text x="{px + 14}" y="{py + 25}" font-family="Segoe UI, sans-serif" '
            f'font-size="18" font-weight="600" fill="#303438">{label}</text>'
        )

    elements.extend([
        '<rect x="800" y="398" width="376" height="290" rx="8" fill="#e9e5dc"/>',
        '<text x="824" y="438" font-family="Segoe UI, sans-serif" font-size="22" '
        'font-weight="600" fill="#303438">PROPORTION REVIEW</text>',
        '<text x="824" y="478" font-family="Segoe UI, sans-serif" font-size="17" fill="#4c5054">'
        'Skull · rib cage · pelvis</text>',
        '<text x="824" y="510" font-family="Segoe UI, sans-serif" font-size="17" fill="#4c5054">'
        'Leg stance · tail taper</text>',
        '<text x="824" y="542" font-family="Segoe UI, sans-serif" font-size="17" fill="#4c5054">'
        'Joint centers remain functional</text>',
        '<text x="24" y="34" font-family="Segoe UI, sans-serif" font-size="24" '
        'font-weight="600" fill="#303438">SkeleCAD T. rex — orthographic review</text>',
    ])
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" '
        'viewBox="0 0 1200 720">' + "".join(elements) + '</svg>'
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")


def build_documents(shapes):
    parts_doc = App.newDocument("SkeleCAD_Parts")
    palette = {
        "connector_v1": (0.92, 0.34, 0.20),
        "calibration_coupon": (0.55, 0.65, 0.72),
    }
    for name, shape in shapes.items():
        add_feature(parts_doc, name, name.replace("_", " ").title(), shape,
                    palette.get(name, (0.88, 0.84, 0.70)))
    parts_doc.recompute()
    parts_doc.saveAs(str(BUILD / "SkeleCAD_Parts.FCStd"))

    assembly_doc = App.newDocument("SkeleCAD_Assembly")
    arm_bone = shapes["trex_arm_bone"]
    bone_long = shapes["bone_long"]
    bone_short = shapes["bone_short"]
    femur = shapes["trex_femur"]
    shin = shapes["trex_shin"]
    rib_cage = shapes["trex_rib_cage"]
    hub = shapes["hub_3way"]
    cross = shapes["hub_cross"]
    skull = shapes["trex_skull"]
    claw = shapes["arm_claw"]
    connector = shapes["connector_v1"]
    trex = PARAMS["trex"]
    bones = PARAMS["bones"]
    hub_r = PARAMS["bones"]["hub_diameter_mm"] / 2
    half_collar = J["collar_thickness_mm"] / 2
    hub_joint = hub_r + half_collar
    collar = J["collar_thickness_mm"]
    tiny_length = bones["tiny_length_mm"]
    short_length = bones["short_length_mm"]
    long_length = bones["long_length_mm"]
    rib_length = trex["rib_cage_length_mm"]
    skull_rear_radius = trex["skull_height_mm"] * 0.46
    palm_radius = bones["end_diameter_mm"] / 2
    z_body = trex["body_height_mm"]
    pelvis_x = 20.0
    rib_center_x = pelvis_x - (hub_r + collar + rib_length / 2)
    shoulder_x = pelvis_x - (2 * hub_r + 2 * collar + rib_length)
    neck_center_x = shoulder_x - (hub_r + collar + short_length / 2)
    neck_front_mouth_x = shoulder_x - (hub_r + collar + short_length)
    skull_center_x = neck_front_mouth_x - collar - skull_rear_radius
    tail_bone_center_x = pelvis_x + hub_r + collar + long_length / 2
    tail_hub_x = pelvis_x + 2 * hub_r + 2 * collar + long_length
    tail_tip_center_x = tail_hub_x + hub_r + collar + short_length / 2
    hip_bone_center_y = hub_r + collar + short_length / 2
    hip_y = 2 * hub_r + 2 * collar + short_length
    femur_center_z = z_body - (hub_r + collar + long_length / 2)
    knee_z = z_body - (2 * hub_r + 2 * collar + long_length)
    shin_center_z = knee_z - (hub_r + collar + short_length / 2)
    ankle_z = knee_z - (2 * hub_r + 2 * collar + short_length)
    foot_center_x = pelvis_x - (hub_r + collar + short_length / 2)
    arm_bone_center_y = hub_r + collar + tiny_length / 2
    hand_center_y = hub_r + 2 * collar + tiny_length + palm_radius
    bone_color = (0.88, 0.84, 0.70)
    hub_color = (0.72, 0.68, 0.55)
    pin_color = (0.92, 0.34, 0.20)
    instances = [
        ("PelvisCrossHub", placed(cross, (pelvis_x, 0, z_body)), hub_color),
        ("RibCage", oriented(rib_cage, (rib_center_x, 0, z_body), (-1, 0, 0)), bone_color),
        ("PelvisTorsoPin", oriented(connector, (pelvis_x - hub_joint, 0, z_body), (-1, 0, 0)), pin_color),
        ("ShoulderCrossHub", placed(cross, (shoulder_x, 0, z_body)), hub_color),
        ("TorsoShoulderPin", oriented(connector, (shoulder_x + hub_joint, 0, z_body), (1, 0, 0)), pin_color),
        ("NeckBone", oriented(bone_short, (neck_center_x, 0, z_body), (-1, 0, 0)), bone_color),
        ("ShoulderNeckPin", oriented(connector, (shoulder_x - hub_joint, 0, z_body), (-1, 0, 0)), pin_color),
        ("TrexSkull", placed(skull, (skull_center_x, 0, z_body)), bone_color),
        ("SkullPin", oriented(connector, (neck_front_mouth_x - half_collar, 0, z_body), (-1, 0, 0)), pin_color),
        ("TailLong", oriented(bone_long, (tail_bone_center_x, 0, z_body), (1, 0, 0)), bone_color),
        ("PelvisTailPin", oriented(connector, (pelvis_x + hub_joint, 0, z_body), (1, 0, 0)), pin_color),
        ("TailHub", placed(hub, (tail_hub_x, 0, z_body)), hub_color),
        ("TailHubPin", oriented(connector, (tail_hub_x - hub_joint, 0, z_body), (-1, 0, 0)), pin_color),
        ("TailTip", oriented(bone_short, (tail_tip_center_x, 0, z_body), (1, 0, 0)), bone_color),
        ("TailTipPin", oriented(connector, (tail_hub_x + hub_joint, 0, z_body), (1, 0, 0)), pin_color),
    ]
    for side_name, sign in (("Left", 1), ("Right", -1)):
        y_bone = sign * hip_bone_center_y
        y_hip = sign * hip_y
        instances.extend([
            (f"{side_name}HipBone", oriented(bone_short, (pelvis_x, y_bone, z_body), (0, sign, 0)), bone_color),
            (f"{side_name}PelvisPin", oriented(connector, (pelvis_x, sign * hub_joint, z_body), (0, sign, 0)), pin_color),
            (f"{side_name}HipPin", oriented(connector, (pelvis_x, sign * (hip_y - hub_joint), z_body), (0, sign, 0)), pin_color),
            (f"{side_name}HipHub", placed(hub, (pelvis_x, y_hip, z_body), (0, 0, 1), 90), hub_color),
            (f"{side_name}Femur", oriented(femur, (pelvis_x, y_hip, femur_center_z), (0, 0, -1)), bone_color),
            (f"{side_name}FemurTopPin", oriented(connector, (pelvis_x, y_hip, z_body - hub_joint), (0, 0, -1)), pin_color),
            (f"{side_name}KneeHub", placed(cross, (pelvis_x, y_hip, knee_z), (0, 1, 0), 90), hub_color),
            (f"{side_name}KneeTopPin", oriented(connector, (pelvis_x, y_hip, knee_z + hub_joint), (0, 0, 1)), pin_color),
            (f"{side_name}Shin", oriented(shin, (pelvis_x, y_hip, shin_center_z), (0, 0, -1)), bone_color),
            (f"{side_name}KneeBottomPin", oriented(connector, (pelvis_x, y_hip, knee_z - hub_joint), (0, 0, -1)), pin_color),
            (f"{side_name}AnkleHub", placed(hub, (pelvis_x, y_hip, ankle_z), (1, 0, 0), 180), hub_color),
            (f"{side_name}AnklePin", oriented(connector, (pelvis_x, y_hip, ankle_z + hub_joint), (0, 0, 1)), pin_color),
            (f"{side_name}Foot", oriented(bone_short, (foot_center_x, y_hip, ankle_z), (-1, 0, 0)), bone_color),
            (f"{side_name}FootPin", oriented(connector, (pelvis_x - hub_joint, y_hip, ankle_z), (-1, 0, 0)), pin_color),
        ])
        arm_y = sign * arm_bone_center_y
        hand_y = sign * hand_center_y
        claw_direction = (0, -sign, 0)
        instances.extend([
            (f"{side_name}TinyArm", oriented(arm_bone, (shoulder_x, arm_y, z_body), (0, sign, 0)), bone_color),
            (f"{side_name}ShoulderArmPin", oriented(connector, (shoulder_x, sign * hub_joint, z_body), (0, sign, 0)), pin_color),
            (f"{side_name}ArmClaw", oriented(claw, (shoulder_x, hand_y, z_body), claw_direction), bone_color),
            (f"{side_name}ClawPin", oriented(connector, (shoulder_x, sign * (hub_r + collar + tiny_length + half_collar), z_body), (0, sign, 0)), pin_color),
        ])
    assembly_shapes = []
    for name, shape, color in instances:
        add_feature(assembly_doc, name, name, shape, color)
        assembly_shapes.append(shape)
    collisions = []
    for index, (name_a, shape_a, _) in enumerate(instances):
        box_a = shape_a.BoundBox
        for name_b, shape_b, _ in instances[index + 1:]:
            box_b = shape_b.BoundBox
            boxes_overlap = not (
                box_a.XMax < box_b.XMin or box_b.XMax < box_a.XMin or
                box_a.YMax < box_b.YMin or box_b.YMax < box_a.YMin or
                box_a.ZMax < box_b.ZMin or box_b.ZMax < box_a.ZMin
            )
            if not boxes_overlap:
                continue
            overlap_volume = shape_a.common(shape_b).Volume
            if overlap_volume > 0.01:
                collisions.append({
                    "a": name_a, "b": name_b,
                    "overlap_volume_mm3": overlap_volume
                })
    assembly_doc.recompute()
    assembly_doc.saveAs(str(ASSEMBLY_DIR / "SkeleCAD_Assembly.FCStd"))
    compound = Part.makeCompound(assembly_shapes)
    assembly_obj = assembly_doc.addObject("Part::Feature", "AssemblyExport")
    assembly_obj.Shape = compound
    if assembly_obj.ViewObject is not None:
        assembly_obj.ViewObject.Visibility = False
    Part.export([assembly_obj], str(ASSEMBLY_DIR / "SkeleCAD_Assembly.step"))
    # Some export paths leave the source objects hidden in the saved document.
    # Force the review instances visible so a beginner sees the model immediately.
    for obj in assembly_doc.Objects:
        if obj.Name != "AssemblyExport" and obj.ViewObject is not None:
            obj.ViewObject.Visibility = True
    if assembly_obj.ViewObject is not None:
        assembly_obj.ViewObject.Visibility = False
    assembly_doc.saveAs(str(ASSEMBLY_DIR / "SkeleCAD_Assembly.FCStd"))
    render_assembly_svg(instances, BUILD / "preview" / "assembly.svg")
    assembly_report = {
        "instances": [name for name, _, _ in instances],
        "instance_count": len(instances),
        "bounds_mm": {
            "x": compound.BoundBox.XLength,
            "y": compound.BoundBox.YLength,
            "z": compound.BoundBox.ZLength,
        },
        "review_image": "build/preview/assembly.svg",
        "collision_count": len(collisions),
        "collisions": collisions,
        "note": "Visual placement preview; physical joint fit requires calibration print"
    }
    (REPORTS_DIR / "assembly_report.json").write_text(
        json.dumps(assembly_report, indent=2), encoding="utf-8"
    )
    if collisions:
        raise RuntimeError(f"Assembly contains {len(collisions)} volumetric collisions")
    return parts_doc, assembly_doc


def main():
    import sys
    if len(sys.argv)==2 and sys.argv[1]=='--holding-trial':
        from joint_holding_trial import generate
        return generate()
    if len(sys.argv)==2 and sys.argv[1]=='--holding-step-trial':
        from joint_holding_trial import generate
        return generate('joint_holding_step_trial','HoldingTrialR3')
    if len(sys.argv)==3 and sys.argv[1]=='--workflow-tools':
        from freecad_workflow_tools import generate
        return generate(Path(sys.argv[2]))
    if len(sys.argv)==3 and sys.argv[1]=='--workflow-assembly':
        from freecad_workflow_tools import assembly_document
        return assembly_document(Path(sys.argv[2]))
    from trex_v2_project import main as build_trex_v2
    return build_trex_v2()

    for pattern in ("*.step", "*.stl", "*.3mf"):
        for stale in PARTS_DIR.glob(pattern):
            stale.unlink()
    shapes = {
        "connector_v1": double_connector(),
        "bone_short": straight_bone(PARAMS["bones"]["short_length_mm"]),
        "bone_long": straight_bone(PARAMS["bones"]["long_length_mm"]),
        "trex_arm_bone": bent_bone(PARAMS["bones"]["tiny_length_mm"], -4.0),
        "trex_femur": bent_bone(PARAMS["bones"]["long_length_mm"], 10.0),
        "trex_shin": bent_bone(PARAMS["bones"]["short_length_mm"], -7.0),
        "trex_rib_cage": trex_rib_cage(),
        "hub_3way": three_way_hub(),
        "hub_cross": cross_hub(),
        "trex_skull": trex_skull(),
        "arm_claw": arm_claw(),
        "calibration_coupon": calibration_coupon(),
    }
    reports = [export_shape(name, shape) for name, shape in shapes.items()]
    build_documents(shapes)
    print_package = make_print_package(shapes)
    report = {
        "project": PARAMS["project"],
        "freecad_version": ".".join(str(v) for v in App.Version()[:3]),
        "joint_version": J["version"],
        "parts": reports,
        "print_package": print_package,
    }
    (REPORTS_DIR / "cad_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
