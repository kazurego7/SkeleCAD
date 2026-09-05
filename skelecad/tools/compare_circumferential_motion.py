"""Compare actual anatomy before/after full-circle socket relief."""
import sys, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import trimesh
from hybrid_context import H, HYBRID
from hybrid_validate_motion import overlap_volume, rotated, sweep
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'backups/revision_1_2_4_before_stem_reliefs/hybrid_20260830'

def main():
    rows=[];checks=[]
    for name,part in [('shoulder_left','arm_left'),('shoulder_right','arm_right'),
                      ('hip_left','leg_left'),('hip_right','leg_right')]:
        spec=next(s for s in H['connections'] if s['name']==name)
        center=H[spec['center_key']];sign=spec['mouth_direction'][1]
        meshes={label:{n:trimesh.load_mesh(root/'parts'/f'{n}.stl') for n in (part,'torso')}
                for label,root in [('before',OLD),('after',HYBRID)]}
        for angle in (25,30,35):
            row={'joint':name,'outward_deg':angle}
            for label,m in meshes.items():
                row[label+'_overlap_mm3']=overlap_volume(m['torso'],rotated(m[part],center,(1,0,0),sign*angle))
            rows.append(row);print(row,flush=True)
        check=sweep(name,'torso',part,center,(('outward_spread',(1,0,0),(sign*30,)),))
        checks.append(check)
    report={'scope':'1.2.4 versus 1.2.5 actual torso/limb outward spread; full assembly checked at 30 degrees. Feet follow hips. Anatomy may still limit movement; not continuous motion or snap-force validation.',
            'comparisons':rows,'full_assembly_30deg':checks,
            'all_four_30deg_pass':all(c['passed'] for c in checks)}
    (ROOT/'build/reports/circumferential_motion_comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('all_four_30deg_pass',report['all_four_30deg_pass'],flush=True)

if __name__=='__main__':main()
