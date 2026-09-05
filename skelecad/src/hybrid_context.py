"""Select the active image-based production model without overwriting prior parts."""
import json
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARAMS = json.loads((ROOT / "config/parameters.json").read_text(encoding="utf-8"))
H = {**PARAMS["hybrid"], **PARAMS.get("hybrid_new", {})}
if H.get('palm_size', {}).get('enabled'):
    palm = H['palm_size']
    scale = (palm['target_assembly_length_mm']-palm['head_extra_forward_mm']-palm['tail_extra_rearward_mm']) / palm['reference_assembly_length_mm']
    def scaled(value):
        if isinstance(value, dict): return {k:scaled(v) for k,v in value.items()}
        if isinstance(value, list): return [scaled(v) for v in value]
        return value * scale
    # Scale anatomy coordinates, not the dimensional mating interface.
    H = copy.deepcopy(H)
    for key in list(H):
        if key.endswith('_mm') and key not in ('preservation_tolerance_mm',):
            H[key] = scaled(H[key])
    for relief in H.get('local_reliefs', []):
        for key in list(relief):
            if key.endswith('_mm'): relief[key] = scaled(relief[key])
    ring=H['hip_ring_transfer']
    for key in list(ring):
        if key.endswith('_mm'): ring[key]=scaled(ring[key])
    extra=palm['limb_extra_outward_mm']
    for spec in H['connections']:
        for key in ('source_support','target_support'):
            spec[key]=scaled(spec[key])
        # Historical anatomy clearance scales with the source. Precision cups
        # and the 6 mm balls are rebuilt at their unchanged dimensions.
        for key in ('clearance_radius','source_clearance_radius'):
            spec[key]=scaled(spec[key])
        if spec['name'].startswith(('shoulder_','hip_','ankle_')):
            sign=1 if spec['name'].endswith('_left') else -1
            spec['source_support'][1]+=sign*extra
            if spec['name'].startswith('ankle_'):
                spec['target_support'][1]+=sign*extra
                H[spec['center_key']][1]+=sign*extra
                stem_extension=palm.get('ankle_ball_stem_extension_mm',0.0)
                spec['source_support'][2]-=palm['foot_extra_down_mm']+stem_extension
                spec['source_stud_extension_mm']=stem_extension
            else:
                H[spec['center_key']][1]+=sign*palm['socket_extra_outward_mm']
        elif spec['name']=='neck':
            spec['source_support'][0]-=palm['head_extra_forward_mm']
        elif spec['name']=='tail_root':
            spec['source_support'][0]+=palm['tail_extra_rearward_mm']
            H[spec['center_key']][0]+=palm['tail_joint_extra_rearward_mm']
    for name,translation in H['part_translation_mm'].items():
        if name.startswith(('arm_','leg_','foot_')):
            translation[1]+=(1 if name.endswith('_left') else -1)*extra
        if name.startswith('foot_'):
            translation[2]-=palm['foot_extra_down_mm']+palm.get('ankle_ball_stem_extension_mm',0.0)
    H['part_translation_mm']['head'][0]-=palm['head_extra_forward_mm']
    H['part_translation_mm']['tail']=[palm['tail_extra_rearward_mm'],0,0]
    H['preserve_target_anatomy_connections']=['neck','tail_root','ankle_left','ankle_right']
    H['output_directory']=palm['output_directory']
    H['appearance_mesh']=palm['output_directory']+'/source_scaled.stl'
    H['target_length_mm']=palm['target_assembly_length_mm']
HYBRID = ROOT / H.get("output_directory", "build/hybrid")
INPUT = ROOT / H.get("appearance_mesh", "build/generated_appearance/trex_appearance_200mm_outward.stl")
