"""Native Bambu projects from arbitrary validated part manifests (no GUI).

This creates editable, unsliced plates. Geometry-bound review is verified
before release; users slice and inspect supports in Bambu Studio.
"""
import argparse
import copy
import hashlib
import itertools
import json
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
from bambu_settings import native_settings,BAMBU,PARAMS,ROOT
from print_package_audit import set_meta
from print_package_audit import NS,PNS,arrays,metadata
from machine_image_job import load,write,sha
from bambu_project_schema import empty_project


def orient(mesh):
    """Preserve the original low-height rigid orientation and mating scale."""
    choices=[]
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((-1,1),repeat=3):
            R=np.eye(3)[:,perm]*signs
            if np.linalg.det(R)<.9:continue
            size=np.ptp(mesh.vertices@R,axis=0)
            choices.append((float(size[2]),float(size[0]),R))
    return min(choices,key=lambda c:c[:2])[2]


def pack(objects,cfg):
    """Deterministic multi-plate shelves, model extents exclude support/brims.

    Supports can exceed these extents; inspect the slice in Bambu Studio.
    """
    margin=cfg['plate_margin_mm'];gap=cfg['object_gap_mm'];side=cfg['plate_width_mm']
    plates=[[]];x=y=margin;depth=0
    for obj in sorted(objects,key=lambda o:-(o['hi']-o['lo'])[1]):
        size=obj['hi']-obj['lo']
        if max(size[:2])>side-2*margin:raise ValueError('Part does not fit the configured plate without resizing')
        if x+size[0]>side-margin:x=margin;y+=depth+gap;depth=0
        if y+size[1]>side-margin:plates.append([]);x=y=margin;depth=0
        obj={**obj,'shift':np.array([x,y,0])-obj['lo']}
        plates[-1].append(obj);x+=size[0]+gap;depth=max(depth,size[1])
    return plates


def mesh_xml(mesh,offset):
    """Same decimal precision and face order without millions of Element objects."""
    vertices=''.join('<vertex x="{:.12g}" y="{:.12g}" z="{:.12g}"/>'.format(float(x),float(y),float(z)) for x,y,z in mesh.vertices-offset)
    faces=''.join('<triangle v1="{}" v2="{}" v3="{}"/>'.format(int(a),int(b),int(c)) for a,b,c in mesh.faces)
    return ('<mesh xmlns="'+NS[1:-1]+'"><vertices>'+vertices+'</vertices><triangles>'+faces+'</triangles></mesh>').encode('utf-8')


def package(directory):
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if manifest['stage']!='mechanical_review':raise ValueError('Validated mechanical parts required')
    for key in ('executable','library'):
        if sha(Path(BAMBU[key]))!=BAMBU[key+'_sha256']:raise ValueError('Bambu version changed; verify toolchain first')
    objects=[]
    for spec in manifest['parts']:
        source=directory/spec['filename']
        if sha(source)!=spec['sha256']:raise ValueError('Geometry changed after review')
        mesh=load(source)
        if len(mesh.split(only_watertight=False))!=1:raise ValueError('Part is disconnected')
        R=orient(mesh);offset=mesh.bounds.mean(0);v=(mesh.vertices-offset)@R
        objects.append(dict(spec=spec,mesh=mesh,R=R,offset=offset,lo=v.min(0),hi=v.max(0)))
    settings=native_settings();plates=pack(objects,PARAMS['printing']['production_profile'])
    original_root,original_obj,original_item,original_objmd,original_node,base_payload=empty_project()
    output=directory/'print';output.mkdir(exist_ok=True);reports=[]
    for pi,objects in enumerate(plates,1):
        folder=output/f'plate_{pi:02d}';folder.mkdir(exist_ok=True)
        root=copy.deepcopy(original_root);root.set('unit','millimeter')
        resources=root.find(NS+'resources');resources.clear();build=root.find(NS+'build');build.clear()
        md=ET.Element('config');plate=ET.SubElement(md,'plate')
        for k,v in {'plater_id':'1','plater_name':f'SkeleCAD {pi}','locked':'false','filament_map_mode':'Auto For Flush'}.items():set_meta(plate,k,v)
        rel=ET.Element('Relationships',xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        payload=dict(base_payload);records=[]
        for i,data in enumerate(objects):
            spec=data['spec'];mesh=data['mesh'];offset=data['offset'];R=data['R'];shift=data['shift']
            mesh_id=str(2*i+1);oid=str(2*i+2);path=f'3D/Objects/Part_{i+1}.model'
            obj=copy.deepcopy(original_obj);obj.set('id',oid);obj.set(PNS+'UUID',str(uuid.uuid4()))
            component=obj.find(NS+'components/'+NS+'component');component.set('objectid',mesh_id);component.set(PNS+'path','/'+path);component.set(PNS+'UUID',str(uuid.uuid4()));resources.append(obj)
            node=copy.deepcopy(original_node);container=node.find('.//'+NS+'object');container.remove(container.find(NS+'mesh'))
            container.set('id',mesh_id);container.set(PNS+'UUID',str(uuid.uuid4()))
            ET.SubElement(container,'skelecad_mesh')
            payload[path]=ET.tostring(node,encoding='utf-8',xml_declaration=True).replace(b'<skelecad_mesh />',mesh_xml(mesh,offset))
            ET.SubElement(rel,'Relationship',Target='/'+path,Id=f'rel-{i+1}',Type='http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel')
            item=copy.deepcopy(original_item);item.set('objectid',oid);item.set(PNS+'UUID',str(uuid.uuid4()))
            item.set('transform',' '.join(format(float(v),'.12g') for v in np.r_[R.ravel(),shift]));build.append(item)
            objmd=copy.deepcopy(original_objmd);objmd.set('id',oid);set_meta(objmd,'name',spec['name'])
            partmd=objmd.find('part');partmd.set('id',mesh_id);set_meta(partmd,'name',spec['name']);set_meta(partmd,'source_file',spec['filename'])
            for k,v in zip('xyz',offset):set_meta(partmd,'source_offset_'+k,format(float(v),'.15g'))
            md.insert(len(md)-1,objmd);inst=ET.SubElement(plate,'model_instance')
            for k,v in {'object_id':oid,'instance_id':'0','identify_id':oid}.items():set_meta(inst,k,v)
            records.append({'name':spec['name'],'filename':spec['filename'],'sha256':spec['sha256'],
                            'min':(data['lo']+shift).tolist(),'max':(data['hi']+shift).tolist()})
        for meta in list(root.findall(NS+'metadata')):
            if meta.get('name')=='OrcaSlicer':root.remove(meta)
            elif meta.get('name')=='Application':meta.text='BambuStudio-'+BAMBU['version']
            elif meta.get('name')=='Title':meta.text=f'SkeleCAD Image Model - Plate {pi}'
        payload.update({'3D/3dmodel.model':ET.tostring(root,encoding='utf-8',xml_declaration=True),
                        '3D/_rels/3dmodel.model.rels':ET.tostring(rel,encoding='utf-8',xml_declaration=True),
                        'Metadata/model_settings.config':ET.tostring(md,encoding='utf-8',xml_declaration=True),
                        'Metadata/project_settings.config':json.dumps(settings).encode()})
        path=folder/'input.3mf'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            for name,data in payload.items():z.writestr(name,data)
        report={'plate':pi,'manifest_sha256':sha(directory/'manifest.json'),'parts':records,'support_enabled':settings['enable_support']=='1',
                'native_bambu_version':BAMBU['version'],'sliced':False,'physical_strength_verified':False}
        write(folder/'input_audit.json',report);audit_input(path,directory,report)
        reports.append(report)
    write(output/'preparation.json',{'plates':reports,'manifest_sha256':sha(directory/'manifest.json'),'ready_to_print':False})
    return reports


def audit_input(path,directory,report):
    expected={p['name']:p for p in report['parts']};seen=set()
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise ValueError('Corrupt print package')
        settings=json.loads(z.read('Metadata/project_settings.config'))
        support=PARAMS['printing']['support_defaults']
        required={'enable_support':'1','support_type':support['type'],
                  'support_top_z_distance':str(support['top_z_distance_mm']),
                  'support_object_xy_distance':str(support['object_xy_distance_mm']),
                  'support_interface_spacing':str(support['interface_spacing_mm']),
                  'support_interface_speed':[str(support['interface_speed_mm_s'])],
                  'support_interface_top_layers':str(support['interface_top_layers'])}
        for key,value in required.items():
            if settings.get(key)!=value:raise ValueError(f'Unexpected support setting {key}')
        root=ET.fromstring(z.read('3D/3dmodel.model'));md=ET.fromstring(z.read('Metadata/model_settings.config'))
        if root.get('unit')!='millimeter':raise ValueError('Print package must use millimetres')
        mapping={o.get('id'):o for o in md.findall('object')}
        ids=set()
        for obj in root.find(NS+'resources'):
            info=mapping[obj.get('id')];name=metadata(info)['name'];spec=expected[name]
            if name in seen:raise ValueError('Duplicate object');
            seen.add(name)
            component=obj.find(NS+'components/'+NS+'component');v,f=arrays(z.read(component.get(PNS+'path').lstrip('/')))
            for value in (obj.get('id'),component.get('objectid')):
                if value in ids:raise ValueError('Bambu object IDs must be globally unique')
                ids.add(value)
            if sha(directory/spec['filename'])!=spec['sha256']:raise ValueError('Reviewed source changed during packaging')
            ref=load(directory/spec['filename']);offset=np.array([float(metadata(info.find('part'))['source_offset_'+k]) for k in 'xyz'])
            if not np.array_equal(f,ref.faces) or not np.allclose(v+offset,ref.vertices,atol=2e-5,rtol=0):raise ValueError('Print geometry differs from reviewed geometry')
        if seen!=set(expected):raise ValueError('Missing print parts')
        for item in root.find(NS+'build'):
            R=np.array([float(v) for v in item.get('transform').split()[:9]]).reshape(3,3)
            if not np.allclose(R@R.T,np.eye(3),atol=1e-7) or abs(np.linalg.det(R)-1)>1e-7:raise ValueError('Non-rigid print transform')
    return True


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--revision-directory',type=Path,required=True)
    print(json.dumps(package(parser.parse_args().revision_directory.resolve()),indent=2))
