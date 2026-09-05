"""Release gate for the six-object C4 holding-fit comparison plate."""
import json
import audit_retention_print as shared

def main():
    from validate_holding_meshes import main as validate_meshes
    validate_meshes()
    params=json.loads((shared.ROOT/'config/parameters.json').read_text(encoding='utf-8'))
    c=params['joint_holding_trial'];shared.C={**shared.C,**c}
    shared.BASE=shared.ROOT/c['output_directory']
    shared.main('SkeleCAD_Holding_R2_A1mini_PLA_Matte.3mf',6,[
        'Cavity diameters 6.15/6.05/5.95 mm; ball 6 mm and all stems 3.4 mm.',
        'H3 has intentional 0.025 mm radial spherical interference; holding torque and PLA set require a physical trial.',
        'No extra mouth relief; reduced sampled range is reported, not hidden.',
        'Do not force an unseated ball. Stop if whitening, cracking or permanent opening occurs.'])

if __name__=='__main__':main()
