"""Release gate for the five-pattern all-printed calibration plate."""
import hashlib,json,re,zipfile
from xml.etree import ElementTree as ET
import numpy as np
from prepare_retention_print import C,BASE,ROOT,BAMBU
from print_package_audit import NS,PNS,arrays,metadata,sliced_audit

def main(filename='SkeleCAD_Retention_R1_A1mini_PLA_Matte.3mf',expected_count=17,limits=None):
    out=BASE/'print';file=out/filename
    original=json.loads((out/'input_audit.json').read_text(encoding='utf-8'))
    expected={r['label']:r for r in original['parts']};parts=[]
    with zipfile.ZipFile(file) as z:
        assert z.testzip() is None
        root=ET.fromstring(z.read('3D/3dmodel.model'));assert root.get('unit')=='millimeter'
        md=ET.fromstring(z.read('Metadata/model_settings.config'));mds={o.get('id'):o for o in md.findall('object')}
        settings=json.loads(z.read('Metadata/project_settings.config'))
        for obj in root.find(NS+'resources').findall(NS+'object'):
            meta=mds[obj.get('id')];label=metadata(meta)['name'];record=expected[label]
            component=obj.find(NS+'components/'+NS+'component')
            actual_v,actual_f=arrays(z.read(component.get(PNS+'path').lstrip('/')))
            source=ROOT/record['source'];assert hashlib.sha256(source.read_bytes()).hexdigest()==record['sha256']
            with zipfile.ZipFile(source) as src:ref_v,ref_f=arrays(src.read('3D/3dmodel.model'))
            offset=np.array([float(metadata(meta.find('part'))['source_offset_'+k]) for k in 'xyz'])
            delta=float(np.max(np.abs(actual_v+offset-ref_v)))
            assert np.array_equal(actual_f,ref_f) and delta<2e-5,(label,delta)
            parts.append({'name':label,'sha256':record['sha256'],'rounding_mm':delta})
        assert len(parts)==expected_count and {p['name'] for p in parts}==set(expected)
        for item in root.find(NS+'build'):
            R=np.array([float(v) for v in item.get('transform').split()[:9]]).reshape(3,3)
            assert np.allclose(R@R.T,np.eye(3),atol=1e-7) and abs(np.linalg.det(R)-1)<1e-7
        for key,value in {'enable_support':'1','support_type':'tree(auto)','layer_height':'0.12',
                          'nozzle_diameter':['0.4'],'filament_settings_id':[BAMBU['filament_preset']],
                          'sparse_infill_density':'100%','sparse_infill_pattern':'zig-zag','outer_wall_speed':['35'],
                          'curr_bed_type':'Textured PEI Plate','textured_plate_temp':['55']}.items():
            assert settings[key]==value,(key,settings[key])
        for key,value in {
            'support_top_z_distance':str(C.get('print_support_top_z_distance_mm',C['print_layer_height_mm'])),
            'support_object_xy_distance':str(C.get('print_support_object_xy_distance_mm',settings['support_object_xy_distance']))
        }.items():assert settings[key]==value,(key,settings[key])
        header=ET.fromstring(z.read('Metadata/slice_info.config')).find('header')
        header_values={item.get('key'):item.get('value') for item in header}
        assert header_values['X-BBL-Client-Version']==BAMBU['version']
        assert 'OrcaSlicer-Version' not in header_values
        gcode=z.read('Metadata/plate_1.gcode').decode()
        assert re.search(r'^M190 S55\b',gcode,re.M)
        assert '; FEATURE: Support' in gcode,'Supports must actually be generated, not only enabled'
        (out/'plate.png').write_bytes(z.read('Metadata/plate_1.png'))
    sliced=sliced_audit(file);assert len(sliced['plates'])==1
    plate=sliced['plates'][0];assert len(plate['objects'])==expected_count and set(plate['objects'])==set(expected)
    assert all(w['msg']=='not_support_traditional_timelapse' for w in plate['warnings']),plate['warnings']
    assert json.loads((out/'result.json').read_text())['return_code']==0
    cad=json.loads((BASE/'cad_report.json').read_text());mechanical=json.loads((BASE/'mechanical_audit.json').read_text());cae=json.loads((BASE/'cae_report.json').read_text())
    assert mechanical['passed'] and cae['solver_completed'] and all(p['cad_valid'] for p in cad['parts'])
    report={'passed':True,'supports_enabled_and_generated':True,'parts':parts,'slice':sliced,'configuration':C,
            'support_release_settings':{'top_z_distance_mm':float(settings['support_top_z_distance']),
                                        'object_xy_distance_mm':float(settings['support_object_xy_distance']),
                                        'interface_top_layers':int(settings['support_interface_top_layers'])},
            'mechanical_variants':[{'name':v['name'],'minimum_sampled_clear_deg':min(m['clear_deg'] for m in v['motion'])} for v in mechanical['variants']],
            'cae':cae,'physical_retention_verified':False,'production_body_changed':False,
            'limits':limits or ['Five experimental fits, not a validated replacement joint.','Do not force thin stems or hammer wedge keys.','Disable traditional timelapse.']}
    (out/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'plate':plate,'motion':report['mechanical_variants']}),flush=True)
if __name__=='__main__':main()
