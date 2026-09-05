"""Audit native Bambu 3MFs, geometry, presets, and generated toolpaths."""
import hashlib,json,re,sys,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from hybrid_context import PARAMS,HYBRID
from audit_orca_print import project_audit,sliced_audit,metadata
from prepare_bambu_print import BAMBU,preset

def main():
    rev=PARAMS['project']['revision'];out=ROOT/'build/print_ready'/f'bambu_{rev}'
    report={'slicer':'Bambu Studio','version':BAMBU['version'],'geometry_changed':False,'printer_started':False,'jobs':{}}
    for job in ('fit_kit','120mm'):
        path=out/job/f'SkeleCAD_{rev}_{job}_BambuStudio_A1mini.3mf'
        geometry=project_audit(path,job=='fit_kit',str(HYBRID.relative_to(ROOT)))
        source=project_audit(out/'input'/f'{job}.3mf',job=='fit_kit',str(HYBRID.relative_to(ROOT)))
        assert {p['name']:p['source_sha256'] for p in geometry['parts']}=={p['name']:p['source_sha256'] for p in source['parts']}
        sliced=sliced_audit(path);assert len(sliced['plates'])==1
        plate=sliced['plates'][0];assert len(plate['objects'])==(1 if job=='fit_kit' else 9)
        assert plate['preview_bbox_within_bed']
        assert all(w['msg']=='not_support_traditional_timelapse' for w in plate['warnings']),plate['warnings']
        result=json.loads((out/job/'result.json').read_text(encoding='utf-8'));assert result['return_code']==0,result
        with zipfile.ZipFile(path) as z:
            s=json.loads(z.read('Metadata/project_settings.config'))
            header=ET.fromstring(z.read('Metadata/slice_info.config')).find('header')
            header={n.get('key'):n.get('value') for n in header}
            assert header['X-BBL-Client-Version']==BAMBU['version'] and 'OrcaSlicer-Version' not in header
            gcode=z.read('Metadata/plate_1.gcode').decode()
            previews=out/'inspection';previews.mkdir(exist_ok=True)
            (previews/f'{job}_plate.png').write_bytes(z.read('Metadata/plate_1.png'))
        support=PARAMS['printing']['support_defaults']
        for key,val in {'printer_settings_id':BAMBU['machine_preset'],'filament_settings_id':[BAMBU['filament_preset']],
                        'nozzle_diameter':['0.4'],'layer_height':'0.16','wall_loops':'4',
                        'filament_colour':['#FFFFFF'],'curr_bed_type':'Textured PEI Plate','textured_plate_temp':['55'],
                        'ensure_vertical_shell_thickness':'enabled','ironing_pattern':'zig-zag','support_ironing_pattern':'zig-zag',
                        'enable_support':'1','support_type':support['type'],'support_top_z_distance':str(support['top_z_distance_mm']),
                        'support_object_xy_distance':str(support['object_xy_distance_mm']),
                        'support_interface_top_layers':str(support['interface_top_layers']),
                        'support_interface_spacing':str(support['interface_spacing_mm']),
                        'support_interface_speed':[str(support['interface_speed_mm_s'])]}.items():assert s[key]==val,(key,s[key])
        machine=preset('machine',BAMBU['machine_preset'])
        for key in ('machine_start_gcode','machine_end_gcode','change_filament_gcode','printable_area','printable_height','gcode_flavor'):
            assert s[key]==machine[key],key
        assert re.search(r'^M190 S55\b',gcode,re.M)
        assert 'BambuStudio' in gcode[:1000] or 'Bambu Studio' in gcode[:1000]
        assert not re.search(r'\{[^\n]*\}', '\n'.join(x.split(';')[0] for x in gcode.splitlines()))
        report['jobs'][job]={'geometry':geometry,'slice':sliced,'native_enum_values_verified':True,'native_machine_macros_verified':True}
    report['passed']=True
    report['notes']=['Native Bambu settings and engine; no Orca settings copied.',
                     f'CAD/STL/collision/CalculiX results are the validated revision {rev} results.',
                     'Traditional timelapse not supported by these layouts: leave timelapse disabled.',
                     'Physical fit/retention is untested; print fit kit first.']
    (out/'audit.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'passed':True,'jobs':{k:v['slice']['plates'] for k,v in report['jobs'].items()}},ensure_ascii=False))
if __name__=='__main__':main()
