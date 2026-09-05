"""Deterministic non-dinosaur input image for image-workflow integration tests.

Blender renderer only: known robot construction is not used as the inferred mesh.
"""
import math
from pathlib import Path
import bpy
from mathutils import Vector

PROJECT=Path(__file__).resolve().parents[1]
OUTPUT=PROJECT/'assets/workflow_tests/blue_robot.png'
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)


def material(name,color,roughness=.35):
    item=bpy.data.materials.new(name);item.diffuse_color=(*color,1);item.use_nodes=True
    shader=item.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(*color,1)
    shader.inputs['Roughness'].default_value=roughness
    return item


blue=material('robot blue',(.03,.3,.72));joint=material('pale joint',(.8,.86,.92));dark=material('eyes',(.015,.025,.05))


def sphere(name,location,radius,mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,radius=radius,location=location)
    obj=bpy.context.object;obj.name=name;obj.data.materials.append(mat)
    for face in obj.data.polygons:face.use_smooth=True
    return obj


def block(name,location,size,mat):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);obj=bpy.context.object;obj.name=name
    obj.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    mod=obj.modifiers.new('Rounded edges','BEVEL');mod.width=.15;mod.segments=5
    obj.modifiers.new('Normals','WEIGHTED_NORMAL');obj.data.materials.append(mat)
    return obj


def rod(name,a,b,radius,mat):
    delta=Vector(b)-Vector(a)
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=radius,depth=delta.length,location=(Vector(a)+Vector(b))/2)
    obj=bpy.context.object;obj.name=name;obj.rotation_euler=delta.to_track_quat('Z','Y').to_euler();obj.data.materials.append(mat)
    for face in obj.data.polygons:face.use_smooth=True


block('body',(0,0,3.45),(1.65,.9,1.8),blue)
sphere('neck',(0,0,4.55),.33,joint)
block('head',(0,0,5.23),(1.45,1.05,1.05),blue)
for side in (-1,1):
    sphere('eye',(side*.3,-.535,5.3),.11,dark)
    shoulder=(side*1.04,0,4.03);elbow=(side*1.53,-.03,3.12)
    sphere('shoulder',shoulder,.36,joint);rod('upper arm',shoulder,elbow,.22,blue)
    sphere('elbow',elbow,.3,joint);rod('forearm',elbow,(side*1.8,-.05,2.45),.22,blue)
    sphere('hand',(side*1.83,-.05,2.33),.3,blue)
    hip=(side*.55,0,2.4);knee=(side*.68,0,1.4);ankle=(side*.75,-.04,.55)
    sphere('hip',hip,.35,joint);rod('thigh',hip,knee,.27,blue)
    sphere('knee',knee,.32,joint);rod('shin',knee,ankle,.25,blue)
    sphere('ankle',ankle,.28,joint);block('foot',(side*.75,-.26,.23),(.78,1.15,.45),blue)

bpy.ops.object.camera_add(location=(8,-15,9));camera=bpy.context.object
camera.rotation_euler=(Vector((0,0,2.9))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.ortho_scale=7.2;bpy.context.scene.camera=camera
for location,power,size in [((-5,-8,10),1300,6),((6,-1,7),900,5),((0,6,8),1100,4)]:
    bpy.ops.object.light_add(type='AREA',location=location);light=bpy.context.object;light.data.energy=power;light.data.shape='DISK';light.data.size=size
    light.rotation_euler=(Vector((0,0,3))-light.location).to_track_quat('-Z','Y').to_euler()
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32
scene.world.color=(.4,.4,.4);scene.render.film_transparent=True
scene.render.resolution_x=768;scene.render.resolution_y=768;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
OUTPUT.parent.mkdir(parents=True,exist_ok=True);scene.render.filepath=str(OUTPUT)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT.with_suffix('.blend')))
bpy.ops.render.render(write_still=True)
