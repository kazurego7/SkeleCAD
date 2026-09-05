"""Package unchanged validated meshes as nine named, independently selectable objects."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from hybrid_context import HYBRID, PARAMS
from validate_3mf import analyse

NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('',NS)
tag=lambda name:f'{{{NS}}}{name}'
model=ET.Element(tag('model'),{'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'en-US'})
ET.SubElement(model,tag('metadata'),{'name':'Title'}).text=f"SkeleCAD {PARAMS['project']['revision']} - restored anatomy - 9 parts"
resources=ET.SubElement(model,tag('resources'));build=ET.SubElement(model,tag('build'))
names=['head','torso','arm_left','arm_right','leg_left','leg_right','foot_left','foot_right','tail']
records=[];cursor_x=7.0;cursor_y=7.0;row_depth=0.0
for number,name in enumerate(names,1):
    path=HYBRID/'parts'/f'{name}.3mf'
    with zipfile.ZipFile(path) as z:
        xml_name=next(n for n in z.namelist() if n.replace('\\','/')=='3D/3dmodel.model')
        source=ET.fromstring(z.read(xml_name))
    mesh=source.find('.//'+tag('mesh'))
    vertices=mesh.find(tag('vertices'))
    coords=[tuple(float(v.attrib[k]) for k in ('x','y','z')) for v in vertices]
    low=[min(v[i] for v in coords) for i in range(3)]
    high=[max(v[i] for v in coords) for i in range(3)]
    width,depth=high[0]-low[0],high[1]-low[1]
    # Compact review layout only; no printer/filament profile or mesh alteration.
    if cursor_x+width+7>170:
        cursor_x=7.0;cursor_y+=row_depth+7;row_depth=0.0
    obj=ET.SubElement(resources,tag('object'),{'id':str(number),'name':name,'type':'model'})
    obj.append(mesh)
    offset=[cursor_x-low[0],cursor_y-low[1],-low[2]]
    ET.SubElement(build,tag('item'),{'objectid':str(number),'transform':'1 0 0 0 1 0 0 0 1 '+' '.join(str(v) for v in offset)})
    records.append({'name':name,'source':str(path.relative_to(ROOT)),
                    'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'vertices':len(vertices),'triangles':len(mesh.find(tag('triangles'))),
                    'placement_translation_mm':offset})
    cursor_x+=width+7;row_depth=max(row_depth,depth)
out=HYBRID/'parts_review'/f"SkeleCAD_{PARAMS['project']['revision']}_9_parts.3mf"
out.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    z.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
check=analyse(out)
assert check['passed'] and check['objects']==9 and check['build_items']==9
assert check['triangles']==sum(r['triangles'] for r in records)
with zipfile.ZipFile(out) as z:
    packaged=ET.fromstring(z.read('3D/3dmodel.model'))
    for obj,name in zip(packaged.find(tag('resources')),names):
        with zipfile.ZipFile(HYBRID/'parts'/f'{name}.3mf') as s:
            xml_name=next(n for n in s.namelist() if n.replace('\\','/')=='3D/3dmodel.model')
            original=ET.fromstring(s.read(xml_name)).find('.//'+tag('mesh'))
        assert ET.tostring(obj.find(tag('mesh')))==ET.tostring(original),name
report={'revision':PARAMS['project']['revision'],'mesh_data_unchanged':True,'validation':check,'parts':records,'review_layout_height_mm':cursor_y+row_depth+7}
out.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'path':str(out),'validation':check,'mesh_data_unchanged':True,'layout_height_mm':report['review_layout_height_mm']}))
