"""Native Bambu presets + unchanged validated mesh/placement, no Orca settings."""
import hashlib,json
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
PARAMS=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
from print_package_audit import NS
ET.register_namespace('',NS[1:-1])
ET.register_namespace('p','http://schemas.microsoft.com/3dmanufacturing/production/2015/06')
from runtime_paths import tool_config
TOOLCHAIN=tool_config()
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
        'layer_height':str(cfg['layer_height_mm']),
        'enable_support':'1',
        'brim_type':'auto_brim','brim_width':'5'})
    # Support details, strength and speed are inherited from the native presets.
    # Bambu's GUI merges the named system presets using these per-preset diff keys.
    # Values alone work in CLI slicing but are not sufficient on GUI project import.
    settings['different_settings_to_system']=[
        ';'.join(sorted(k for k,v in baselines[kind].items()
                        if k in settings and settings[k]!=v and k not in
                        ('different_settings_to_system','inherits_group')))
        for kind in ('process','filament','machine')]
    return settings
