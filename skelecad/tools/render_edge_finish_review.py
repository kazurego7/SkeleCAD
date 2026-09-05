"""Matched geometry-only views of actual cut borders, without shader smoothing."""
import bpy, math
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
import json
params=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
folder=ROOT/params['hybrid_new']['output_directory']/'edge_finish'
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
mat=bpy.data.materials.new('Neutral blue');mat.diffuse_color=(.22,.46,.63,1);mat.roughness=.65
for row,name in enumerate(('arm_left','leg_left')):
    for col,phase in enumerate(('before','after')):
        bpy.ops.wm.stl_import(filepath=str(folder/f'{name}_{phase}.stl'))
        obj=bpy.context.selected_objects[0];obj.data.materials.append(mat)
        bounds=[Vector(v) for v in obj.bound_box]
        lo=Vector(tuple(min(v[i] for v in bounds) for i in range(3)))
        hi=Vector(tuple(max(v[i] for v in bounds) for i in range(3)))
        scale=34/(hi.z-lo.z)
        center=(lo+hi)/2
        obj.scale=(scale,)*3
        obj.location=Vector((-24+48*col,0,24-48*row))-center*scale
for col,label in enumerate(('BEFORE','AFTER')):
    bpy.ops.object.text_add(location=(-36+48*col,-14,46),rotation=(math.pi/2,0,0))
    text=bpy.context.object;text.data.body=label;text.data.size=4
scene=bpy.context.scene
bpy.ops.object.camera_add(location=(0,-160,0));camera=bpy.context.object
camera.rotation_euler=(Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.ortho_scale=108;scene.camera=camera
for loc,power,size in (((-50,-70,70),160000,75),((55,-35,15),70000,60)):
    bpy.ops.object.light_add(type='AREA',location=loc)
    lamp=bpy.context.object;lamp.data.energy=power;lamp.data.shape='DISK';lamp.data.size=size
    lamp.rotation_euler=(-lamp.location).to_track_quat('-Z','Y').to_euler()
scene.world.color=(.18,.18,.18)
scene.render.engine=('BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT')
scene.render.resolution_x=1000;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.render.filepath=str(ROOT/'build/preview/edge_finish_comparison.png')
scene.render.image_settings.file_format='PNG'
bpy.ops.render.render(write_still=True)
