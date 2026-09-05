"""Compare unchanged source anatomy with previous/new socket hardware."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import trimesh
from hybrid_context import H,HYBRID
from hybrid_validate_motion import overlap_volume,rotated,sweep

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'backups/revision_1_2_3_before_shallow_sockets/hybrid_20260830'

def main():
    rows=[];full_checks=[]
    for name,part in [('shoulder_left','arm_left'),('shoulder_right','arm_right'),('hip_left','leg_left'),('hip_right','leg_right')]:
        spec=next(s for s in H['connections'] if s['name']==name)
        axis=(1,0,0);center=H[spec['center_key']];sign=spec['mouth_direction'][1]
        meshes={label:{p:trimesh.load_mesh(root/'parts'/f'{p}.stl') for p in [part,'torso']} for label,root in [('old',OLD),('new',HYBRID)]}
        for angle in [15,25,35]:
            row={'joint':name,'outward_spread_deg':angle}
            for label in meshes:
                row[label+'_overlap_mm3']=overlap_volume(meshes[label]['torso'],rotated(meshes[label][part],center,axis,sign*angle))
            rows.append(row);print(row,flush=True)
        check=sweep(name,'torso',part,center,(('outward_spread',(1,0,0),(sign*25,)),))
        full_checks.append(check);print('All-part 25deg check',name,check['passed'],flush=True)
    result={'scope':'Sampled torso/limb outward spread comparison, plus current 25-degree pose against all other parts with feet following hips. Not a continuous-motion guarantee. Other anatomical stops may remain.','comparisons':rows,'full_assembly_25deg':full_checks,'passed':all(c['passed'] for c in full_checks)}
    (ROOT/'build/reports/socket_motion_comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')

if __name__=='__main__':main()
