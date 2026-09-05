"""Release gate for the six-object R3 incremental holding-fit plate."""
import json
import audit_retention_print as shared

def main():
    from validate_holding_meshes import main as validate_meshes
    validate_meshes('joint_holding_step_trial')
    params=json.loads((shared.ROOT/'config/parameters.json').read_text(encoding='utf-8'))
    c=params['joint_holding_step_trial'];shared.C={**shared.C,**c}
    shared.BASE=shared.ROOT/c['output_directory']
    shared.main('SkeleCAD_Holding_R3_A1mini_PLA_Matte.3mf',6,[
        'Cavity diameters 5.95/5.925/5.90 mm; ball 6 mm and all stems 3.4 mm.',
        'All three variants intentionally preload the spherical fit; insertion force and holding torque require physical comparison.',
        'No mouth relief; stop if whitening, cracking or permanent opening occurs.',
        'S1 repeats the preferred H3 geometry; S2 and S3 increase diametral interference by 0.025 and 0.05 mm.'])

if __name__=='__main__':main()
