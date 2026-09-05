"""Comparative linear specimen checks, NOT a socket preload or snap simulation."""
import json,subprocess,sys
from pathlib import Path
from cae_actual_bone import parse_gmsh_inp,parse_results,chunks
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT.parent
P=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'));C=P['joint_retention_trial'];OUT=ROOT/C['output_directory']
T=json.loads((ROOT/'config/toolchain.json').read_text(encoding='utf-8'))
def main(names=None):
    directory=OUT/'cae';directory.mkdir(exist_ok=True);reports=[]
    if names is None:names=['locking_key','ball_key']+[v['label']+'_ball_key' for v in C['deep_c4']['variants']]
    for name in names:
        output=directory/(name+'_mesh.inp')
        run=subprocess.run([str(WORK/T['gmsh']['executable']),str((OUT/'parts'/(name+'.step')).relative_to(ROOT)),
            '-3','-order','1','-clmax',str(C['cae_mesh_size_mm']),'-format','inp','-o',str(output.relative_to(ROOT)),'-v','2'],cwd=ROOT,capture_output=True,text=True,timeout=120)
        assert run.returncode==0,run.stderr
        nodes,elements=parse_gmsh_inp(output);assert nodes and elements
        if name=='locking_key':
            limit=C['rail_front_x_mm'];height=C['key_half_height_mm']
            fixed=[n for n,(x,y,z) in nodes.items() if x<limit and z<-height+0.03]
            loaded=[n for n,(x,y,z) in nodes.items() if x<limit and z>height-0.03]
            force=C['proof_key_separation_load_n'];scope='Ideal key top/bottom distributed tension, no groove contact or stress singularity certification'
        else:
            xmax=max(x for x,y,z in nodes.values());xmin=min(x for x,y,z in nodes.values())
            fixed=[n for n,(x,y,z) in nodes.items() if x>xmax-0.5]
            loaded=[n for n,(x,y,z) in nodes.items() if x<xmin+0.5]
            force=C['comparison_ball_side_load_n'];scope='1 N side load on ball, handle fixed; comparative thin-stem bending, not insertion-force proof'
        assert len(fixed)>3 and len(loaded)>3,(name,len(fixed),len(loaded))
        lines=['*HEADING',name+' linear comparison','*NODE']
        lines += [f'{n},{x:.10g},{y:.10g},{z:.10g}' for n,(x,y,z) in nodes.items()]
        lines+=['*ELEMENT,TYPE=C3D4,ELSET=ALL']+[str(n)+','+','.join(map(str,conn)) for n,conn in elements]
        for label,ids in [('FIX',fixed),('LOAD',loaded)]:
            lines+=['*NSET,NSET='+label]+[','.join(map(str,part)) for part in chunks(ids)]
        mat=C['cae_material']
        lines+=['*SOLID SECTION,ELSET=ALL,MATERIAL=PLA','','*MATERIAL,NAME=PLA','*ELASTIC',f"{mat['youngs_modulus_mpa']},{mat['poisson_ratio']}",
                '*STEP','*STATIC','*BOUNDARY','FIX,1,3,0','*CLOAD']
        lines += [f'{n},3,{force/len(loaded):.12g}' for n in loaded]
        lines += ['*NODE PRINT,NSET=LOAD','U','*EL PRINT,ELSET=ALL','S','*END STEP']
        deck=directory/(name+'.inp');deck.write_text('\n'.join(lines)+'\n',encoding='ascii')
        run=subprocess.run([str(WORK/T['calculix']['executable']),name],cwd=directory,capture_output=True,text=True,timeout=120)
        displacement,stress=parse_results(directory/(name+'.dat'))
        assert run.returncode==0 and displacement is not None and stress is not None
        ratio=mat['tensile_reference_mpa']/stress
        row={'name':name,'nodes':len(nodes),'elements':len(elements),'load_n':force,'displacement_mm':displacement,'max_von_mises_mpa':stress,
             'tensile_reference_ratio_not_certified_safety_factor':ratio,'solver_passed':True,'scope':scope}
        reports.append(row);print(json.dumps(row),flush=True)
    report={'solver_completed':True,'physical_strength_verified':False,'material':C['cae_material'],'specimens':reports,
            'limitations':['Linear scalar material, not orthotropic layer or contact model.','No plastic set, friction, creep, wear, key withdrawal or snap insertion prediction.','C4 narrow stems need gentler handling; do not force an unseated ball.']}
    (OUT/'cae_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':main()
