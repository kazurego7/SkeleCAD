"""Render the measured left-ankle interference for design review."""

import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

from sys import path as sys_path

ROOT = Path(__file__).resolve().parents[1]
sys_path.insert(0, str(ROOT / "src"))
from hybrid_context import H, HYBRID  # noqa: E402


def material(name, color, emission=0.0):
    value = bpy.data.materials.new(name)
    value.diffuse_color = color
    value.roughness = 0.62
    value.use_nodes = True
    principled = value.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Alpha"].default_value = color[3]
    if color[3] < 1.0:
        value.surface_render_method = "DITHERED"
    if emission:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Emission Color"].default_value = color
        principled.inputs["Emission Strength"].default_value = emission
    return value


def load_stl(path, name, mat):
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.selected_objects[0]
    obj.name = name
    obj.data.materials.append(mat)
    return obj


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
leg = load_stl(HYBRID / "parts" / "leg_left.stl", "Socket-side leg", material("Leg", (.34, .39, .46, .30)))
foot = load_stl(HYBRID / "parts" / "foot_left.stl", "Ball-side foot", material("Foot", (.14, .43, .78, .30)))
collision = load_stl(HYBRID / "ankle_left_excess_5deg.stl", "Excess interference", material("Interference", (1, .025, .015, 1), 1.2))

center = Vector(H["ankle_center_left_mm"])
foot.matrix_world = Matrix.Translation(center) @ Matrix.Rotation(math.radians(5), 4, "Y") @ Matrix.Translation(-center)

camera_data = bpy.data.cameras.new("Close-up camera")
camera = bpy.data.objects.new("Close-up camera", camera_data)
bpy.context.collection.objects.link(camera)
bpy.context.scene.camera = camera
camera.data.type = "ORTHO"
camera.data.ortho_scale = 19.0
camera.location = center + Vector((19, -27, 15))
camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()

world = bpy.context.scene.world or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.color = (.025, .03, .04)
for location, energy, size in (((8, -10, 28), 1000, 12), ((-24, 6, 15), 650, 10)):
    data = bpy.data.lights.new("Area", "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    lamp = bpy.data.objects.new("Area", data)
    bpy.context.collection.objects.link(lamp)
    lamp.location = Vector(location)
    lamp.rotation_euler = (center - lamp.location).to_track_quat("-Z", "Y").to_euler()

scene = bpy.context.scene
scene.render.engine = ("BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT")
scene.render.resolution_x = 900
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.render.filepath = str(ROOT / "build" / "preview" / "ankle_collision_detail.png")
bpy.ops.render.render(write_still=True)
