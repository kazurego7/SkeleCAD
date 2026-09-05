"""Release audit for current 120 mm geometry and headless Orca output."""
import hashlib,json,re,sys,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from hybrid_context import PARAMS,HYBRID
from audit_orca_print import project_audit,sliced_audit,metadata,NS,PNS,arrays

def inherited_machine(name):
    folder=ROOT.parent/'.tools/orcaslicer-2.4.2/resources/profiles/BBL/machine'
    paths=list(folder.rglob(name+'.json'));assert len(paths)==1,name
    data=json.loads(paths[0].read_text(encoding='utf-8'))
    result=inherited_machine(data['inherits']) if data.get('inherits') else {}
    result.update(data);return result

def verify_settings(package):
    with zipfile.ZipFile(package) as z:
        settings=json.loads(z.read('Metadata/project_settings.config'))
        code=z.read('Metadata/plate_1.gcode').decode()
    assert settings['printer_model']=='Bambu Lab A1 mini'
    assert settings['printer_settings_id']=='Bambu Lab A1 mini 0.4 nozzle'
    assert settings['nozzle_diameter']==['0.4']
    assert settings['filament_settings_id']==['Bambu PLA Matte @BBL A1M']
    assert settings['filament_colour']==['#FFFFFF']
    assert settings['curr_bed_type']=='Textured PEI Plate'
    assert settings['textured_plate_temp']==[str(PARAMS['printing']['textured_pei_bed_temperature_c'])]
    assert settings['textured_plate_temp_initial_layer']==settings['textured_plate_temp']
    assert settings['layer_height']=='0.16' and settings['wall_loops']=='4'
    machine=inherited_machine('Bambu Lab A1 mini 0.4 nozzle')
    keys=['machine_start_gcode','machine_end_gcode','change_filament_gcode','printable_area','printable_height','gcode_flavor']
    for key in keys:assert settings[key]==machine[key],('Machine profile differs',key)
    assert re.search(r'^M190 S55\b',code,re.M)
    assert re.search(r'^M83\b',code,re.M) and re.search(r'^G90\b',code,re.M)
    assert not re.search(r'\{[^\n]*\}', '\n'.join(x.split(';')[0] for x in code.splitlines()))
    return {'stock_machine_macros_match':keys,'bed_c':55,'nozzle_c':settings['nozzle_temperature'],
            'support':settings['support_type'],'support_top_z_distance':settings['support_top_z_distance'],
            'support_interface_top_layers':settings['support_interface_top_layers']}

def main():
    rev=PARAMS['project']['revision'];out=ROOT/'build/print_ready'/f'sliced_{rev}'
    review=json.loads((ROOT/'build/review/current/review.json').read_text(encoding='utf-8'))
    assert review['project']['revision']==rev,'Full model build must finish first'
    assert json.loads((ROOT/'build/review/current/parameters.json').read_text(encoding='utf-8'))==PARAMS
    report={'revision':rev,'status':'prepared_for_prototype_print_not_physically_validated','physical_fit_tested':False,'printer_started':False,'jobs':{}}
    for job in ('fit_kit','120mm'):
        base=f'SkeleCAD_{rev}_{job}_A1mini_BambuMatte_TexturedPEI'
        source=ROOT/'build/print_ready'/f'{base}.3mf';package=out/job/f'{base}.gcode.3mf'
        current=project_audit(source,fit=job=='fit_kit',hybrid_directory=str(HYBRID.relative_to(ROOT)))
        saved=project_audit(package,fit=job=='fit_kit',hybrid_directory=str(HYBRID.relative_to(ROOT)))
        sliced=sliced_audit(package);assert len(sliced['plates'])==1
        for plate in sliced['plates']:
            assert plate['preview_bbox_within_bed']
            assert len(plate['objects'])==(1 if job=='fit_kit' else 9)
            allowed_warnings={'bed_temperature_too_high_than_filament','not_support_traditional_timelapse'}
            assert all(w['msg'] in allowed_warnings for w in plate['warnings']),plate['warnings']
        settings=verify_settings(package)
        with zipfile.ZipFile(package) as z:
            # Extract generated G-code with a unique descriptive filename for microSD.
            code=z.read('Metadata/plate_1.gcode');gcode=out/job/f'{base}.gcode';gcode.write_bytes(code)
        report['jobs'][job]={'input_project':current,'sliced_geometry':saved,'slice':sliced,'settings':settings,'gcode':gcode.name,'gcode_sha256':hashlib.sha256(code).hexdigest()}
    required=['environment_report','cad_report','hybrid_joint_tools','hybrid_parts','anatomy_preservation','hybrid_assembly_collision','hybrid_motion','hybrid_package','mesh_report','three_mf_report','joint_motion_report','socket_fit_report','assembly_motion_report','cae_report','cae_actual_bone_report','cae_ball_stud_report']
    report['validation_reports']={}
    for name in required:
        path=ROOT/'build/reports'/f'{name}.json';data=json.loads(path.read_text(encoding='utf-8'))
        if name=='cad_report':
            passed=bool(data['parts']) and all(p['valid'] and p['solid_count']>0 for p in data['parts'])
            assert data['project']['revision']==rev
        elif name in ('mesh_report','three_mf_report'):
            entries=data['parts' if name=='mesh_report' else 'files']
            passed=bool(entries) and all(p['passed'] for p in entries)
        else:passed=data.get('passed') is True
        assert passed,(name,'not passed')
        if name=='hybrid_package':
            assert data['revision']==rev and data['palm_size']['passed']
        report['validation_reports'][name]={'passed':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    sizing=json.loads((HYBRID/'sizing.json').read_text(encoding='utf-8'))
    report['sizing']=sizing
    report['limitations']=[
        'Print fit kit first; joint holding force, repeatability, wear and organic-wall strength are not physically verified.',
        '55 C Textured PEI bed is within manufacturer guidance. Orca warns because inherited PLA vitrification threshold is 45 C; warning retained.',
        'Body layout does not support traditional timelapse. Leave timelapse disabled when printing; warning retained.',
        'CLI slice_info first_layer_time is unreliable; use G-code header estimate and prediction, not that field.',
        'Stock A1 mini start/end/toolchange macros match pinned official profiles; purge and cleaning moves intentionally extend beyond model print bounds.',
        'Image-derived details and shallow rims are delicate; remove supports carefully. Not a certified children\'s toy.'
    ]
    (out/'print_audit.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'audit':str(out/'print_audit.json'),'passed':True,'jobs':{k:v['slice']['plates'] for k,v in report['jobs'].items()}},ensure_ascii=False))
if __name__=='__main__':main()
