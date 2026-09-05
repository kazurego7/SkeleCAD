"""Render a lightweight review image of an image-to-3D GLB in Blender."""

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--view", choices=("hero", "side", "front", "top"), default="hero")
script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
args = parser.parse_args(script_args)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
input_path = Path(args.input).resolve()
if input_path.suffix.lower() == ".stl":
    bpy.ops.wm.stl_import(filepath=str(input_path))
else:
    bpy.ops.import_scene.gltf(filepath=str(input_path))
meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
if not meshes:
    raise RuntimeError("GLB contains no mesh objects")

for obj in meshes:
    obj.select_set(True)
    obj.data.materials.clear()

bone = bpy.data.materials.new("Warm bone")
bone.diffuse_color = (0.60, 0.43, 0.25, 1.0)
bone.metallic = 0.0
bone.roughness = 0.62
for obj in meshes:
    obj.data.materials.append(bone)

corners = []
for obj in meshes:
    corners.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
lo = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
hi = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
center = (lo + hi) * 0.5
size = hi - lo

camera_data = bpy.data.cameras.new("Review camera")
camera = bpy.data.objects.new("Review camera", camera_data)
bpy.context.collection.objects.link(camera)
bpy.context.scene.camera = camera
camera.data.type = "ORTHO"
camera.data.ortho_scale = max(size.x, size.y, size.z) * 1.34
directions = {
    "hero": Vector((1.35, -1.75, 0.82)),
    "side": Vector((0.0, -1.0, 0.06)),
    "front": Vector((-1.0, 0.0, 0.06)),
    "top": Vector((0.0, -0.06, 1.0)),
}
direction = directions[args.view].normalized()
camera.location = center + direction * max(size.x, size.y, size.z) * 3.0
look_at(camera, center)

world = bpy.context.scene.world or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.color = (0.92, 0.92, 0.92)

for name, energy, direction in (
    ("Key", 1100, (-1.6, -2.2, 2.8)),
    ("Fill", 700, (2.4, -0.8, 1.4)),
    ("Rim", 900, (0.8, 2.5, 2.0)),
):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy * (max(size) / 2.0) ** 2
    data.shape = "DISK"
    data.size = max(size) * 1.6
    lamp = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(lamp)
    lamp.location = center + Vector(direction) * max(size)
    look_at(lamp, center)

scene = bpy.context.scene
scene.render.engine = ("BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT")
scene.render.resolution_x = 768
scene.render.resolution_y = 768
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.render.filepath = str(Path(args.output).resolve())
scene.view_settings.look = "AgX - Medium High Contrast"
scene.render.image_settings.color_mode = "RGB"
bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.output).with_suffix(".blend").resolve()))
bpy.ops.render.render(write_still=True)
