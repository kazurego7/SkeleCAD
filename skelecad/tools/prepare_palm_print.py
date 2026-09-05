"""Build an unsliced Orca project from current meshes and pinned local presets.

Old project is only a schema/orientation/settings template. No old mesh, thumbnail
or toolpath is copied. Slicing and visual support inspection remain mandatory.
"""
import argparse,copy,hashlib,json,sys,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from hybrid_context import PARAMS,HYBRID
from audit_orca_print import metadata,arrays
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
PNS='http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
ET.register_namespace('',NS);ET.register_namespace('p',PNS)
tag=lambda n:f'{{{NS}}}{n}'
profiles=ROOT.parent/'.tools/orcaslicer-2.4.2/resources/profiles/BBL/filament'

def preset(name):
    paths=list(profiles.rglob(name+'.json'))
    if len(paths)!=1:raise RuntimeError(f'Preset not unique: {name}')
    data=json.loads(paths[0].read_text(encoding='utf-8'))
    result=preset(data['inherits']) if data.get('inherits') else {}
    result.update({k:v for k,v in data.items() if k not in ('inherits','name','type','from','setting_id','filament_id','instantiation','version','compatible_printers')})
    return result

def set_meta(parent,key,value):
    node=next((e for e in parent.findall('metadata') if e.get('key')==key),None)
    if node is None:node=ET.SubElement(parent,'metadata',key=key)
    node.set('value',str(value))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fit',action='store_true');args=parser.parse_args()
    cfg=PARAMS['printing']['production_profile'];revision=PARAMS['project']['revision']
    template=ROOT/'build/print_ready'/('SkeleCAD_1.2.4_fit_kit_A1mini_PLA_draft.3mf' if args.fit else 'SkeleCAD_1.2.4_A1mini_PLA_draft.3mf')
    with zipfile.ZipFile(template) as old:
        root=ET.fromstring(old.read('3D/3dmodel.model'))
        md=ET.fromstring(old.read('Metadata/model_settings.config'))
        settings=json.loads(old.read('Metadata/project_settings.config'))
        payload={name:old.read(name) for name in ('[Content_Types].xml','3D/_rels/3dmodel.model.rels')}
        roots={name:ET.fromstring(old.read(name)) for name in old.namelist() if name.startswith('3D/Objects/')}
    settings.update(preset('Bambu PLA Matte @BBL A1M'))
    settings.update({'filament_settings_id':['Bambu PLA Matte @BBL A1M'],
        'filament_ids':['GFA01'],'filament_colour':['#FFFFFF'],'filament_multi_colour':['#FFFFFF'],
        'print_settings_id':f'SkeleCAD {revision} 120mm 0.16mm 4walls',
        'layer_height':str(cfg['layer_height_mm']),'wall_loops':str(cfg['wall_loops']),
        'curr_bed_type':cfg.get('orca_bed_type','High Temp Plate'),
        'textured_plate_temp':[str(PARAMS['printing']['textured_pei_bed_temperature_c'])],
        'textured_plate_temp_initial_layer':[str(PARAMS['printing']['textured_pei_bed_temperature_c'])]})
    for node in root.findall(tag('metadata')):
        if node.get('name')=='Title':node.text=f'SkeleCAD {revision} - 120mm - Bambu PLA Matte White'
    object_md={o.get('id'):o for o in md.findall('object')}
    items={i.get('objectid'):i for i in root.find(tag('build'))}
    objects=[];records=[]
    for obj in root.find(tag('resources')).findall(tag('object')):
        oid=obj.get('id');meta=object_md[oid];name=metadata(meta)['name']
        component=obj.find(tag('components')).find(tag('component'))
        path=component.get(f'{{{PNS}}}path').lstrip('/')
        source=ROOT/'build/print/starter_fit_kit.3mf' if args.fit else HYBRID/'parts'/f'{name}.3mf'
        with zipfile.ZipFile(source) as z:original=ET.fromstring(z.read('3D/3dmodel.model')).find('.//'+tag('mesh'))
        mesh=copy.deepcopy(original);vs=mesh.find(tag('vertices'))
        coords=np.array([[float(v.get(k)) for k in 'xyz'] for v in vs]);offset=(coords.min(0)+coords.max(0))/2
        for vertex,point in zip(vs,coords-offset):
            for k,value in zip('xyz',point):vertex.set(k,format(value,'.12g'))
        container=roots[path].find('.//'+tag('object'))
        container.remove(container.find(tag('mesh')));container.append(mesh)
        part_meta=meta.find('part')
        for k,value in zip('xyz',offset):set_meta(part_meta,'source_offset_'+k,format(value,'.15g'))
        set_meta(part_meta,'source_file',source.name)
        R=np.array(list(map(float,items[oid].get('transform').split()))[:9]).reshape(3,3)
        if name.startswith('leg_') and not args.fit:
            # Lay the lateral plane flat; support both round mating surfaces.
            sign=1 if name.endswith('left') else -1
            R=np.array([[1,0,0],[0,0,sign],[0,-sign,0]],dtype=float)
        assert np.allclose(R@R.T,np.eye(3),atol=1e-7) and np.linalg.det(R)>.999999
        oriented=(coords-offset)@R;lo=oriented.min(0);hi=oriented.max(0)
        objects.append((oid,name,R,lo,hi))
        records.append({'name':name,'source':str(source.relative_to(ROOT)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'vertices':len(vs),'triangles':len(mesh.find(tag('triangles'))),'source_offset':offset.tolist()})
    margin=cfg['plate_margin_mm'];gap=cfg['object_gap_mm'];side=cfg['plate_width_mm']
    x=y=margin;depth=0;all_bounds=[]
    for oid,name,R,lo,hi in sorted(objects,key=lambda o:-(o[4]-o[3])[1]):
        size=hi-lo
        if x+size[0]>side-margin:x=margin;y+=depth+gap;depth=0
        shift=np.array([x,y,0])-lo
        assert y+size[1]<=side-margin,(name,'Does not fit one plate')
        items[oid].set('transform',' '.join(format(v,'.12g') for v in np.r_[R.ravel(),shift]))
        all_bounds.append([lo+shift,hi+shift]);x+=size[0]+gap;depth=max(depth,size[1])
    for node in list(md):
        if node.tag!='object':md.remove(node)
    plate=ET.SubElement(md,'plate')
    for k,v in {'plater_id':'1','plater_name':f'120mm {revision}','locked':'false','filament_map_mode':'Auto For Flush'}.items():set_meta(plate,k,v)
    for oid in items:
        inst=ET.SubElement(plate,'model_instance')
        for k,v in {'object_id':oid,'instance_id':'0','identify_id':oid}.items():set_meta(inst,k,v)
    for path,node in roots.items():payload[path]=ET.tostring(node,encoding='utf-8',xml_declaration=True)
    payload['3D/3dmodel.model']=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    payload['Metadata/model_settings.config']=ET.tostring(md,encoding='utf-8',xml_declaration=True)
    payload['Metadata/project_settings.config']=json.dumps(settings,indent=2).encode()
    payload['_rels/.rels']=b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    suffix='TexturedPEI' if cfg['plate_confirmed'] else 'plate_PENDING'
    out=ROOT/'build/print_ready'/f'SkeleCAD_{revision}_{"fit_kit" if args.fit else "120mm"}_A1mini_BambuMatte_{suffix}.3mf'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in payload.items():z.writestr(name,data)
    report={'file':out.name,'sliced':False,'plate_confirmed':cfg['plate_confirmed'],'parts':records,'layout_bounds_mm':np.array(all_bounds).tolist(),'filament':'Bambu PLA Matte @BBL A1M','geometry_scaled_in_slicer':False}
    out.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
