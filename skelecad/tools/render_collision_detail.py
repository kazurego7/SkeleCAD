"""Render two interfering solids translucently with their exact overlap in red."""
import argparse
import sys
from pathlib import Path
import bpy
from mathutils import Vector


def material(name,color,alpha=1.0):
    value=bpy.data.materials.new(name)
    value.diffuse_color=(*color,alpha)
    value.use_nodes=True
    principled=value.node_tree.nodes.get('Principled BSDF')
    principled.inputs['Base Color'].default_value=(*color,1)
    principled.inputs['Roughness'].default_value=.45
    principled.inputs['Alpha'].default_value=alpha
    if alpha<1:
        value.surface_render_method='DITHERED'
    return value


def load_stl(path,name,mat):
    bpy.ops.wm.stl_import(filepath=str(Path(path).resolve()))
    obj=bpy.context.selected_objects[0];obj.name=name
    obj.data.materials.clear();obj.data.materials.append(mat)
    return obj


def look_at(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()


parser=argparse.ArgumentParser()
parser.add_argument('--a',required=True);parser.add_argument('--b',required=True)
parser.add_argument('--overlap',required=True);parser.add_argument('--output',required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
a=load_stl(args.a,'Socket mount A',material('Blue mount',(.08,.42,.95),.28))
b=load_stl(args.b,'Socket mount B',material('Orange mount',(1.0,.48,.06),.28))
overlap=load_stl(args.overlap,'Collision volume',material('Collision red',(1.0,.015,.02),1.0))

corners=[overlap.matrix_world@Vector(corner) for corner in overlap.bound_box]
lo=Vector(tuple(min(v[k] for v in corners) for k in range(3)))
hi=Vector(tuple(max(v[k] for v in corners) for k in range(3)))
center=(lo+hi)*.5;span=max((hi-lo).length,8.0)
camera_data=bpy.data.cameras.new('Camera');camera=bpy.data.objects.new('Camera',camera_data)
bpy.context.collection.objects.link(camera);bpy.context.scene.camera=camera
camera.data.type='ORTHO';camera.data.ortho_scale=span*2.2
camera.location=center+Vector((1.25,-1.6,.9)).normalized()*span*4
look_at(camera,center)

world=bpy.context.scene.world or bpy.data.worlds.new('World');bpy.context.scene.world=world
world.color=(.025,.032,.045)
for name,energy,direction in [('Key',850,(-1.2,-1.8,2.4)),('Fill',500,(2,-.5,1)),('Rim',700,(.5,2,1.5))]:
    data=bpy.data.lights.new(name,'AREA');data.energy=energy;data.size=span*2
    lamp=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(lamp)
    lamp.location=center+Vector(direction).normalized()*span*2;look_at(lamp,center)
scene=bpy.context.scene;scene.render.engine=('BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT')
scene.render.resolution_x=900;scene.render.resolution_y=700;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(Path(args.output).resolve())
scene.view_settings.look='AgX - Medium High Contrast';scene.render.film_transparent=False
bpy.ops.render.render(write_still=True)
