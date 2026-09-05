import json
import math
from pathlib import Path

import FreeCAD as App
import MeshPart
import Part

import freecad_project as legacy


ROOT = legacy.ROOT
BUILD = legacy.BUILD
PARTS_DIR = legacy.PARTS_DIR
ASSEMBLY_DIR = legacy.ASSEMBLY_DIR
REPORTS_DIR = legacy.REPORTS_DIR
PRINT_DIR = legacy.PRINT_DIR
PARAMS = legacy.PARAMS
JOINT = PARAMS["joint"]
HINGE = PARAMS["hinge"]
TREX = PARAMS["trex"]


def vector(values):
    return App.Vector(*values)


def direction_between(start, end):
    return vector(end).sub(vector(start))


def fuse_all(shapes):
    shapes = list(shapes)
    if not shapes:
        raise ValueError("No shapes to fuse")
    result = shapes[0].multiFuse(shapes[1:]).removeSplitter() if len(shapes) > 1 else shapes[0]
    if not result.isValid():
        result.fix(0.01, 0.01, 0.1)
    return result


def robust_fuse(shapes):
    """Sequential fuse for dense ornamental bone clusters."""
    shapes = list(shapes)
    if not shapes:
        raise ValueError("No shapes to fuse")
    result = shapes[0]
    for shape in shapes[1:]:
        result = result.fuse(shape)
    result = result.removeSplitter()
    if not result.isValid():
        result.fix(0.01, 0.01, 0.1)
    return result


def capsule(start, end, radius):
    return legacy.capsule_between(start, end, radius)


def tapered_bone(start, end, start_radius, end_radius):
    """Printable tapered tooth/claw with a deliberately blunt end."""
    axis = direction_between(start, end)
    return Part.makeCone(
        start_radius, end_radius, axis.Length, vector(start), axis
    )


def oriented(shape, center, outward):
    copy = shape.copy()
    copy.Placement = App.Placement(
        vector(center), App.Rotation(App.Vector(1, 0, 0), vector(outward))
    )
    return copy


def rounded_socket_local(clearance_mm=None):
    """Constant-wall spherical cup closed by a tangent R1 rolled mouth.

    The capture diameter is independent of the spherical fit clearance.
    Both profile arcs are revolved, so the front does not have a long cone lip.
    """
    cfg=JOINT['socket_profile']
    clearance=JOINT['socket_diameter_mm']-JOINT['ball_diameter_mm'] if clearance_mm is None else clearance_mm
    ri=(JOINT['ball_diameter_mm']+clearance)/2
    edge=cfg['rim_radius_mm'];wall=2*edge;ro=ri+wall;mid=ri+edge
    throat=cfg['retention_diameter_mm']/2;radial=throat+edge
    if wall<PARAMS['printing']['min_wall_mm'] or not 0<throat<JOINT['ball_diameter_mm']/2 or radial>=mid:
        raise ValueError('Invalid shallow socket wall or capture diameter')
    a=math.acos(radial/mid)
    def p(r,t):return App.Vector(r*math.sin(t),r*math.cos(t),0)
    rear=App.Vector(-ro,0,0);back=App.Vector(-ri,0,0);c=p(mid,a)
    front=c+App.Vector(edge,0,0);axis_front=App.Vector(front.x,0,0)
    outer_join=p(ro,a);inner_join=p(ri,a)
    outer_mid=c+App.Vector(edge*math.cos((math.pi/2-a)/2),edge*math.sin((math.pi/2-a)/2),0)
    outer_edges=[Part.Arc(rear,p(ro,(a-math.pi/2)/2),outer_join).toShape(),
                 Part.Arc(outer_join,outer_mid,front).toShape(),Part.makeLine(front,axis_front),Part.makeLine(axis_front,rear)]
    outer=Part.Face(Part.Wire(outer_edges)).revolve(App.Vector(),App.Vector(1,0,0),360)
    exit_point=App.Vector(ro+2,ro+2,0);exit_axis=App.Vector(ro+2,0,0)
    inner_edges=[Part.Arc(back,p(ri,(a-math.pi/2)/2),inner_join).toShape(),
                 Part.Arc(inner_join,c+App.Vector(0,-edge,0),front).toShape(),
                 Part.makeLine(front,exit_point),Part.makeLine(exit_point,exit_axis),Part.makeLine(exit_axis,back)]
    cutter=Part.Face(Part.Wire(inner_edges)).revolve(App.Vector(),App.Vector(1,0,0),360)
    slot=JOINT['relief_slot_mm']
    relief=Part.makeBox(ro+1.5,slot,ro*2+2,App.Vector(-0.25,-slot/2,-ro-1))
    # Round the continuous ring before cutting the flex slit. This avoids
    # split-arc fillets and keeps the rim an analytic surface for later unions.
    negative=cutter
    circumferential=cfg.get('circumferential_relief')
    if circumferential:
        # Axisymmetric envelope of the tilted neck: removes the inner/front
        # rim around its entire circumference, not just four directional slots.
        # The uncut outer wall and spherical fit remain unchanged. Hybrid source
        # anatomy uses separate historical cutters, never this enlarged mouth.
        angle=math.radians(circumferential['angle_deg'])
        if not 0<angle<math.pi/4:
            raise ValueError('Invalid circumferential socket relief angle')
        radius=JOINT['neck_diameter_mm']/2/math.cos(angle)
        length=2*ro
        cone=Part.makeCone(radius,radius+length*math.tan(angle),length,
                           App.Vector(),App.Vector(1,0,0))
        negative=negative.fuse(cone)
    height_trim=cfg.get('height_trim')
    if height_trim:
        # Remove the actual exterior height, not just an internal chamfer.
        # Adjust calibration heights to keep the same spherical aperture at
        # the cut plane while varying the intended cavity clearance.
        nominal_ri=JOINT['socket_diameter_mm']/2
        height=math.sqrt(ri*ri-nominal_ri*nominal_ri+height_trim['nominal_front_height_mm']**2)
        # Build the R1 tangent arc in the meridian and revolve it through 360
        # degrees. Selecting post-cut edges missed half the old rim; OCCT's
        # post-Boolean fillets also produced unreliable subsequent intersections.
        # This analytic sphere/torus profile has neither edge-selection issue.
        radius=height_trim['outer_edge_radius_mm']
        cx=height-radius
        radial=math.sqrt((ro-radius)**2-cx**2)
        angle=math.atan2(cx,radial)
        center=App.Vector(cx,radial,0)
        join=p(ro,angle);front=App.Vector(height,radial,0)
        midpoint=center+App.Vector(radius*math.cos((math.pi/2-angle)/2),radius*math.sin((math.pi/2-angle)/2),0)
        edges=[Part.Arc(rear,p(ro,(angle-math.pi/2)/2),join).toShape(),
               Part.Arc(join,midpoint,front).toShape(),
               Part.makeLine(front,App.Vector(height,0,0)),
               Part.makeLine(App.Vector(height,0,0),rear)]
        outer=Part.Face(Part.Wire(edges)).revolve(App.Vector(),App.Vector(1,0,0),360)
    return outer,negative.fuse(relief).removeSplitter()


def socket_local(clearance_mm=None, legacy_profile=False):
    if JOINT.get('socket_profile',{}).get('type')=='rounded_shallow' and not legacy_profile:
        return rounded_socket_local(clearance_mm)
    ball_r = JOINT["ball_diameter_mm"] / 2
    clearance = (
        JOINT["socket_diameter_mm"] - JOINT["ball_diameter_mm"]
        if clearance_mm is None else clearance_mm
    )
    cavity_r = ball_r + clearance / 2
    outer_r = JOINT["socket_outer_diameter_mm"] / 2
    throat_r = JOINT["throat_diameter_mm"] / 2
    slot = JOINT["relief_slot_mm"]
    outer = Part.makeSphere(outer_r)
    cavity = Part.makeSphere(cavity_r)
    mouth = Part.makeCone(
        throat_r, outer_r - 0.8, outer_r + 1.2,
        App.Vector(0, 0, 0), App.Vector(1, 0, 0)
    )
    relief = Part.makeBox(
        outer_r + 1.5,
        slot,
        outer_r * 2 + 2,
        App.Vector(-0.25, -slot / 2, -outer_r - 1),
    )
    return outer, cavity.fuse(mouth).fuse(relief)


def socket_components(center, mouth_direction, clearance_mm=None):
    outer, cutter = socket_local(clearance_mm)
    return (
        oriented(outer, center, mouth_direction),
        oriented(cutter, center, mouth_direction),
    )


def add_socket(body, center, mouth_direction, clearance_mm=None):
    outer, cutter = socket_components(center, mouth_direction, clearance_mm)
    # Machine the base and cup separately before union, avoiding a repeated
    # cut across coincident mating faces at their interface.
    result = body.cut(cutter).fuse(outer.cut(cutter)).removeSplitter()
    if not result.isValid():
        result.fix(0.01, 0.01, 0.1)
    return result


def ball_stud(center, support_point):
    ball_r = JOINT["ball_diameter_mm"] / 2
    neck_r = JOINT["neck_diameter_mm"] / 2
    return fuse_all([
        Part.makeSphere(ball_r, vector(center)),
        capsule(support_point, center, neck_r),
    ])


def organic_chain(points, radii, joint_scale=1.25):
    """Connected tapered bone chain with enlarged vertebral/end landmarks."""
    segments = []
    for index, (start, end) in enumerate(zip(points, points[1:])):
        segments.append(capsule(start, end, min(radii[index], radii[index + 1])))
    for point, radius in zip(points, radii):
        segments.append(Part.makeSphere(radius * joint_scale, vector(point)))
    return fuse_all(segments)


def upper_skull():
    # Broad, domed braincase and a short deep snout.  The cavities are cut
    # through the mass before raised orbital and cheek arches are added.
    skull_mass = [
        capsule((-82, 0, 85), (-66, 0, 82), 13.5),
        Part.makeSphere(9.5, vector((-89, 0, 85))),
        capsule((-104, 0, 86), (-88, 0, 88.5), 5.6),
        capsule((-105, -5.8, 87.0), (-105, 5.8, 87.0), 3.1),
        capsule((-105, -7.2, 79.2), (-105, 7.2, 79.2), 3.2),
    ]
    body = robust_fuse(skull_mass)
    cutters = [
        Part.makeCylinder(5.7, 40, vector((-79, -20, 85)), App.Vector(0, 1, 0)),
        Part.makeCylinder(4.2, 40, vector((-66, -20, 82)), App.Vector(0, 1, 0)),
        Part.makeCylinder(4.3, 40, vector((-91, -20, 83)), App.Vector(0, 1, 0)),
        Part.makeCylinder(2.8, 30, vector((-101, -15, 85)), App.Vector(0, 1, 0)),
        Part.makeBox(30, 18, 7.0, vector((-106, -9, 69.8))),
    ]
    for cutter in cutters:
        body = body.cut(cutter)
    body = body.removeSplitter()

    skull_arches = []
    for sign in (-1, 1):
        skull_arches.extend([
            organic_chain(
                [(-104, sign * 7.2, 79.2), (-97, sign * 8.4, 80), (-89, sign * 9.3, 79), (-81, sign * 9.2, 78)],
                [3.4, 3.7, 3.8, 3.4], 1.06,
            ),
            organic_chain(
                [(-103, sign * 5.5, 87), (-97, sign * 7.0, 90), (-89, sign * 8.0, 91)],
                [3.1, 3.4, 3.2], 1.06,
            ),
            organic_chain(
                [(-88, sign * 7.8, 90), (-80, sign * 10.3, 94), (-70, sign * 9.2, 89)],
                [2.5, 2.7, 2.5], 1.05,
            ),
            organic_chain(
                [(-89, sign * 9.2, 79), (-80, sign * 10.6, 75), (-70, sign * 9.2, 77)],
                [2.8, 3.1, 2.8], 1.08,
            ),
            capsule((-70, sign * 9.2, 77), (-68, sign * 9.2, 90), 2.6),
            capsule((-97, sign * 8.4, 80), (-90, sign * 8.5, 89), 2.4),
            capsule((-102, sign * 7.0, 80), (-99, sign * 6.4, 87), 2.1),
        ])
    body = robust_fuse([body, *skull_arches])

    teeth = []
    tooth_row = (
        (-103, 4.2), (-99.5, 4.7), (-96, 5.1), (-92.5, 5.5),
        (-89, 5.6), (-85.5, 5.2), (-82, 4.8), (-78.8, 4.2),
    )
    for x, size in tooth_row:
        for sign in (-1, 1):
            teeth.append(tapered_bone(
                (x, sign * 7.0, 78.0), (x + 0.2, sign * 7.0, 78.0 - size),
                1.45, 1.0,
            ))
    body = robust_fuse([body, *teeth])
    body = add_socket(body, (-59, 0, 82), (1, 0, 0))
    # Re-establish the four characteristic side openings after the raised
    # arches and socket shell have been fused into the skull.
    finish_fenestrae = [
        Part.makeCylinder(5.3, 40, vector((-79, -20, 85)), App.Vector(0, 1, 0)),
        Part.makeCylinder(3.8, 40, vector((-92, -20, 83)), App.Vector(0, 1, 0)),
        Part.makeCylinder(3.4, 40, vector((-69.5, -20, 84)), App.Vector(0, 1, 0)),
        Part.makeCylinder(2.2, 32, vector((-101, -16, 85)), App.Vector(0, 1, 0)),
    ]
    for cutter in finish_fenestrae:
        body = body.cut(cutter)
    body = body.removeSplitter()
    # Local under-occipital relief for the real neck shaft at +25 degrees.
    # This does not change the spherical capture or nominal joint clearance.
    body = body.cut(capsule((-55.5, 0, 78.5), (-52.5, 0, 76.5), 2.7)).removeSplitter()

    hinge_center = (-74, 0, 69)
    lug_r = 4.5
    left_lug = Part.makeCylinder(lug_r, 4.0, vector((-74, -11, 69)), App.Vector(0, 1, 0))
    right_lug = Part.makeCylinder(lug_r, 4.0, vector((-74, 7, 69)), App.Vector(0, 1, 0))
    cheek_links = [
        capsule((-70, -9, 76), (-74, -9, 69), 2.8),
        capsule((-70, 9, 76), (-74, 9, 69), 2.8),
    ]
    body = fuse_all([body, left_lug, right_lug, *cheek_links])
    hole = Part.makeCylinder(
        HINGE["hole_diameter_mm"] / 2, 24,
        vector((hinge_center[0], -12, hinge_center[2])), App.Vector(0, 1, 0)
    )
    knuckle_clearance = Part.makeCylinder(
        6.0, 16,
        vector((hinge_center[0], -8, hinge_center[2])), App.Vector(0, 1, 0)
    )
    finished = body.cut(hole.fuse(knuckle_clearance)).removeSplitter()
    # Boolean subtraction can leave a microscopic isolated sliver at the
    # hinge clearance boundary.  It is not a printable feature.
    return max(finished.Solids, key=lambda solid: solid.Volume)


def lower_jaw():
    hinge = (-74, 0, 69)
    knuckle = Part.makeCylinder(4.25, 10, vector((-74, -5, 69)), App.Vector(0, 1, 0))
    jaw_shapes = [knuckle]
    for sign in (-1, 1):
        jaw_shapes.extend([
            capsule((-74, sign * 3.0, 68), (-81, sign * 5.8, 61), 3.0),
            capsule((-81, sign * 5.8, 61), (-94, sign * 7.0, 56), 2.9),
            capsule((-94, sign * 7.0, 56), (-106, sign * 6.4, 58), 2.65),
            capsule((-77, sign * 4.3, 66), (-83, sign * 6.4, 69), 2.4),
            capsule((-83, sign * 6.4, 69), (-97, sign * 6.8, 66.5), 2.2),
        ])
    jaw_shapes.extend([
        capsule((-81, -5.8, 61), (-81, 5.8, 61), 2.6),
        capsule((-106, -6.4, 58), (-106, 6.4, 58), 2.5),
    ])
    jaw = fuse_all(jaw_shapes)
    hole = Part.makeCylinder(
        HINGE["hole_diameter_mm"] / 2, 16,
        vector((hinge[0], -8, hinge[2])), App.Vector(0, 1, 0)
    )
    jaw = jaw.cut(hole).removeSplitter()
    lower_teeth = []
    for x, z, size in ((-103, 59.2, 3.7), (-99.5, 58.3, 4.2), (-96, 57.0, 4.0), (-92.5, 57.7, 4.9), (-89, 58.4, 4.7), (-85.5, 59.4, 4.3), (-82, 60.8, 3.8)):
        for sign in (-1, 1):
            lower_teeth.append(tapered_bone(
                (x, sign * 6.4, z), (x - 0.1, sign * 6.4, z + size),
                1.35, 1.0,
            ))
    return fuse_all([jaw, *lower_teeth])


def hinge_pin():
    pin_r = HINGE["pin_diameter_mm"] / 2
    shaft = Part.makeCylinder(pin_r, 24, vector((-74, -12, 69)), App.Vector(0, 1, 0))
    head = Part.makeCylinder(2.7, 2.2, vector((-74, -14.2, 69)), App.Vector(0, 1, 0))
    return shaft.fuse(head).removeSplitter()


def torso_front():
    spine_points = [
        (-48 + index * 6.4, 0, 81 - index * 0.55)
        for index in range(8)
    ]
    spine_radii = [3.2, 3.5, 3.7, 3.8, 3.8, 3.7, 3.5, 3.2]
    spine = organic_chain(spine_points, spine_radii, 1.35)
    neural_spines = [
        capsule((x, 0, z + 1.0), (x + 0.7, 0, z + 7.0), 1.45)
        for x, _, z in spine_points
    ]
    spine = robust_fuse([spine, *neural_spines])
    ribs = []
    rib_bottoms = []
    rib_count = int(TREX["rib_count"])
    rib_radius = TREX["rib_diameter_mm"] / 2
    for index in range(rib_count):
        x = -43 + index * 6.0
        profile = math.sin((index + 1) / (rib_count + 1) * math.pi)
        width = 14.5 + profile * 4.8
        depth = 23.5 + profile * 5.0
        top_z = 80.6 - index * 0.55
        for sign in (-1, 1):
            points = [
                (x, sign * 1.6, top_z),
                (x - 1.8, sign * width * 0.45, top_z - 3.0),
                (x - 0.5, sign * width * 0.82, top_z - 9.0),
                (x + 2.5, sign * width, top_z - 16.0),
                (x + 6.0, sign * width * 0.78, top_z - 22.0),
                (x + 7.8, sign * 4.0, top_z - depth),
            ]
            ribs.append(organic_chain(
                points, [rib_radius] * len(points), 1.02,
            ))
        rib_bottom = (x + 7.8, 0, top_z - depth)
        ribs.append(capsule(
            (rib_bottom[0], -4.0, rib_bottom[2]),
            (rib_bottom[0], 4.0, rib_bottom[2]),
            rib_radius,
        ))
        rib_bottoms.append(rib_bottom)
    sternum = organic_chain(rib_bottoms, [2.1] * len(rib_bottoms), 1.08)
    neck_ball = ball_stud((-59, 0, 82), (-50, 0, 82))
    neck_transition = capsule((-50, 0, 82), (-48, 0, 81), JOINT["neck_diameter_mm"] / 2)
    cervical_chain = organic_chain(
        [(-49, 0, 81.5), (-45.5, 0, 80.2), (-42, 0, 79.7), (-38.5, 0, 79.4)],
        [2.7, 3.1, 3.4, 3.6], 1.32,
    )
    cervical_spines = [
        capsule((-46, 0, 81.5), (-45, 0, 86), 1.3),
        capsule((-41.5, 0, 81), (-40.5, 0, 86), 1.35),
    ]
    shoulder_girdle = []
    arms = []
    for sign in (-1, 1):
        shoulder_girdle.extend([
            organic_chain(
                [(-43, sign * 3, 80), (-39, sign * 10, 75), (-35, sign * 15, 66)],
                [3.0, 3.1, 2.7], 1.18,
            ),
            capsule((-39, sign * 10, 75), (-32, sign * 12, 59), 2.35),
            capsule((-32, sign * 12, 59), (-27, sign * 4, 54), 2.1),
        ])
        shoulder = (-40, sign * 13.5, 74)
        elbow = (-45, sign * 16, 64)
        wrist = (-52, sign * 16.5, 59)
        arms.extend([
            organic_chain([shoulder, elbow], [2.8, 3.0], 1.2),
            organic_chain([elbow, wrist], [2.35, 2.1], 1.2),
            Part.makeSphere(2.6, vector(wrist)),
            tapered_bone(wrist, (-59, sign * 18.0, 58.5), 1.5, 1.0),
            tapered_bone(wrist, (-58, sign * 14.0, 56.3), 1.5, 1.0),
        ])
    socket_bridge = capsule((-3, 0, 76), (2, 0, 75), 2.8)
    body = robust_fuse([
        spine, sternum, neck_ball, neck_transition, cervical_chain, socket_bridge,
        *cervical_spines, *ribs, *shoulder_girdle, *arms,
    ])
    return add_socket(body, (6, 0, 75), (1, 0, 0))


def torso_rear():
    front_ball = ball_stud((6, 0, 75), (19, 0, 75))
    transition = capsule((19, 0, 75), (22, 0, 74), JOINT["neck_diameter_mm"] / 2)
    spine = organic_chain(
        [(22, 0, 74), (28, 0, 73.5), (34, 0, 72.5)],
        [3.8, 4.2, 3.8], 1.38,
    )
    pelvis = [
        capsule((17, -6.0, 72.5), (17, 6.0, 72.5), 4.0),
        Part.makeSphere(5.0, vector((20, 0, 73))),
        capsule((23, 0, 75), (24, 0, 82), 1.6),
        capsule((29, 0, 74), (30, 0, 81), 1.6),
        capsule((35, 0, 72), (36, 0, 78), 1.45),
    ]
    hip_shapes = []
    for sign in (-1, 1):
        hip_shapes.extend([
            organic_chain(
                [(17, sign * 4.5, 73), (27, sign * 9.0, 76), (35, sign * 10.0, 71)],
                [4.2, 4.6, 4.0], 1.16,
            ),
            organic_chain(
                [(35, sign * 10.0, 71), (30, sign * 9.2, 61), (27, sign * 8.0, 54)],
                [3.7, 3.5, 3.2], 1.12,
            ),
            organic_chain(
                [(27, sign * 8.0, 54), (20, sign * 7.0, 61), (17, sign * 5.0, 70)],
                [3.2, 3.35, 3.4], 1.12,
            ),
            capsule((22, sign * 7.8, 66), (23, sign * 9.0, 65), 2.9),
            ball_stud((23, sign * 17, 65), (23, sign * 9.0, 65)),
        ])
    tail_bridge = capsule((34, 0, 72.5), (38, 0, 72), 3.2)
    body = robust_fuse([front_ball, transition, spine, tail_bridge, *pelvis, *hip_shapes])
    return add_socket(body, (41, 0, 72), (1, 0, 0))


def leg(side):
    sign = 1 if side == "left" else -1
    hip = (23, sign * 17, 65)
    knee = (8, sign * 25, 39)
    ankle = (23, sign * 22, 12)
    cup_outer, cup_cutter = socket_components(hip, (0, -sign, 0))
    thigh_root = capsule((23, sign * 21.8, 60), (20, sign * 23.5, 53), 3.6)
    thigh = organic_chain(
        [(20, sign * 23.5, 53), (14, sign * 25, 47), knee],
        [4.4, 4.9, 4.8], 1.26,
    )
    shin = organic_chain(
        [knee, (15, sign * 24, 27), ankle],
        [4.5, 4.2, 4.7], 1.18,
    )
    fibula = capsule((10, sign * 28, 37), (24, sign * 25, 14), 2.25)
    knee_bulb = Part.makeSphere(6.0, vector(knee))
    ankle_bulb = Part.makeSphere(5.2, vector(ankle))
    heel_point = (16, sign * 23, 6.0)
    heel = organic_chain([ankle, heel_point], [3.9, 3.7], 1.2)
    toes = []
    for y_delta in (-5.0, 0.0, 5.0):
        toe_y = sign * 23 + y_delta
        knuckle = (6 - abs(y_delta) * 0.2, toe_y, 4.6)
        tip = (-4 + abs(y_delta) * 0.4, toe_y + y_delta * 0.2, 3.1)
        claw_tip = (-8 + abs(y_delta) * 0.55, toe_y + y_delta * 0.26, 2.6)
        toes.extend([
            capsule((16, sign * 23 + y_delta * 0.28, 6.0), knuckle, 2.6),
            Part.makeSphere(3.0, vector(knuckle)),
            capsule(knuckle, tip, 2.1),
            tapered_bone(tip, claw_tip, 1.75, 1.0),
        ])
    body = robust_fuse([
        cup_outer, thigh_root, thigh, shin, fibula,
        knee_bulb, ankle_bulb, heel, *toes,
    ])
    result = body.cut(cup_cutter).removeSplitter()
    if not result.isValid():
        result.fix(0.01, 0.01, 0.1)
    return result


def tail_front():
    ball = ball_stud((41, 0, 72), (49, 0, 72))
    chain = organic_chain(
        [(53, 0, 71.5), (59, 0, 70.8), (65, 0, 69.8), (71, 0, 68.6), (77, 0, 67.3), (81.5, 0, 66.2)],
        [4.2, 4.6, 4.5, 4.2, 3.8, 3.35], 1.26,
    )
    chevrons = [
        capsule((58, 0, 69), (60, 0, 62), 1.55),
        capsule((65, 0, 68), (67, 0, 61.5), 1.45),
        capsule((72, 0, 66.8), (74, 0, 61), 1.35),
        capsule((78, 0, 65.8), (80, 0, 61), 1.2),
    ]
    processes = []
    for x, z, scale in ((58, 70.8, 1.0), (65, 69.7, 0.9), (72, 68.4, 0.8), (78, 67.0, 0.7)):
        processes.extend([
            capsule((x, 0, z + 1), (x + 0.8, 0, z + 6 * scale), 1.3),
            capsule((x, 0, z), (x, 4.2 * scale, z - 0.6), 1.15),
            capsule((x, 0, z), (x, -4.2 * scale, z - 0.6), 1.15),
        ])
    body = robust_fuse([
        ball,
        capsule((49, 0, 72), (53, 0, 71.5), JOINT["neck_diameter_mm"] / 2),
        chain, *chevrons, *processes,
    ])
    return add_socket(body, (87, 0, 65), (1, 0, 0))


def tail_rear():
    chain = organic_chain(
        [(97, 0, 64.2), (101, 0, 63.3), (105, 0, 62.1), (109, 0, 60.6), (112.5, 0, 58.7), (115.5, 0, 56.5), (118, 0, 54)],
        [3.0, 3.2, 3.0, 2.7, 2.35, 1.9, 1.35], 1.25,
    )
    processes = []
    for x, z, scale in ((101, 63.2, 0.65), (106, 61.7, 0.55), (111, 59.6, 0.45)):
        processes.extend([
            capsule((x, 0, z), (x + 0.6, 0, z + 4.5 * scale), 1.05),
            capsule((x, 0, z - 0.5), (x + 1.0, 0, z - 4.2 * scale), 1.0),
        ])
    return robust_fuse([
        ball_stud((87, 0, 65), (95, 0, 65)),
        capsule((95, 0, 65), (97, 0, 64.2), JOINT["neck_diameter_mm"] / 2),
        chain,
        *processes,
    ])


def calibration_socket_strip():
    clearances = JOINT["calibration_diametral_clearances_mm"]
    body = Part.makeBox(72, 24, 3, vector((0, 0, 0)))
    cutters = []
    for index, clearance in enumerate(clearances):
        center = (12 + index * 24, 12, 7.0)
        outer, cutter = socket_components(center, (0, 0, 1), clearance)
        body = body.fuse(outer)
        cutters.append(cutter)
        for marker in range(index + 1):
            dot = Part.makeCylinder(
                1.2, 1.0,
                vector((center[0] + (marker - index / 2) * 3.2, 3.0, 3.0)),
                App.Vector(0, 0, 1),
            )
            body = body.fuse(dot)
    body = body.cut(fuse_all(cutters)).removeSplitter()
    if not body.isValid():
        body.fix(0.01, 0.01, 0.1)
    return body


def ball_test_key():
    ball = Part.makeSphere(JOINT["ball_diameter_mm"] / 2, vector((0, 0, 0)))
    handle = capsule((0, 0, 0), (22, 0, 0), 2.8)
    grip = capsule((22, -6, 0), (22, 6, 0), 3.2)
    return fuse_all([ball, handle, grip])


def ball_connector():
    """Reusable male connector only: nominal ball with a short straight stem."""
    ball_r = JOINT["ball_diameter_mm"] / 2
    neck_r = JOINT["neck_diameter_mm"] / 2
    overlap = min(0.5, neck_r * 0.25)
    stem_start = ball_r - overlap
    stem_length = JOINT["stud_reach_mm"] + overlap
    ball = Part.makeSphere(ball_r, vector((0, 0, 0)))
    stem = Part.makeCylinder(
        neck_r, stem_length, vector((stem_start, 0, 0)), App.Vector(1, 0, 0)
    )
    return fuse_all([ball, stem])


def ball_stud_specimen():
    ball = Part.makeSphere(JOINT["ball_diameter_mm"] / 2, vector((0, 0, 0)))
    neck = Part.makeCylinder(
        JOINT["neck_diameter_mm"] / 2, 9.0,
        vector((0, 0, 0)), App.Vector(1, 0, 0)
    )
    base = Part.makeBox(6.0, 12.0, 12.0, vector((8.0, -6.0, -6.0)))
    return fuse_all([ball, neck, base])


def bed_oriented(shape):
    """Choose a simple orthogonal orientation with the smallest print height."""
    candidates = []
    for axis in (None, (1, 0, 0), (0, 1, 0)):
        candidate = shape.copy()
        label = "original"
        if axis is not None:
            candidate.rotate(App.Vector(0, 0, 0), App.Vector(*axis), 90)
            label = "rotate_x_90" if axis[0] else "rotate_y_90"
        candidates.append((candidate.BoundBox.ZLength, candidate, label))
    _, result, label = min(candidates, key=lambda item: item[0])
    # Use the wider bed axis for the longest footprint dimension.
    if result.BoundBox.YLength > result.BoundBox.XLength:
        result.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 90)
        label += "+rotate_z_90"
    return result, label


def make_full_print_plate(local_shapes):
    names = [
        "skull_upper", "jaw_lower", "hinge_pin_v2", "torso_front", "torso_rear",
        "leg_left", "leg_right", "tail_front", "tail_rear",
    ]
    gap = 6.0
    bed_limit_x = 240.0
    cursor_x = gap
    cursor_y = gap
    row_depth = 0.0
    placed = []
    placements = []
    for name in names:
        oriented_shape, orientation = bed_oriented(local_shapes[name])
        box = oriented_shape.BoundBox
        width = box.XLength
        depth = box.YLength
        if cursor_x + width + gap > bed_limit_x:
            cursor_x = gap
            cursor_y += row_depth + gap
            row_depth = 0.0
        oriented_shape.translate(App.Vector(
            cursor_x - box.XMin,
            cursor_y - box.YMin,
            -box.ZMin,
        ))
        placed.append(oriented_shape)
        placements.append({
            "part": name,
            "orientation": orientation,
            "x_mm": cursor_x,
            "y_mm": cursor_y,
            "width_mm": width,
            "depth_mm": depth,
            "height_mm": oriented_shape.BoundBox.ZLength,
        })
        cursor_x += width + gap
        row_depth = max(row_depth, depth)

    package = Part.makeCompound(placed)
    mesh = MeshPart.meshFromShape(
        Shape=package,
        LinearDeflection=PARAMS["printing"]["linear_deflection_mm"],
        AngularDeflection=PARAMS["printing"]["angular_deflection_rad"],
        Relative=False,
    )
    mesh.write(str(PRINT_DIR / "trex_full_print_plate.3mf"))
    return {
        "file": "build/print/trex_full_print_plate.3mf",
        "contents": names,
        "placements": placements,
        "facets": mesh.CountFacets,
        "bounds_mm": {
            "x": package.BoundBox.XLength,
            "y": package.BoundBox.YLength,
            "z": package.BoundBox.ZLength,
        },
        "bed_limit_mm": [256, 256],
        "note": "Low-profile orthogonal layout; slicer support choice still depends on printer and material",
    }


def normalize(shape):
    box = shape.BoundBox
    origin = App.Vector(
        (box.XMin + box.XMax) / 2,
        (box.YMin + box.YMax) / 2,
        (box.ZMin + box.ZMax) / 2,
    )
    local = shape.copy()
    local.translate(origin.negative())
    return local, origin


def place_local(shape, origin):
    copy = shape.copy()
    copy.translate(origin)
    return copy


def make_print_package(local_shapes):
    strip = local_shapes["joint_calibration_v2"].copy()
    key = local_shapes["ball_test_key_v2"].copy()
    strip.translate(App.Vector(38, 14, -strip.BoundBox.ZMin))
    key.translate(App.Vector(88, 14, -key.BoundBox.ZMin))
    package = Part.makeCompound([strip, key])
    mesh = MeshPart.meshFromShape(
        Shape=package,
        LinearDeflection=PARAMS["printing"]["joint_linear_deflection_mm"],
        AngularDeflection=PARAMS["printing"]["joint_angular_deflection_rad"],
        Relative=False,
    )
    mesh.write(str(PRINT_DIR / "starter_fit_kit.3mf"))
    mesh.write(str(PRINT_DIR / "starter_fit_kit.stl"))
    starter = {
        "file": "build/print/starter_fit_kit.3mf",
        "contents": ["joint_calibration_v2", "ball_test_key_v2"],
        "calibration_map_left_to_right_mm": JOINT["calibration_diametral_clearances_mm"],
        "marker_map": "one/two/three raised dots = 0.4/0.6/0.8 mm diametral clearance",
        "facets": mesh.CountFacets,
        "bounds_mm": {
            "x": package.BoundBox.XLength,
            "y": package.BoundBox.YLength,
            "z": package.BoundBox.ZLength,
        },
    }
    return {"starter_fit_kit": starter, "full_print_plate": make_full_print_plate(local_shapes)}


def build_documents(global_parts, local_parts, origins):
    parts_doc = App.newDocument("SkeleCAD_Parts")
    for name, shape in local_parts.items():
        legacy.add_feature(parts_doc, name, name.replace("_", " ").title(), shape, (0.88, 0.84, 0.70))
    parts_doc.recompute()
    parts_doc.saveAs(str(BUILD / "SkeleCAD_Parts.FCStd"))

    assembly_names = [
        "skull_upper", "jaw_lower", "hinge_pin_v2", "torso_front", "torso_rear",
        "leg_left", "leg_right", "tail_front", "tail_rear",
    ]
    colors = {
        "hinge_pin_v2": (0.92, 0.34, 0.20),
        "torso_rear": (0.78, 0.72, 0.57),
    }
    posed_parts = {name: global_parts[name].copy() for name in assembly_names}
    # Present the heavy skull in a slightly lowered, forward-driving pose.
    for name in ("skull_upper", "jaw_lower", "hinge_pin_v2"):
        posed_parts[name].rotate(
            App.Vector(-59, 0, 82), App.Vector(0, 1, 0), -5
        )
    posed_parts["leg_left"].rotate(
        App.Vector(23, 17, 65), App.Vector(0, 1, 0), 8
    )
    posed_parts["leg_right"].rotate(
        App.Vector(23, -17, 65), App.Vector(0, 1, 0), -8
    )
    instances = [
        (name, posed_parts[name], colors.get(name, (0.88, 0.84, 0.70)))
        for name in assembly_names
    ]
    collisions = []
    for index, (name_a, shape_a, _) in enumerate(instances):
        for name_b, shape_b, _ in instances[index + 1:]:
            if shape_a.BoundBox.isInside(shape_b.BoundBox) or shape_b.BoundBox.isInside(shape_a.BoundBox):
                pass
            boxes_overlap = not (
                shape_a.BoundBox.XMax < shape_b.BoundBox.XMin or
                shape_b.BoundBox.XMax < shape_a.BoundBox.XMin or
                shape_a.BoundBox.YMax < shape_b.BoundBox.YMin or
                shape_b.BoundBox.YMax < shape_a.BoundBox.YMin or
                shape_a.BoundBox.ZMax < shape_b.BoundBox.ZMin or
                shape_b.BoundBox.ZMax < shape_a.BoundBox.ZMin
            )
            if not boxes_overlap:
                continue
            volume = shape_a.common(shape_b).Volume
            if volume > 0.01:
                collisions.append({"a": name_a, "b": name_b, "overlap_volume_mm3": volume})

    assembly_doc = App.newDocument("SkeleCAD_Assembly")
    assembly_shapes = []
    for name, posed, color in instances:
        legacy.add_feature(assembly_doc, name, name.replace("_", " ").title(), posed, color)
        assembly_shapes.append(posed)
    compound = Part.makeCompound(assembly_shapes)
    assembly_doc.recompute()
    assembly_doc.saveAs(str(ASSEMBLY_DIR / "SkeleCAD_Assembly.FCStd"))
    export_obj = assembly_doc.addObject("Part::Feature", "AssemblyExport")
    export_obj.Shape = compound
    if export_obj.ViewObject is not None:
        export_obj.ViewObject.Visibility = False
    Part.export([export_obj], str(ASSEMBLY_DIR / "SkeleCAD_Assembly.step"))
    assembly_doc.saveAs(str(ASSEMBLY_DIR / "SkeleCAD_Assembly.FCStd"))
    legacy.render_assembly_svg(instances, BUILD / "preview" / "assembly.svg")
    legacy.render_orthographic_svg(instances, BUILD / "preview" / "orthographic.svg")

    report = {
        "instances": assembly_names,
        "instance_count": len(assembly_names),
        "bounds_mm": {
            "x": compound.BoundBox.XLength,
            "y": compound.BoundBox.YLength,
            "z": compound.BoundBox.ZLength,
        },
        "review_image": "build/preview/assembly.svg",
        "collision_count": len(collisions),
        "collisions": collisions,
        "note": "Nine-piece T. rex in a lowered-head walking pose; ball joints at neck, torso, hips and tail; pin hinge at jaw",
    }
    (REPORTS_DIR / "assembly_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    if collisions:
        raise RuntimeError(f"Assembly contains {len(collisions)} volumetric collisions")
    return parts_doc, assembly_doc


def joint_report(global_parts):
    ball_d = JOINT["ball_diameter_mm"]
    socket_d = JOINT["socket_diameter_mm"]
    outer_d = JOINT["socket_outer_diameter_mm"]
    throat_d = JOINT.get('socket_profile',{}).get('retention_diameter_mm',JOINT["throat_diameter_mm"])
    connections = [
        ("neck", "skull_upper", "torso_front"),
        ("torso", "torso_front", "torso_rear"),
        ("left_hip", "torso_rear", "leg_left"),
        ("right_hip", "torso_rear", "leg_right"),
        ("tail_root", "torso_rear", "tail_front"),
        ("tail_mid", "tail_front", "tail_rear"),
    ]
    results = []
    for name, socket_part, ball_part in connections:
        results.append({
            "name": name,
            "socket_part": socket_part,
            "ball_part": ball_part,
            "assembled_overlap_volume_mm3": global_parts[socket_part].common(global_parts[ball_part]).Volume,
        })
    report = {
        "joint_version": JOINT["version"],
        "type": JOINT["type"],
        "ball_diameter_mm": ball_d,
        "socket_diameter_mm": socket_d,
        "diametral_clearance_mm": socket_d - ball_d,
        "radial_wall_mm": (outer_d - socket_d) / 2,
        "radial_capture_undercut_mm": (ball_d - throat_d) / 2,
        "neck_to_throat_radial_clearance_mm": (throat_d - JOINT["neck_diameter_mm"]) / 2,
        "relief_slot_mm": JOINT["relief_slot_mm"],
        "jaw_hinge": {
            "pin_diameter_mm": HINGE["pin_diameter_mm"],
            "hole_diameter_mm": HINGE["hole_diameter_mm"],
            "diametral_clearance_mm": HINGE["hole_diameter_mm"] - HINGE["pin_diameter_mm"],
        },
        "connections": results,
        "passed": (
            socket_d > ball_d and
            (outer_d - socket_d) / 2 >= PARAMS["printing"]["min_wall_mm"] and
            throat_d < ball_d and
            JOINT["neck_diameter_mm"] < throat_d and
            all(item["assembled_overlap_volume_mm3"] <= 0.01 for item in results)
        ),
    }
    (REPORTS_DIR / "joint_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    if not report["passed"]:
        raise RuntimeError("Ball/socket joint validation failed")
    return report


def main():
    for directory in (PARTS_DIR, ASSEMBLY_DIR, REPORTS_DIR, PRINT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.step", "*.stl", "*.3mf"):
        for stale in PARTS_DIR.glob(pattern):
            stale.unlink()

    global_parts = {
        "skull_upper": upper_skull(),
        "jaw_lower": lower_jaw(),
        "hinge_pin_v2": hinge_pin(),
        "torso_front": torso_front(),
        "torso_rear": torso_rear(),
        "leg_left": leg("left"),
        "leg_right": leg("right"),
        "tail_front": tail_front(),
        "tail_rear": tail_rear(),
        "joint_calibration_v2": calibration_socket_strip(),
        "ball_test_key_v2": ball_test_key(),
        "ball_connector_v2": ball_connector(),
        "ball_stud_specimen_v2": ball_stud_specimen(),
        "bone_long": legacy.straight_bone(PARAMS["bones"]["long_length_mm"]),
    }
    local_parts = {}
    origins = {}
    for name, shape in global_parts.items():
        local_parts[name], origins[name] = normalize(shape)

    reports = []
    for name, shape in local_parts.items():
        info = legacy.export_shape(name, shape)
        info["role"] = "analysis_specimen" if name in ("bone_long", "ball_stud_specimen_v2") else (
            "connector" if name == "ball_connector_v2" else (
                "calibration" if name in ("joint_calibration_v2", "ball_test_key_v2") else "assembly"
            )
        )
        reports.append(info)

    build_documents(global_parts, local_parts, origins)
    joints = joint_report(global_parts)
    print_package = make_print_package(local_parts)
    report = {
        "project": PARAMS["project"],
        "freecad_version": ".".join(str(v) for v in App.Version()[:3]),
        "joint_version": JOINT["version"],
        "joint_type": JOINT["type"],
        "parts": reports,
        "print_package": print_package,
        "joint_summary": joints,
    }
    (REPORTS_DIR / "cad_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
