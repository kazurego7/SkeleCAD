"""Native Bambu calibration plate: named objects, no old meshes, supports ON."""
import copy,hashlib,json,sys,uuid,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
import trimesh
from bambu_settings import native_settings,BAMBU,PARAMS,ROOT
from print_package_audit import set_meta
from print_package_audit import NS,PNS,arrays

C=PARAMS['joint_retention_trial'];BASE=ROOT/C['output_directory']
def main(names=None,title='Retention R1 - 5 patterns',profile_name='SkeleCAD Retention R1 0.12 Support ON'):
    for key in ('executable','library'):
        assert hashlib.sha256(Path(BAMBU[key]).read_bytes()).hexdigest()==BAMBU[key+'_sha256']
    from bambu_project_schema import empty_project
    root,original_obj,original_item,original_md,original_model,payload=empty_project()
    md=ET.Element('config')
    resources=root.find(NS+'resources');resources.clear();build=root.find(NS+'build');build.clear();md.clear()
    rel_ns='http://schemas.openxmlformats.org/package/2006/relationships'
    rel=ET.Element('Relationships',xmlns=rel_ns)
    plate=ET.SubElement(md,'plate')
    for k,v in {'plater_id':'1','plater_name':title,'locked':'false','filament_map_mode':'Auto For Flush'}.items():set_meta(plate,k,v)
    if names is None:
        names=[f'socket_{i}_{side}' for i in (1,2,3) for side in ('lower','upper')]+['locking_key']*6+['ball_key']
        names += [v['label']+suffix for v in C['deep_c4']['variants'] for suffix in ('_socket','_ball_key')]
    records=[];objects=[];counts={}
    for i,name in enumerate(names):
        counts[name]=counts.get(name,0)+1
        label=name+(f'_{counts[name]}' if name=='locking_key' else '')
        source=BASE/'parts'/f'{name}.3mf';stl=BASE/'parts'/f'{name}.stl'
        mesh=trimesh.load_mesh(stl)
        assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0 and len(mesh.split())==1,name
        with zipfile.ZipFile(source) as z:
            srcxml=z.read('3D/3dmodel.model');srcmesh=ET.fromstring(srcxml).find('.//'+NS+'mesh')
        vertices,faces=arrays(srcxml);offset=(vertices.min(0)+vertices.max(0))/2
        R=np.eye(3)
        if name.endswith('_upper'):R=np.diag([1,-1,-1])
        elif name.endswith('_socket'):R=np.array([[0,0,1],[0,1,0],[-1,0,0]])
        elif name.endswith('ball_key'):R=np.array([[0,0,-1],[0,1,0],[1,0,0]])
        # Row-vector rotations; cavity upwards, ball upwards, broad rails/handles down.
        oriented=(vertices-offset)@R;lo=oriented.min(0);hi=oriented.max(0)
        mesh_id=str(2*i+1);oid=str(2*i+2);path=f'3D/Objects/Trial_{i+1}.model'
        obj=copy.deepcopy(original_obj);obj.set('id',oid);obj.set(PNS+'UUID',str(uuid.uuid4()))
        component=obj.find(NS+'components/'+NS+'component');component.set(PNS+'path','/'+path);component.set(PNS+'UUID',str(uuid.uuid4()));component.set('objectid',mesh_id)
        resources.append(obj)
        node=copy.deepcopy(original_model);container=node.find('.//'+NS+'object');container.remove(container.find(NS+'mesh'))
        container.set('id',mesh_id);container.set(PNS+'UUID',str(uuid.uuid4()))
        newmesh=copy.deepcopy(srcmesh)
        for v,xyz in zip(newmesh.find(NS+'vertices'),vertices-offset):
            for k,val in zip('xyz',xyz):v.set(k,format(val,'.12g'))
        container.append(newmesh);payload[path]=ET.tostring(node,encoding='utf-8',xml_declaration=True)
        ET.SubElement(rel,'Relationship',Target='/'+path,Id=f'rel-{i+1}',Type='http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel')
        item=copy.deepcopy(original_item);item.set('objectid',oid);item.set(PNS+'UUID',str(uuid.uuid4()));build.append(item)
        objmd=copy.deepcopy(original_md);objmd.set('id',oid);set_meta(objmd,'name',label);partmd=objmd.find('part');partmd.set('id',mesh_id);set_meta(partmd,'name',label);set_meta(partmd,'source_file',source.name)
        for k,val in zip('xyz',offset):set_meta(partmd,'source_offset_'+k,format(val,'.15g'))
        md.insert(len(md)-1,objmd)
        inst=ET.SubElement(plate,'model_instance')
        for k,val in {'object_id':oid,'instance_id':'0','identify_id':oid}.items():set_meta(inst,k,val)
        objects.append((item,label,R,lo,hi))
        records.append({'label':label,'source':str(source.relative_to(ROOT)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'stl_watertight':True,'stl_winding':True,'solids':1,'vertices':len(vertices),'triangles':len(faces)})
    cfg=PARAMS['printing']['production_profile'];margin=cfg['plate_margin_mm'];gap=cfg['object_gap_mm'];side=cfg['plate_width_mm']
    x=y=margin;depth=0;bounds=[]
    for item,label,R,lo,hi in sorted(objects,key=lambda o:-(o[4]-o[3])[1]):
        size=hi-lo
        if x+size[0]>side-margin:x=margin;y+=depth+gap;depth=0
        assert y+size[1]<side-margin,(label,'plate overflow')
        shift=np.array([x,y,0])-lo
        item.set('transform',' '.join(format(v,'.12g') for v in np.r_[R.ravel(),shift]))
        bounds.append({'name':label,'min':(lo+shift).tolist(),'max':(hi+shift).tolist()})
        x+=size[0]+gap;depth=max(depth,size[1])
    settings=native_settings()
    support_top_z=C.get('print_support_top_z_distance_mm',C['print_layer_height_mm'])
    support_xy=C.get('print_support_object_xy_distance_mm',settings['support_object_xy_distance'])
    settings.update({'layer_height':str(C['print_layer_height_mm']),'support_top_z_distance':str(support_top_z),
                     'support_object_xy_distance':str(support_xy),
                     'outer_wall_speed':str(C['print_outer_wall_speed_mm_s']),'inner_wall_speed':str(C['print_inner_wall_speed_mm_s']),
                     'sparse_infill_density':str(C['print_infill_percent'])+'%','sparse_infill_pattern':'zig-zag',
                     'enable_support':'1','support_type':'tree(auto)','print_settings_id':profile_name})
    for meta in root.findall(NS+'metadata'):
        if meta.get('name')=='Title':meta.text='SkeleCAD '+title
    payload.update({'3D/3dmodel.model':ET.tostring(root,encoding='utf-8',xml_declaration=True),
                    '3D/_rels/3dmodel.model.rels':ET.tostring(rel,encoding='utf-8',xml_declaration=True),
                    'Metadata/model_settings.config':ET.tostring(md,encoding='utf-8',xml_declaration=True),
                    'Metadata/project_settings.config':json.dumps(settings).encode()})
    output=BASE/'print';output.mkdir(exist_ok=True)
    with zipfile.ZipFile(output/'input.3mf','w',zipfile.ZIP_DEFLATED) as z:
        for name,data in payload.items():z.writestr(name,data)
    (output/'input_audit.json').write_text(json.dumps({'parts':records,'bounds':bounds,'supports_enabled':True,'native_bambu':BAMBU},indent=2),encoding='utf-8')
    print(json.dumps({'objects':len(records),'bounds':bounds,'supports_enabled':True}),flush=True)
if __name__=='__main__':main()
