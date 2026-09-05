"""Native Bambu presets + unchanged validated mesh/placement, no Orca settings."""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from hybrid_context import PARAMS,HYBRID
from audit_orca_print import project_audit,NS
ET.register_namespace('',NS[1:-1])
ET.register_namespace('p','http://schemas.microsoft.com/3dmanufacturing/production/2015/06')
TOOLCHAIN=json.loads((ROOT/'config/toolchain.json').read_text(encoding='utf-8'))
BAMBU=TOOLCHAIN['bambu_studio']
PRESET_FILES={}

def preset(kind,name):
    paths=list((Path(BAMBU['profiles'])/kind).rglob(name+'.json'))
    if len(paths)!=1:raise RuntimeError(f'Preset not unique: {name}')
    path=paths[0];data=json.loads(path.read_text(encoding='utf-8'))
    PRESET_FILES[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    values=preset(kind,data['inherits']) if data.get('inherits') else {}
    values.update({k:v for k,v in data.items() if k not in ('name','type','inherits','from','setting_id','filament_id','instantiation','version','description','compatible_printers','compatible_printers_condition','compatible_prints','compatible_prints_condition')})
    return values

def native_settings():
    settings={}
    baselines={}
    for kind,key in [('machine','machine_preset'),('process','process_preset'),('filament','filament_preset')]:
        baselines[kind]=preset(kind,BAMBU[key])
        settings.update(baselines[kind])
    cfg=PARAMS['printing']['production_profile'];support=PARAMS['printing']['support_defaults'];temp=str(PARAMS['printing']['textured_pei_bed_temperature_c'])
    if support.get('enabled') is not True:
        raise ValueError('Production print preparation requires support to be enabled by default')
    settings.update({'printer_settings_id':BAMBU['machine_preset'],'print_settings_id':BAMBU['process_preset'],
        'filament_settings_id':[BAMBU['filament_preset']],'filament_ids':['GFA01'],
        'filament_colour':['#FFFFFF'],'filament_multi_colour':['#FFFFFF'],
        'curr_bed_type':cfg['orca_bed_type'],'textured_plate_temp':[temp],'textured_plate_temp_initial_layer':[temp],
        'layer_height':str(cfg['layer_height_mm']),'wall_loops':str(cfg['wall_loops']),
        'enable_support':'1' if support['enabled'] else '0',
        'support_type':support['type'],'support_top_z_distance':str(support['top_z_distance_mm']),
        'support_object_xy_distance':str(support['object_xy_distance_mm']),
        'support_interface_spacing':str(support['interface_spacing_mm']),
        'support_interface_speed':[str(support['interface_speed_mm_s'])],
        'support_interface_top_layers':str(support['interface_top_layers']),'brim_type':'auto_brim','brim_width':'5','sparse_infill_density':'15%',
        'ensure_vertical_shell_thickness':'enabled','ironing_pattern':'zig-zag','support_ironing_pattern':'zig-zag'})
    # Native enum spellings. Do not import any full Orca configuration.
    assert settings['ensure_vertical_shell_thickness']=='enabled'
    assert settings['ironing_pattern']=='zig-zag'
    assert settings['support_ironing_pattern']=='zig-zag'
    # Bambu's GUI merges the named system presets using these per-preset diff keys.
    # Values alone work in CLI slicing but are not sufficient on GUI project import.
    settings['different_settings_to_system']=[
        ';'.join(sorted(k for k,v in baselines[kind].items()
                        if k in settings and settings[k]!=v and k not in
                        ('different_settings_to_system','inherits_group')))
        for kind in ('process','filament','machine')]
    return settings

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fit',action='store_true');args=parser.parse_args()
    for key in ('executable','library'):
        assert hashlib.sha256(Path(BAMBU[key]).read_bytes()).hexdigest()==BAMBU[key+'_sha256']
    rev=PARAMS['project']['revision'];job='fit_kit' if args.fit else '120mm'
    source=ROOT/'build/print_ready'/f'SkeleCAD_{rev}_{job}_A1mini_BambuMatte_TexturedPEI.3mf'
    model_audit=project_audit(source,args.fit,str(HYBRID.relative_to(ROOT)))
    settings=native_settings()
    with zipfile.ZipFile(source) as z:payload={n:z.read(n) for n in z.namelist() if not n.endswith('.gcode')}
    root=ET.fromstring(payload['3D/3dmodel.model'])
    for item in list(root.findall(NS+'metadata')):
        if item.get('name')=='OrcaSlicer':root.remove(item)
        elif item.get('name')=='Application':item.text='BambuStudio-'+BAMBU['version']
    ET.SubElement(root,NS+'metadata',name='SkeleCAD:Preparation').text='Native Bambu presets; awaiting Bambu CLI export'
    payload['3D/3dmodel.model']=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    payload['Metadata/project_settings.config']=json.dumps(settings,indent=2).encode()
    out=ROOT/'build/print_ready'/f'bambu_{rev}'/'input';out.mkdir(parents=True,exist_ok=True)
    target=out/f'{job}.3mf'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for n,data in payload.items():z.writestr(n,data)
    report={'source_project':model_audit,'preset_files':PRESET_FILES,'slicer':BAMBU,'geometry_changed':False,'native_settings':settings}
    target.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(target)
if __name__=='__main__':main()
